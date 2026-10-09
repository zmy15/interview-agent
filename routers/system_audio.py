"""
系统音频转写路由 — 捕获「电脑正在播放的声音」并实时转成文字

接口：
    GET  /system-audio/info      能力、可用设备、当前配置
    GET  /system-audio/devices   可捕获的播放设备列表
    GET  /system-audio/status    运行状态（含 STT 连接情况与电平）
    POST /system-audio/start     开始捕获并转写
    POST /system-audio/stop      停止捕获
    GET  /system-audio/transcript 增量拉取转写结果（?since=<seq>）
    POST /system-audio/clear     清空转写结果

认证策略：与 screenshot 路由一致，使用 get_optional_user。
    AUTH_REQUIRED=true  → 未登录返回 401
    AUTH_REQUIRED=false → 单用户模式，无需登录

设计说明：
    转写结果放在**服务端内存**里按 seq 递增，前端轮询增量拉取。
    没有用 SSE/WebSocket 直接推给前端，是因为：
      1) 音频流的实时性由后端到 STT 那段保证，前端只需展示；
      2) 轮询实现简单、断线自动恢复，不会因为前端刷新丢历史。
    后续若需要更低延迟，可在此基础上加一个 SSE 通道。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from config import settings
from models.schemas import (
    SystemAudioDevice,
    SystemAudioInfoResponse,
    SystemAudioStartRequest,
    SystemAudioStartResponse,
    SystemAudioStatusResponse,
    SystemAudioTranscriptResponse,
)
from services import system_audio as sa
from utils.auth import CurrentUser, get_optional_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system-audio", tags=["system-audio"])

# 当前转写会话（全局唯一：同一时刻只捕获一路系统音频）
_session = None


def _ensure_enabled() -> None:
    if not settings.SYSTEM_AUDIO_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="系统音频捕获未启用（设置 SYSTEM_AUDIO_ENABLED=true 后重启服务）",
        )


def _get_session():
    return _session


@router.get("/info", response_model=SystemAudioInfoResponse)
async def system_audio_info(
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """返回系统音频捕获的可用性、设备列表与默认配置。

    即使不可用也返回 200，由 available/error 字段说明原因，
    这样前端可以展示明确的引导提示，而不是一个红色报错。
    """
    _ensure_enabled()

    if not sa.is_available():
        return SystemAudioInfoResponse(
            available=False,
            error=sa.availability_error(),
            devices=[],
            configured_device=settings.SYSTEM_AUDIO_DEVICE or None,
            running=False,
        )

    devices = sa.list_loopback_devices()

    return SystemAudioInfoResponse(
        available=True,
        error=None,
        devices=[SystemAudioDevice(**d) for d in devices],
        configured_device=settings.SYSTEM_AUDIO_DEVICE or None,
        running=_session is not None,
        block_ms=settings.SYSTEM_AUDIO_BLOCK_MS,
        sample_rate=sa.TARGET_SAMPLE_RATE,
    )


@router.get("/devices", response_model=list[SystemAudioDevice])
async def list_devices(
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """可捕获的播放设备（每个扬声器都能回环抓取其播放内容）"""
    _ensure_enabled()

    if not sa.is_available():
        raise HTTPException(status_code=503, detail=sa.availability_error())

    return [SystemAudioDevice(**d) for d in sa.list_loopback_devices()]


@router.get("/status", response_model=SystemAudioStatusResponse)
async def status(
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """当前运行状态：是否在抓、电平多少、STT 是否连上"""
    _ensure_enabled()

    base = {
        "available": sa.is_available(),
        "error": None if sa.is_available() else sa.availability_error(),
    }
    session = _get_session()
    if session is None:
        return SystemAudioStatusResponse(
            **base,
            running=False,
            stt_connected=False,
            transcript_count=0,
        )

    st = session.status()
    return SystemAudioStatusResponse(
        **base,
        running=bool(st["capture"].get("running")),
        device=st["capture"].get("device"),
        seconds=st["capture"].get("seconds", 0.0),
        peak=st["capture"].get("peak", 0.0),
        rms=st["capture"].get("rms", 0.0),
        voiced=st["capture"].get("voiced", False),
        stt_connected=st["stt_connected"],
        stt_error=st["stt_error"] or None,
        audio_error=st["audio_error"] or None,
        transcript_count=st["transcript_count"],
    )


@router.post("/start", response_model=SystemAudioStartResponse)
async def start(
    req: SystemAudioStartRequest,
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """开始捕获系统音频并实时转写。

    **幂等**：若已在运行且设备一致，直接返回当前状态，不做任何重建。

    为什么必须幂等：
        界面重挂载（路由切换、React StrictMode 的挂载-卸载-再挂载、
        状态水合）都会再调一次 start。早期实现每次 start 都把旧会话
        停掉重建，导致捕获被反复拆装 —— 表现为日志里密集的
        「已停止 / 已启动」，且每次都丢失已识别的文字。
        捕获是「持续状态」，不该被重复的启动请求打断。

    只有显式传入不同的 device_id 时，才会切换到新设备。
    """
    global _session
    _ensure_enabled()

    if not sa.is_available():
        raise HTTPException(status_code=503, detail=sa.availability_error())

    requested_device = (req.device_id or settings.SYSTEM_AUDIO_DEVICE or "").strip() or None

    # ── 已在运行：按幂等语义直接复用 ──
    if _session is not None:
        current = _session.status()
        if current["capture"].get("running"):
            running_device_id = (_session.device_id or "").strip() or None
            # 设备一致（或调用方没指定设备）→ 复用，不重建
            if requested_device in (None, running_device_id):
                logger.info("系统音频已在运行，复用现有会话（设备=%s）", current["capture"].get("device"))
                return SystemAudioStartResponse(
                    running=True,
                    device=current["capture"].get("device") or "",
                    device_id=running_device_id,
                    stt_connected=current["stt_connected"],
                    stt_error=current["stt_error"] or None,
                    sample_rate=sa.TARGET_SAMPLE_RATE,
                    block_ms=settings.SYSTEM_AUDIO_BLOCK_MS,
                )

        # 设备变了（或旧会话已死）：停掉再按新设备启动
        try:
            await _session.stop()
        except Exception as exc:
            logger.warning("停止旧会话失败（忽略）: %s", exc)
        _session = None

    from services.audio_transcribe import AudioTranscribeSession

    session = AudioTranscribeSession(device_id=requested_device)

    try:
        info = await session.start()
    except sa.SystemAudioError as exc:
        # 设备打不开属于可预期的用户侧问题
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _session = session

    return SystemAudioStartResponse(
        running=True,
        device=info["device"],
        device_id=info.get("device_id") or None,
        stt_connected=session.stt_connected,
        stt_error=session.stt_error or None,
        sample_rate=sa.TARGET_SAMPLE_RATE,
        block_ms=settings.SYSTEM_AUDIO_BLOCK_MS,
    )


@router.post("/stop", response_model=SystemAudioStatusResponse)
async def stop(
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """停止捕获（转写结果保留，可继续用 /transcript 拉取）"""
    global _session
    _ensure_enabled()

    session = _session
    if session is None:
        return SystemAudioStatusResponse(
            available=sa.is_available(),
            running=False,
            stt_connected=False,
            transcript_count=0,
        )

    await session.stop()
    _session = None

    return SystemAudioStatusResponse(
        available=sa.is_available(),
        running=False,
        stt_connected=False,
        transcript_count=session.store.latest_seq(),
    )


@router.get("/transcript", response_model=SystemAudioTranscriptResponse)
async def transcript(
    since: int = 0,
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """增量拉取转写结果。

    since 传上次拿到的最大 seq，只返回更新的行，避免重复渲染。
    """
    _ensure_enabled()

    session = _get_session()
    if session is None:
        return SystemAudioTranscriptResponse(
            lines=[],
            latest_seq=0,
            running=False,
            stt_connected=False,
        )

    lines = session.store.since(since)
    return SystemAudioTranscriptResponse(
        lines=lines,
        latest_seq=session.store.latest_seq(),
        running=bool(session.status()["capture"].get("running")),
        stt_connected=session.stt_connected,
        stt_error=session.stt_error or None,
    )


@router.post("/clear")
async def clear(
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """清空已累积的转写结果（不影响正在进行的捕获）"""
    _ensure_enabled()

    session = _get_session()
    if session is None:
        return {"cleared": False, "message": "当前没有捕获会话"}

    session.store.clear()
    return {"cleared": True, "message": "转写结果已清空"}