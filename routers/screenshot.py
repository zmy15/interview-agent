"""
截图识别路由 — 整屏截图 + DeepSeek 视觉提取题目并作答

接口：
    GET  /screenshot/info      截图能力与显示器信息
    POST /screenshot/capture   整屏截图并交给 AI 识别作答

认证策略：与 chat 路由保持一致，使用 get_optional_user。
    AUTH_REQUIRED=true  → 未登录返回 401
    AUTH_REQUIRED=false → 单用户模式，无需登录
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from config import settings
from models.schemas import (
    CaptureRequest,
    CaptureResponse,
    MonitorItem,
    ScreenshotInfoResponse,
)
from services import screen_capture as sc
from utils.auth import CurrentUser, get_optional_user
from utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screenshot", tags=["screenshot"])

# 提示词模板名（对应 prompts/screenshot.txt）
_PROMPT_TEMPLATE = "screenshot"

# 用户未提供 prompt 时的默认提问
_DEFAULT_QUESTION = "请提取截图中的问题并回答。"

_VALID_MONITORS = {"primary"}


def _ensure_enabled() -> None:
    if not settings.SCREENSHOT_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="截图识别功能未启用（设置 SCREENSHOT_ENABLED=true 后重启服务）",
        )


@router.get("/info", response_model=ScreenshotInfoResponse)
async def screenshot_info(
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """返回截图可用性与显示器列表。

    即使截图不可用也返回 200，由 available/error 字段说明原因，
    这样前端可以展示明确的引导提示，而不是一个红色报错。
    """
    _ensure_enabled()

    if not sc.is_available():
        return ScreenshotInfoResponse(
            available=False,
            error=sc.availability_error(),
            monitors=[],
            vision_model=settings.SCREENSHOT_VISION_MODEL,
        )

    try:
        monitors = sc.list_monitors()
    except Exception as exc:
        logger.warning("获取显示器列表失败: %s", exc)
        monitors = []

    return ScreenshotInfoResponse(
        available=True,
        error=None,
        monitors=[MonitorItem(**m) for m in monitors],
        vision_model=settings.SCREENSHOT_VISION_MODEL,
    )


@router.post("/capture", response_model=CaptureResponse)
async def capture(
    req: CaptureRequest,
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """截取整个屏幕，交给 DeepSeek 视觉模型识别题目并作答。"""
    _ensure_enabled()

    if not sc.is_available():
        raise HTTPException(status_code=503, detail=sc.availability_error())

    started = time.perf_counter()

    # ── 1) 截取主显示器 ──
    try:
        img = sc.grab_screen(cursor=req.include_cursor)
    except sc.CaptureError as exc:
        # 截图失败属于可预期的用户侧问题，返回 400 而不是 500
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ── 2) 编码 ──
    try:
        data_url, raw = sc.encode_image(img, settings.SCREENSHOT_MAX_IMAGE_EDGE)
    except sc.CaptureError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ── 4) 保存（失败不影响识别） ──
    should_save = settings.SCREENSHOT_SAVE if req.save is None else req.save
    image_path: Optional[str] = None
    if should_save:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        try:
            image_path = sc.save_image(raw, f"shot_{stamp}.png")
        except sc.CaptureError as exc:
            logger.warning("截图保存失败（继续识别）: %s", exc)

    # ── 5) 组装提示词 ──
    # 模板来自 prompts/screenshot.txt，遵循项目统一的 prompt 管理方式；
    # 用户在界面上填写的补充说明作为提问追加。
    try:
        system_prompt = load_prompt(_PROMPT_TEMPLATE)
    except FileNotFoundError:
        logger.warning("提示词模板 %s.txt 缺失，使用内置精简版", _PROMPT_TEMPLATE)
        system_prompt = (
            "你是面试答题助手。请先逐字提取截图中的题目，再给出答案，"
            "并列出不确定之处。若图中没有题目，请如实说明，不要编造。"
        )

    # load_prompt 走的是 ChatPromptTemplate.format()，返回值会带上
    # "System: " 前缀（这是该工具链的行为）。此处要把内容作为真正的
    # system 消息发送，前缀必须去掉，否则会污染提示词。
    if system_prompt.startswith("System: "):
        system_prompt = system_prompt[len("System: "):]
    system_prompt = system_prompt.strip()

    question = (req.prompt or "").strip() or _DEFAULT_QUESTION

    # ── 6) 调用视觉模型 ──
    try:
        answer, used_model = await sc.ask_vision(
            data_url,
            prompt=question,
            system_prompt=system_prompt,
            api_key=req.api_key,
            model=req.model,
        )
    except sc.CaptureError as exc:
        # 模型侧问题（Key 无效 / 无视觉模型）返回 502
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return CaptureResponse(
        answer=answer,
        model=used_model,
        monitor="primary",
        width=img.width,
        height=img.height,
        image_bytes=len(raw),
        image_path=image_path,
        elapsed_ms=elapsed_ms,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )