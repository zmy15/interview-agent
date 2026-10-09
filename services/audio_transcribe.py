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
import itertools
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


# 进程级单调递增的序号。
#
# 为什么不能每个 TranscriptStore 从 0 开始计数：
#   前端按「上次拿到的最大 seq」增量拉取（/transcript?since=N）。
#   若会话重建后 seq 重新从 1 开始，而前端已经推进到 N>1，
#   那么新产生的行（seq=1,2,3…）永远不满足 `seq > since`，
#   前端会一直请求 since=N 且永远拿不到新内容 ——
#   日志里持续出现的 "transcript?since=0"（不推进）就是这个症状。
#   用全局计数器可保证「后产生的行序号一定更大」。
_seq_counter = itertools.count(1)
_seq_counter_lock = threading.Lock()


@dataclass
class TranscriptStore:
    """转写结果的内存环形缓冲。

    前端按 `since`（上次拿到的最大 seq）增量拉取，避免重复渲染。
    序号来自进程级计数器（见 _seq_counter），跨会话单调递增。
    """
    maxlen: int = 200
    lines: deque = field(default_factory=lambda: deque(maxlen=200))
    _last_seq: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        self.lines = deque(maxlen=max(1, self.maxlen))

    def add(self, text: str, kind: str, ts: Optional[float] = None) -> TranscriptLine:
        with self._lock:
            seq = next(_seq_counter)
            self._last_seq = seq
            line = TranscriptLine(
                seq=seq,
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
            return self._last_seq

    def clear(self) -> None:
        """清空缓冲。

        注意：**不重置计数器**。前端可能已经推进到很大的 seq，
        若这里归零，之后的新行会因 `seq > since` 不成立而永远拉不到。
        清空只影响内容，不影响序号单调性。
        """
        with self._lock:
            self.lines.clear()


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
        self._reconnect_task: Optional[asyncio.Task] = None
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

    async def _teardown_ws(self) -> None:
        """关闭并清理当前的 WebSocket 与接收任务（可重复调用）

        重连路径与 stop() 都走这里，避免两处各写一份清理逻辑而遗漏。
        """
        task = self._recv_task
        self._recv_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        ws = self._ws
        self._ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass

        self.stt_connected = False

    async def _connect_stt(self) -> None:
        """连接 stt_service 的 /stream

        超时给得比较宽松（默认 30s）：STT 微服务在 WebSocket **握手期间**
        就会加载 Whisper 模型（main.py 里 `_ensure_model()` 在 `accept()`
        之前调用），首次连接可能等十几秒。超时太短会把「正在加载模型」
        误报成「连不上」。

        心跳（ping_interval / ping_timeout）也放宽：
            STT 侧在首次转录时会**同步阻塞事件循环**加载/运行模型，
            期间无法及时回 pong。默认 20s/20s 会因此判定连接死亡
            （日志里的 "keepalive ping timeout; no close frame received"）。
            这里把 ping_timeout 设得足够大，让它不至于被误杀。
        """
        import websockets

        url = self._stt_ws_url()
        timeout = max(5.0, float(settings.SYSTEM_AUDIO_STT_TIMEOUT))
        ping_timeout = max(30.0, float(settings.SYSTEM_AUDIO_STT_PING_TIMEOUT))

        # 重连前先彻底清理上一次的连接与接收任务，
        # 否则每断一次线就泄漏一个 websocket 与一个后台任务。
        await self._teardown_ws()

        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    open_timeout=timeout,
                    # 心跳间隔比超时略小，保证有多次机会
                    ping_interval=max(20.0, ping_timeout / 3.0),
                    ping_timeout=ping_timeout,
                    # 单帧上限放大：一段音频可能较大
                    max_size=None,
                ),
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
            # 提示里必须带上实际尝试的地址：地址不对是最常见的原因，
            # 不写出来用户根本无从判断。
            # 也不要让人去开 STT_ENABLED —— 那条链路只控制浏览器的
            # /stt 代理路由，与本模块直连微服务无关。
            self.stt_error = (
                f"无法连接 STT 微服务（{url}）：{detail}。"
                "音频捕获仍在进行，但不会产生文字；"
                "请确认该地址上的 STT 服务已启动"
                "（本地一般为 STT_SERVICE_URL=http://localhost:8001）。"
            )
            logger.warning(self.stt_error)

    def _stt_ws_url(self) -> str:
        """推导 STT 的 WebSocket 地址。

        优先级：显式配置的 STT_WS_URL > 由 STT_SERVICE_URL 推导。

        为什么不无条件用 STT_WS_URL：
            它的默认值是 Docker 内部服务名 `ws://stt:8000/stream`
            （见 config.py）。本地直接把 STT 跑在 localhost:8001 时，
            宿主机解析不了 `stt` 这个主机名，会报
            「getaddrinfo failed」，且因为默认值非空，
            永远走不到从 STT_SERVICE_URL 推导的分支。
            因此凡是「没配」或「等于 Docker 默认值」的情况，
            都改用 STT_SERVICE_URL 推导。
        """
        explicit = (settings.STT_WS_URL or "").strip()

        # config.py 里的 Docker 默认值，本地场景下应当忽略
        docker_default = "ws://stt:8000/stream"
        if explicit and explicit != docker_default:
            return explicit if explicit.endswith("/stream") else explicit.rstrip("/") + "/stream"

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

        两种消息的语义与处理方式**不同**：

        - `partial`：本段正在识别的文本。STT 会反复推送，
          且相邻两次常互为前缀/重复，因此做增量去重，
          只保留新增部分，避免前端刷重复行。
        - `final`：一句话已结束，是**给 AI 用的完整句子**，
          必须无条件产出，不参与去重。

        回归（曾导致功能完全不可用）：
            早期实现让 partial 与 final 共用同一个 _last_text 去重。
            由于 STT 常先推 partial("你好") 再推内容完全相同的
            final("你好")，final 会被判为「重复」而丢弃 ——
            结果是库里只有 partial、一条 final 都没有，
            而前端只把 final 交给 AI，于是「识别成功但从不发送」。
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
                elif mtype == "final":
                    text = (msg.get("text") or "").strip()
                    if not text:
                        continue
                    # final 必须发出：它是断句后的完整句子，前端据此提问。
                    # 不做去重，也不推进 partial 的前缀游标。
                    self._last_final = text
                    self.store.add(text, "final", msg.get("ts"))
                    logger.info("转写完成: %s", text[:80])
                elif mtype == "partial":
                    text = (msg.get("text") or "").strip()
                    if not text:
                        continue
                    added = self._new_suffix(text)
                    if not added:
                        continue
                    self._last_text = text
                    self.store.add(added, "partial", msg.get("ts"))
                elif mtype == "error":
                    self.stt_error = msg.get("message") or "STT 返回错误"
                    logger.warning("STT 错误: %s", self.stt_error)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if not self._stopping:
                self.stt_connected = False
                self.stt_error = f"STT 连接中断：{exc}"
                logger.warning(self.stt_error)
                # 断线自动重连：音频捕获线程仍在跑，只要重连成功
                # 就能继续把后续语音转成文字。否则一次网络抖动
                # （或 STT 侧模型加载导致的 ping 超时）就会让整个
                # 功能永久失效，用户只能手动关了开关再开。
                self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """安排一次重连（串行、带退避，避免疯狂重试）"""
        if self._stopping or self._loop is None or self._loop.is_closed():
            return
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        try:
            self._reconnect_task = self._loop.create_task(self._reconnect_loop())
        except RuntimeError:
            # 事件循环已关闭（进程退出中）
            pass

    async def _reconnect_loop(self) -> None:
        """按退避策略反复尝试重连，直到成功或会话被停止"""
        delay = 2.0
        max_delay = 30.0
        attempt = 0

        while not self._stopping:
            attempt += 1
            await asyncio.sleep(delay)
            if self._stopping:
                return

            logger.info("尝试重连 STT（第 %d 次）…", attempt)
            await self._connect_stt()

            if self.stt_connected:
                logger.info("STT 重连成功")
                return

            # 指数退避，避免 STT 长时间不可用时刷屏
            delay = min(delay * 2, max_delay)

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

        # 1) 取消可能正在进行的重连，避免停止后又被连回来
        reconnect = self._reconnect_task
        self._reconnect_task = None
        if reconnect is not None and not reconnect.done():
            reconnect.cancel()
            try:
                await reconnect
            except (asyncio.CancelledError, Exception):
                pass

        # 2) 停止捕获（阻塞式 join，放到线程里避免卡住事件循环）
        await asyncio.to_thread(sa.stop_capture)

        # 3) 通知 STT 冲刷剩余音频，拿到最后一段文本
        #
        #    顺序很关键：必须先 flush + 等待 final 返回，**最后**才关闭
        #    连接。反过来会丢掉最后一句。
        ws = self._ws
        if ws is not None and self.stt_connected:
            try:
                await asyncio.wait_for(ws.send(json.dumps({"type": "flush"})), timeout=3.0)
                # 给 flush 一点时间返回 final（Whisper 转录需要时间）
                await asyncio.sleep(1.5)
            except Exception:
                pass

        # 4) 关闭连接与后台任务（与重连路径共用同一套清理）
        await self._teardown_ws()

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