"""
系统音频转写会话 — 把回环抓到的音频持续送入 STT 微服务，收集转写结果

数据流：
    LoopbackCapture（线程）
        └─ on_frame(pcm_bytes, samples)
              └─ asyncio.run_coroutine_threadsafe → 事件循环
                    └─ WebSocket → stt_service /stream
                          └─ VAD 断句 → faster-whisper → partial/final
                                └─ 写入内存环形缓冲，前端按 seq 增量拉取

为什么走 STT 微服务的 WebSocket 而不是本地直接调 faster-whisper：
    模型（Whisper + Silero VAD）体积大、初始化慢，项目里已经把这部分
    隔离在独立微服务，由它做单例复用。主进程直接加载会拖慢启动、
    并让「没装 torch 也能跑主服务」这一现状失效。

降级策略：
    STT 微服务不可用时（未启用 / 未启动 / 连接失败），捕获仍然继续，
    只是没有转写结果；状态里会带上 stt_error 说明原因，前端可提示用户。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class TranscriptLine:
    """一条转写文本（final=断句完成，partial=当前正在说的）"""
    seq: int
    text: str
    kind: str            # "partial" / "final"
    ts: float            # 相对捕获开始的秒数（未提供时为墙上时间）


@dataclass
class TranscriptStore:
    """转写结果的内存环形缓冲。

    前端按 `since`（上次拿到的最大 seq）增量拉取，避免重复渲染。
    """
    maxlen: int = 200
    lines: deque = field(default_factory=lambda: deque(maxlen=200))
    _seq: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        self.lines = deque(maxlen=max(1, self.maxlen))

    def add(self, text: str, kind: str, ts: Optional[float] = None) -> TranscriptLine:
        with self._lock:
            self._seq += 1
            line = TranscriptLine(
                seq=self._seq,
                text=text,
                kind=kind,
                ts=ts if ts is not None else time.time(),
            )
            self.lines.append(line)
            return line

    def since(self, since_seq: int = 0) -> list[dict]:
        with self._lock:
            return [asdict(l) for l in self.lines if l.seq > since_seq]

    def latest_seq(self) -> int:
        with self._lock:
            return self._seq

    def clear(self) -> None:
        with self._lock:
            self.lines.clear()
            self._seq = 0


class AudioTranscribeSession:
    """一路「回环捕获 → STT 微服务」的会话。

    生命周期：
        start()  → 启动捕获线程 + 建立 WS 连接
        stop()   → 关闭 WS + 停止捕获
    """

    def __init__(self, device_id: Optional[str] = None):
        self.device_id = device_id
        self.store = TranscriptStore(maxlen=settings.SYSTEM_AUDIO_TRANSCRIPT_BUFFER)

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws: Any = None
        self._ws_task: Optional[asyncio.Task] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._ready = threading.Event()
        self._stopping = False

        self.stt_connected = False
        self.stt_error = ""
        self.audio_error = ""
        self._last_final = ""
        # 上一条累积文本（STT 的 partial/final 都是累积语义，用于去重）
        self._last_text = ""
        self._capture = None

    # ── 启动 ──

    async def start(self) -> dict:
        """启动捕获并连接 STT（在事件循环中调用）"""
        from services import system_audio as sa

        self._loop = asyncio.get_running_loop()
        self._stopping = False
        self._ready.clear()

        # 1) 先连 STT：连不上也不阻断捕获，只记录原因
        await self._connect_stt()

        # 2) 启动回环捕获（线程回调 → 投递回本事件循环）
        capture = sa.start_capture(
            device_id=self.device_id,
            on_frame=self._on_frame_threadsafe,
            on_error=self._on_audio_error,
        )
        self._capture = capture
        return {
            "device": capture.device_name,
            "device_id": capture.device_id or "",
            "source": capture.source_format,
            "target": {
                "sample_rate": sa.TARGET_SAMPLE_RATE,
                "channels": sa.TARGET_CHANNELS,
            },
        }

    async def _connect_stt(self) -> None:
        """连接 stt_service 的 /stream

        超时给得比较宽松（默认 30s）：STT 微服务在 WebSocket **握手期间**
        就会加载 Whisper 模型（main.py 里 `_ensure_model()` 在 `accept()`
        之前调用），首次连接可能等十几秒。超时太短会把「正在加载模型」
        误报成「连不上」。
        """
        import websockets

        url = self._stt_ws_url()
        timeout = max(5.0, float(settings.SYSTEM_AUDIO_STT_TIMEOUT))
        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(url, open_timeout=timeout),
                timeout=timeout + 5.0,
            )
            self.stt_connected = True
            self.stt_error = ""
            self._recv_task = asyncio.create_task(self._recv_loop())
            logger.info("系统音频已连接 STT 微服务: %s", url)
        except asyncio.TimeoutError:
            self.stt_connected = False
            self._ws = None
            self.stt_error = (
                f"连接 STT 微服务超时（{url}，>{timeout:.0f}s）。"
                "若该服务是首次启动，可能正在加载 Whisper 模型，稍后重试即可；"
                "否则请确认 STT_SERVICE_URL 正确且 stt 服务已启动。"
            )
            logger.warning(self.stt_error)
        except Exception as exc:
            self.stt_connected = False
            self._ws = None
            detail = str(exc) or type(exc).__name__
            self.stt_error = (
                f"无法连接 STT 微服务（{url}）：{detail}。"
                "音频捕获仍在进行，但不会产生文字；"
                "请确认 STT_ENABLED=true 且 stt 服务已启动。"
            )
            logger.warning(self.stt_error)

    def _stt_ws_url(self) -> str:
        """把 STT_SERVICE_URL（http://stt:8000）转成 ws://stt:8000/stream"""
        base = (settings.STT_WS_URL or "").strip()
        if base:
            return base if base.endswith("/stream") else base.rstrip("/") + "/stream"

        http = (settings.STT_SERVICE_URL or "http://127.0.0.1:8000").strip()
        if http.startswith("https://"):
            return "wss://" + http[len("https://"):].rstrip("/") + "/stream"
        if http.startswith("http://"):
            return "ws://" + http[len("http://"):].rstrip("/") + "/stream"
        return http.rstrip("/") + "/stream"

    # ── 音频帧：线程 → 事件循环 ──

    def _on_frame_threadsafe(self, pcm: bytes, samples) -> None:
        """捕获线程回调：把 PCM 帧投递到事件循环，避免跨线程直接用 WS"""
        loop = self._loop
        if loop is None or loop.is_closed() or self._stopping:
            return
        try:
            asyncio.run_coroutine_threadsafe(self._send_frame(pcm), loop)
        except RuntimeError:
            # 事件循环已关闭（进程退出中），忽略
            pass

    async def _send_frame(self, pcm: bytes) -> None:
        ws = self._ws
        if ws is None or not self.stt_connected:
            return
        try:
            await ws.send(pcm)
        except Exception as exc:
            self.stt_connected = False
            self.stt_error = f"STT 连接已断开：{exc}"
            logger.warning(self.stt_error)

    def _on_audio_error(self, message: str) -> None:
        self.audio_error = message

    # ── 接收转写结果 ──

    async def _recv_loop(self) -> None:
        """读取 STT 返回的 partial / final / vad / ready

        去重说明：
            STT 微服务的 `final` 是「本次会话累积全文」，`partial` 是
            「累积全文 + 当前段」。二者都会随每次断句重复推送**已经出现过
            的前缀**，直接全部落库会让前端看到大量重复行。
            因此这里只保留「新增的那部分」：拿新文本去掉已知前缀，
            空则丢弃。这是 STT 微服务的既有语义，在主进程侧做归一化
            比改动微服务协议更安全（前端与测试都按现有协议写）。
        """
        ws = self._ws
        if ws is None:
            return

        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                mtype = msg.get("type")
                if mtype == "ready":
                    self._ready.set()
                    logger.info(
                        "STT 就绪 | model=%s device=%s",
                        msg.get("model"), msg.get("device"),
                    )
                elif mtype in ("partial", "final"):
                    text = (msg.get("text") or "").strip()
                    if not text:
                        continue

                    added = self._new_suffix(text)
                    if not added:
                        # 与上一条完全相同或只是旧内容的前缀（重复推送）
                        continue

                    self._last_text = text
                    self.store.add(added, mtype, msg.get("ts"))
                    if mtype == "final":
                        self._last_final = text
                elif mtype == "error":
                    self.stt_error = msg.get("message") or "STT 返回错误"
                    logger.warning("STT 错误: %s", self.stt_error)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._stopping:
                self.stt_connected = False
                self.stt_error = f"STT 接收循环结束：{exc}"
                logger.warning(self.stt_error)

    def _new_suffix(self, text: str) -> str:
        """返回 text 相对上一条累积文本的新增部分（无新增则返回空串）

        STT 的累积文本存在轻微抖动（标点/空格），做一次宽松比较：
        上一版既可能是新版前缀，也可能反过来（重识别导致回退）。
        """
        prev = self._last_text
        if not prev:
            return text

        if text == prev:
            return ""
        if text.startswith(prev):
            return text[len(prev):].strip()
        if prev.startswith(text):
            # 重识别后变短：视为无新增，等下一次完整输出
            return ""

        # 两者不是前缀关系：视为全新内容
        return text

    # ── 停止 ──

    async def stop(self) -> None:
        from services import system_audio as sa

        self._stopping = True

        # 1) 停止捕获（阻塞式 join，放到线程里避免卡住事件循环）
        await asyncio.to_thread(sa.stop_capture)

        # 2) 通知 STT 冲刷剩余音频，拿到最后一段文本
        #
        #    顺序很关键：必须先 flush + 等待 final 返回，**最后**才取消
        #    接收循环。反过来会触发 stt_service 侧的
        #    「Cannot call receive once a disconnect message has been received」，
        #    并且丢掉最后一句。
        ws = self._ws
        if ws is not None and self.stt_connected:
            try:
                await asyncio.wait_for(ws.send(json.dumps({"type": "flush"})), timeout=3.0)
                # 给 flush 一点时间返回 final（Whisper 转录需要时间）
                await asyncio.sleep(1.5)
            except Exception:
                pass

        # 3) 关闭连接与后台任务
        if self._recv_task is not None:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except (asyncio.CancelledError, Exception):
                pass
            self._recv_task = None

        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
            self._ws = None

        self.stt_connected = False
        logger.info("系统音频转写会话已停止 | 共 %d 条", self.store.latest_seq())

    # ── 状态 ──

    def status(self) -> dict:
        from services import system_audio as sa

        return {
            "stt_connected": self.stt_connected,
            "stt_error": self.stt_error,
            "audio_error": self.audio_error,
            "last_final": self._last_final,
            "transcript_count": self.store.latest_seq(),
            "capture": sa.capture_status(),
        }