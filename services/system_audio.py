"""
系统音频捕获服务 — WASAPI 回环抓取「电脑正在播放的声音」

用途：
    面试场景下，题目/提问往往来自对方的声音（会议软件、视频、网页播放），
    麦克风录不到这些内容。本模块通过 Windows 的 **WASAPI loopback**
    从扬声器设备上回环抓取，得到与「人耳听到的」一致的音频流。

与截图功能的对称性：
    services/screen_capture.py  抓「屏幕上看到的」→ 视觉模型
    services/system_audio.py    抓「扬声器放出的」→ STT 转文字
    两者都属于「本机能力」，同样只在 Windows 桌面模式下有意义。

数据格式（关键）：
    统一输出 **16kHz / 单声道 / float32 [-1,1]** 的 PCM —— 这正是
    stt_service 的 VAD 与 faster-whisper 期望的输入格式。
    回环设备通常以 48kHz 立体声给出数据，因此这里必须做
    下混（多声道 → 单声道）与重采样（48k → 16k），否则 STT 拿到的是
    语速错乱的音频，转录结果会完全不可用。

为什么不用 sounddevice / PyAudio：
    它们的 loopback 支持在 Windows 上要么缺失、要么需要额外装
    PyAudioWPatch 之类的分支包。soundcard 直接暴露 WASAPI 回环，
    纯 cffi 实现、无需编译，跨 Python 版本稳定。
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from config import settings

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# ── 可选依赖：缺失时接口返回明确指引，而不是 500 ──
try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    import soundcard as sc

    SC_AVAILABLE = True
    SC_IMPORT_ERROR = ""
except Exception as _exc:  # pragma: no cover
    sc = None  # type: ignore[assignment]
    SC_AVAILABLE = False
    SC_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"


class SystemAudioError(RuntimeError):
    """系统音频捕获失败（可预期的错误，会被路由转换成 4xx）"""


# 目标格式：与 stt_service / faster-whisper 对齐
TARGET_SAMPLE_RATE = 16000
TARGET_CHANNELS = 1

# 拿不到设备原生采样率时的兜底值（WASAPI 共享模式常见混音格式）
DEFAULT_SOURCE_RATE = 48000


# ══════════════════════════════════════════════════════════════
# 可用性
# ══════════════════════════════════════════════════════════════


def is_available() -> bool:
    """系统音频捕获是否可用"""
    return bool(IS_WINDOWS and SC_AVAILABLE and np is not None)


def availability_error() -> str:
    """返回不可用的原因（可用时为空串），用于前端提示"""
    if not IS_WINDOWS:
        return "系统音频捕获仅支持 Windows（依赖 WASAPI 回环）"
    if not SC_AVAILABLE:
        return (
            f"soundcard 未安装或加载失败（{SC_IMPORT_ERROR}）。"
            "请执行：pip install soundcard"
        )
    if np is None:
        return "缺少 numpy，请执行：pip install numpy"
    return ""


# ══════════════════════════════════════════════════════════════
# 设备枚举
# ══════════════════════════════════════════════════════════════


def _safe_id(device) -> str:
    """soundcard 的 id 是形如 '{0.0.0.00000000}.{guid}' 的字符串"""
    return (getattr(device, "id", None) or getattr(device, "name", "")) or ""


def list_loopback_devices() -> list[dict]:
    """列出可用于回环捕获的扬声器（即「电脑发出的声音」的来源）。

    每个扬声器都能通过同 id 的 loopback 麦获取其播放内容，
    所以这里返回的是**播放设备**列表，而不是录音设备列表。
    """
    if not is_available():
        return []

    devices: list[dict] = []
    try:
        default_id = ""
        try:
            default_id = _safe_id(sc.default_speaker())
        except Exception:
            pass

        for speaker in sc.all_speakers():
            sid = _safe_id(speaker)
            devices.append({
                "id": sid,
                "name": speaker.name,
                "is_default": sid == default_id,
            })
    except Exception as exc:
        logger.warning("枚举回环设备失败: %s", exc)
        return []

    # 默认设备排在最前，方便前端直接取第一个
    devices.sort(key=lambda d: (not d["is_default"], d["name"]))
    return devices


def _resolve_loopback(device_id: Optional[str]):
    """按 id 取回环麦克风；id 为空或找不到时回退到默认扬声器的回环。

    返回 (loopback_mic, 展示名)。

    展示名统一用**扬声器**的名字而不是回环麦克风的名字：
    用户界面上看到的是「扬声器 (Realtek(R) Audio)」这样的设备，
    而回环麦克风在 soundcard 里叫「Loopback ...」，对用户没有意义。
    """
    if not is_available():
        raise SystemAudioError(availability_error())

    target_id = (device_id or "").strip()

    try:
        if target_id:
            # 先确认这个 id 对应哪个扬声器（用于展示名）
            display = target_id
            for speaker in sc.all_speakers():
                if _safe_id(speaker) == target_id:
                    display = speaker.name
                    break

            mic = sc.get_microphone(target_id, include_loopback=True)
            if mic is not None:
                return mic, display

            # 指定的设备不存在：明确报错，而不是静默换成别的设备
            available = "、".join(d["name"] for d in list_loopback_devices()) or "（无）"
            raise SystemAudioError(
                f"找不到指定的音频设备（{target_id}）。可用设备：{available}"
            )

        # 未指定：用默认扬声器的回环
        speaker = sc.default_speaker()
        if speaker is None:
            raise SystemAudioError("系统没有可用的默认播放设备")
        mic = sc.get_microphone(_safe_id(speaker), include_loopback=True)
        if mic is None:
            raise SystemAudioError(
                f"无法为默认播放设备「{speaker.name}」创建回环捕获"
            )
        return mic, speaker.name

    except SystemAudioError:
        raise
    except Exception as exc:
        raise SystemAudioError(f"获取回环音频设备失败：{exc}") from exc


# ══════════════════════════════════════════════════════════════
# 音频后处理：下混 + 重采样
# ══════════════════════════════════════════════════════════════


def to_mono(samples: "np.ndarray") -> "np.ndarray":
    """多声道 → 单声道（按通道求平均）"""
    if samples.ndim == 1:
        return samples
    if samples.shape[1] == 1:
        return samples[:, 0]
    return samples.mean(axis=1)


def resample_linear(samples: "np.ndarray", src_rate: int, dst_rate: int) -> "np.ndarray":
    """线性插值重采样。

    为什么用线性插值而不是 scipy/librosa：
        语音识别对重采样质量不敏感（Whisper 前端本就会做滤波与降采样），
        而线性插值零额外依赖、纯 numpy、可预测。
        引入 scipy 只为这一步不划算。
    """
    if src_rate == dst_rate or samples.size == 0:
        return samples.astype(np.float32, copy=False)

    duration = samples.shape[0] / float(src_rate)
    dst_len = max(1, int(round(duration * dst_rate)))
    src_idx = np.linspace(0.0, samples.shape[0] - 1, dst_len, dtype=np.float64)
    return np.interp(src_idx, np.arange(samples.shape[0]), samples).astype(np.float32)


def to_target_format(samples: "np.ndarray", src_rate: int) -> "np.ndarray":
    """把回环原始数据转成 16kHz 单声道 float32"""
    mono = to_mono(np.asarray(samples, dtype=np.float32))
    return resample_linear(mono, src_rate, TARGET_SAMPLE_RATE)


def pcm16_bytes(samples: "np.ndarray") -> bytes:
    """float32 [-1,1] → int16 小端字节流（STT WebSocket 的帧格式）"""
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


# ══════════════════════════════════════════════════════════════
# 捕获会话
# ══════════════════════════════════════════════════════════════


@dataclass
class CaptureStats:
    """一次捕获会话的运行统计"""
    started_at: float = 0.0
    frames: int = 0
    samples: int = 0          # 累计采到的**目标格式**采样点数
    peak: float = 0.0         # 近期峰值（用于判断是否真有声音）
    rms: float = 0.0          # 近期 RMS
    voiced: bool = False      # 近期是否检测到声音
    last_error: str = ""

    @property
    def seconds(self) -> float:
        return self.samples / float(TARGET_SAMPLE_RATE)


# 回调签名： (pcm_bytes, samples_float32) -> None
FrameCallback = Callable[[bytes, "np.ndarray"], None]


class LoopbackCapture:
    """从一个扬声器回环持续抓取音频，逐块回调。

    为什么放在独立线程：
        soundcard 的 recorder.record() 是**阻塞**的，会在内部等待音频块。
        放到 asyncio 事件循环里会直接卡死整个服务，因此必须丢到线程中，
        再通过回调把数据交回上层（上层用 asyncio.run_coroutine_threadsafe
        投递回事件循环）。
    """

    def __init__(
        self,
        device_id: Optional[str] = None,
        *,
        block_ms: int = 100,
        on_frame: Optional[FrameCallback] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.device_id = device_id
        self.block_ms = max(20, int(block_ms))
        self.on_frame = on_frame
        self.on_error = on_error
        self.stats = CaptureStats()

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._device_name: str = ""
        self._source_rate: int = 0
        self._source_channels: int = 0
        self._started = False
        # 状态读写锁：start/stop 会被路由并发调用
        self._lock = threading.Lock()

    # ── 只读属性 ──

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def source_format(self) -> dict:
        """回环设备的原始格式（排查「没声音」时很有用）"""
        return {"sample_rate": self._source_rate, "channels": self._source_channels}

    # ── 生命周期 ──

    def start(self) -> dict:
        """打开设备并启动抓取线程（非阻塞）"""
        with self._lock:
            if self.running:
                raise SystemAudioError("系统音频捕获已在运行中")

            mic, name = _resolve_loopback(self.device_id)

            # 采样率交给 soundcard 选（WASAPI 共享模式下会自动做格式转换），
            # 这里显式指定一个常见值，失败时再退回设备默认。
            self._stop_event.clear()
            self._device_name = name
            self.stats = CaptureStats(started_at=time.time())

            thread = threading.Thread(
                target=self._run,
                args=(mic,),
                name="system-audio-capture",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            self._started = True

        # 给线程一点时间真正打开设备，这样能尽早把「打不开」反馈给调用方
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if self.stats.frames > 0 or self.stats.last_error:
                break
            if not self.running:
                break
            time.sleep(0.05)

        if self.stats.last_error:
            self.stop()
            raise SystemAudioError(self.stats.last_error)

        logger.info(
            "系统音频捕获已启动 | 设备=%s | 源格式=%s | 目标=%dHz mono",
            self._device_name, self.source_format, TARGET_SAMPLE_RATE,
        )
        return {
            "device": self._device_name,
            "device_id": self.device_id or "",
            "source": self.source_format,
            "target": {"sample_rate": TARGET_SAMPLE_RATE, "channels": TARGET_CHANNELS},
        }

    def stop(self) -> None:
        """停止抓取并等待线程退出"""
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            self._thread = None
            self._started = False

        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        logger.info(
            "系统音频捕获已停止 | 累计 %.1fs | %d 帧",
            self.stats.seconds, self.stats.frames,
        )

    # ── 抓取线程主体 ──

    def _run(self, mic) -> None:
        block_frames = int(TARGET_SAMPLE_RATE * self.block_ms / 1000)

        try:
            # 回环设备用设备自身的原生格式最稳：WASAPI 共享模式下指定
            # 采样率会触发系统重采样，某些驱动会直接报错。
            # 这里按设备默认采样率录制，再自行重采样到 16k。
            native_rate = int(
                getattr(mic, "samplerate", 0)
                or getattr(getattr(mic, "default_samplerate", None), "__int__", lambda: 0)()
                or self._source_rate
                or DEFAULT_SOURCE_RATE
            )
            native_channels = int(getattr(mic, "channels", 0) or 0)

            if not native_rate or native_rate <= 0:
                native_rate = DEFAULT_SOURCE_RATE

            self._source_rate = native_rate

            with mic.recorder(samplerate=native_rate, blocksize=block_frames) as recorder:
                # 从 recorder 上再确认一次真实采样率（可能与请求值不同）
                actual_rate = int(getattr(recorder, "samplerate", 0) or 0)
                if actual_rate > 0:
                    self._source_rate = actual_rate

                # 按**源采样率**换算每次要读的帧数，保证每块约 block_ms
                src_block = max(1, int(self._source_rate * self.block_ms / 1000))

                while not self._stop_event.is_set():
                    data = recorder.record(numframes=src_block)
                    if data is None or len(data) == 0:
                        continue

                    # 通道数由实际数据决定（recorder.channels 可能是 None）
                    if self._source_channels == 0:
                        self._source_channels = (
                            int(data.shape[1]) if getattr(data, "ndim", 1) > 1 else 1
                        )

                    mono16k = to_target_format(data, self._source_rate)
                    if mono16k.size == 0:
                        continue

                    self._update_stats(mono16k)

                    if self.on_frame:
                        try:
                            self.on_frame(pcm16_bytes(mono16k), mono16k)
                        except Exception as exc:
                            # 回调里的异常不能打断抓取循环
                            logger.warning("音频帧回调异常: %s", exc)

        except Exception as exc:
            message = f"回环捕获失败：{exc}"
            # 主动 stop() 触发的关闭不算错误
            if not self._stop_event.is_set():
                self.stats.last_error = message
                logger.error("%s（设备=%s）", message, self._device_name)
                if self.on_error:
                    try:
                        self.on_error(message)
                    except Exception:
                        pass

    def _update_stats(self, samples: "np.ndarray") -> None:
        """更新运行统计。peak/rms 用指数滑动平均，反映「最近」是否有声音"""
        self.stats.frames += 1
        self.stats.samples += int(samples.size)

        peak = float(np.abs(samples).max()) if samples.size else 0.0
        rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0

        alpha = 0.3
        self.stats.peak = peak if self.stats.frames == 1 else (
            alpha * peak + (1 - alpha) * self.stats.peak
        )
        self.stats.rms = rms if self.stats.frames == 1 else (
            alpha * rms + (1 - alpha) * self.stats.rms
        )
        # 静音判定阈值：RMS 低于 0.005 视为「没有声音在播」
        self.stats.voiced = self.stats.rms > 0.005


# ══════════════════════════════════════════════════════════════
# 全局单例（同一时刻只允许一路捕获）
# ══════════════════════════════════════════════════════════════

_capture: Optional[LoopbackCapture] = None
_capture_lock = threading.Lock()


def get_capture() -> Optional[LoopbackCapture]:
    return _capture


def start_capture(
    device_id: Optional[str] = None,
    *,
    on_frame: Optional[FrameCallback] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> LoopbackCapture:
    """启动全局捕获会话（已在运行时先停掉旧的）"""
    global _capture
    with _capture_lock:
        if _capture is not None and _capture.running:
            _capture.stop()

        capture = LoopbackCapture(
            device_id=device_id,
            block_ms=settings.SYSTEM_AUDIO_BLOCK_MS,
            on_frame=on_frame,
            on_error=on_error,
        )
        capture.start()
        _capture = capture
        return capture


def stop_capture() -> bool:
    """停止全局捕获会话；返回是否真的停了一个正在跑的会话"""
    global _capture
    with _capture_lock:
        if _capture is None:
            return False
        was_running = _capture.running
        _capture.stop()
        _capture = None
        return was_running


def capture_status() -> dict:
    """当前捕获状态（供 /status 接口）"""
    capture = _capture
    if capture is None or not capture.running:
        return {"running": False}

    return {
        "running": True,
        "device": capture.device_name,
        "device_id": capture.device_id or "",
        "source": capture.source_format,
        "seconds": round(capture.stats.seconds, 2),
        "frames": capture.stats.frames,
        "peak": round(capture.stats.peak, 4),
        "rms": round(capture.stats.rms, 4),
        "voiced": capture.stats.voiced,
        "last_error": capture.stats.last_error,
    }