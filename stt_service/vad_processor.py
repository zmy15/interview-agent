"""
Silero VAD 流式处理器
实时检测语音活动（speech/silence），输出语音段边界事件。
"""

import logging
import threading
from typing import Optional
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class VADState(Enum):
    SILENCE = "silence"
    SPEECH = "speech"


# ══════════════════════════════════════════════════════════════
# Silero VAD 的输入约束
# ══════════════════════════════════════════════════════════════
#
# Silero 的 ONNX 模型对单次调用的样本数有**硬性要求**：
#   8kHz  → 256 样本
#   16kHz → 512 样本
# 而本模块的帧长是 100ms（16kHz 下 1600 样本），直接喂进去会抛
# ValueError: Provided number of samples is 1600 (Supported values: ...)。
#
# 早期实现把这次异常吞掉并当成 speech_prob=0，结果**永远检测不到语音**，
# speech_end 一次都不会触发，转写自然永远是空的。
# 正确做法是把一帧切成 512 样本的小块，逐块推理后取最大概率。
VAD_WINDOW_SAMPLES = {8000: 256, 16000: 512}

# ── 进程级 Silero 单例 ──
# 模型加载很慢（首次需 torch.hub 拉取并解包，实测约 15 秒）。
# 早期每个连接各加载一份，日志里会出现成串的
# 「Silero VAD model loaded (ONNX)」。模型本身无状态，可安全共享。
_silero_cache: dict = {}
_silero_lock = threading.Lock()


def _get_shared_silero():
    """取（或首次加载）进程级共享的 Silero VAD 模型。

    返回 (model, get_speech_timestamps)。
    """
    with _silero_lock:
        if "model" in _silero_cache:
            return _silero_cache["model"], _silero_cache["utils"]

        import torch

        logger.info("首次加载 Silero VAD 模型（ONNX）…")
        model, utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            onnx=True,
        )
        _silero_cache["model"] = model
        _silero_cache["utils"] = utils[0]
        logger.info("Silero VAD 模型已加载并缓存，后续连接直接复用")
        return model, utils[0]


class VADProcessor:
    """Silero VAD 流式处理器

    参数（均可通过环境变量覆盖）：
    - speech_threshold: 语音概率 > 此值判定为语音（默认 0.5）
    - silence_timeout: 连续静默多少秒触发 speech_end（默认 1.0s）
    - min_speech_duration: 最短语音段（默认 0.3s，短于此忽略）
    - max_speech_duration: 最长语音段（默认 30s，超过强制切分）
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        speech_threshold: float = 0.5,
        silence_timeout: float = 1.0,
        min_speech_duration: float = 0.3,
        max_speech_duration: float = 30.0,
        preroll_seconds: float = 0.3,
    ):
        self.sample_rate = sample_rate
        self.speech_threshold = speech_threshold
        self.silence_timeout = silence_timeout
        self.min_speech_duration = min_speech_duration
        self.max_speech_duration = max_speech_duration
        # 语音起点前保留的音频长度：VAD 需要几帧才能确认「开始说话」，
        # 不留前置缓冲会把第一个字吃掉（听感上就是「断头」）。
        self.preroll_seconds = max(0.0, preroll_seconds)

        # Silero VAD 模型（懒加载）
        self._model = None
        self._get_speech_timestamps = None

        # 状态机
        self._state: VADState = VADState.SILENCE
        self._speech_start_time: Optional[float] = None
        self._silence_start_time: Optional[float] = None
        self._current_time: float = 0.0

        # 正在累积的语音段音频
        self._buffer: list[np.ndarray] = []
        # 语音开始前的滑动窗口（只保留最近 preroll_seconds 的帧）
        self._preroll: list[np.ndarray] = []
        self._preroll_samples = int(self.preroll_seconds * sample_rate)

    # ── 懒加载模型 ──

    def _ensure_model(self):
        """确保 Silero VAD 模型可用（复用进程级共享实例）

        与 Whisper 同理：模型加载慢（首次还要 torch.hub 拉取），
        每个连接各加载一份会白白浪费十几秒与显存。
        VAD 模型本身是无状态的（状态机在 VADProcessor 实例上），
        因此可以安全共享。
        """
        if self._model is not None:
            return
        self._model, self._get_speech_timestamps = _get_shared_silero()

    # ── 核心：逐帧处理 ──

    def _speech_probability(self, audio_frame: np.ndarray) -> float:
        """算一帧的语音概率。

        Silero 只接受固定长度的输入（16kHz → 512 样本），因此把整帧切成
        若干 512 样本的窗口逐块推理，取**最大**概率：
        只要帧内有任意一段像语音，就认为这一帧在说话（宁可多检测，
        也不要漏掉说话，漏检会导致整句不转录）。

        尾部不足一个窗口的样本直接丢弃：它们会在下一帧里重新出现，
        不会造成信息丢失。
        """
        window = VAD_WINDOW_SAMPLES.get(self.sample_rate)
        if window is None:
            # 非常规采样率：不猜，直接按「非语音」处理并提示
            logger.warning("Silero VAD 不支持 %d Hz，语音检测已跳过", self.sample_rate)
            return 0.0

        try:
            import torch
        except ImportError:  # pragma: no cover
            return 0.0

        audio = np.asarray(audio_frame, dtype=np.float32).reshape(-1)
        if audio.size < window:
            return 0.0

        best = 0.0
        for start in range(0, audio.size - window + 1, window):
            chunk = audio[start:start + window]
            try:
                prob = float(
                    self._model(torch.from_numpy(chunk.copy()), self.sample_rate).item()
                )
            except Exception as exc:
                # 这里不再静默吞掉：早期版本把 ValueError 当成 prob=0，
                # 导致语音永远检测不到，且完全没有日志可查。
                logger.warning("Silero VAD 推理失败: %s", exc)
                return 0.0
            if prob > best:
                best = prob
                if best >= 0.99:
                    break
        return best

    def process_frame(
        self,
        audio_frame: np.ndarray,
        timestamp: Optional[float] = None,
    ) -> list[dict]:
        """
        处理一帧音频，返回触发的事件列表。

        Args:
            audio_frame: float32 numpy array, shape (n_samples,), 16kHz mono
            timestamp: 此帧对应的时间戳（秒），None 则自动推算

        Returns:
            list[dict]: 事件列表，每个事件格式:
                {"type": "speech_start", "ts": float}
                {"type": "speech_end", "ts": float}
        """
        self._ensure_model()

        # 更新时间
        frame_duration = len(audio_frame) / self.sample_rate
        if timestamp is not None:
            self._current_time = timestamp
        ts = self._current_time

        # VAD 检测：使用 Silero 模型判断当前帧是否为语音
        speech_prob = self._speech_probability(audio_frame)
        is_speech = speech_prob > self.speech_threshold

        # 累积 buffer 的策略决定了转录质量与速度：
        #
        # 早期实现把**每一帧**都塞进 buffer，静音也不例外。后果：
        #   - 用户说完一句话后，前面的几十秒静音也一起送去转录，
        #     Whisper 在静音上白跑（实测出现过 44s / 77s 的片段），
        #     既慢又容易产生与内容无关的幻觉文本；
        #   - 两次说话之间只要没触发断句，就会被并成一大段。
        #
        # 现在改为：
        #   - 静默状态：帧进**滑动窗口** _preroll，只保留最近
        #     preroll_seconds 秒（用于接住被 VAD 判定延迟的起头字）；
        #   - 一旦判定开始说话：把窗口里的帧作为前置缓冲并入 buffer，
        #     之后只累积说话期间的帧。
        self._append_frame(audio_frame, is_speech)

        events = []

        if self._state == VADState.SILENCE:
            if is_speech:
                # 静默 → 语音：记录开始时间，但并不立即触发 speech_start
                # 等积累到 min_speech_duration 后才正式触发
                self._state = VADState.SPEECH
                self._speech_start_time = ts
                self._silence_start_time = None
                self._promote_preroll()
        else:  # SPEECH
            # 注意：不能写 `self._speech_start_time or ts` —— 语音从第 0 秒
            # 就开始时，_speech_start_time 是 0.0（falsy），会被错误地替换成
            # ts，算出 speech_duration=0，从而走进「语音太短，忽略」分支，
            # 整段语音被丢弃且不报错。
            start = self._speech_start_time
            # 时长只算到「静默开始」为止：ts 在静默期间仍在推进，
            # 若用 ts 计算，一声 0.1 秒的咳嗽也会因为后面 1 秒静默
            # 被算成 1.1 秒，min_speech_duration 形同失效。
            end = self._silence_start_time if self._silence_start_time is not None else ts
            speech_duration = end - (start if start is not None else end)
            if not is_speech:
                # 可能开始静默
                if self._silence_start_time is None:
                    self._silence_start_time = ts
                silence_duration = ts - self._silence_start_time
                # 静默超时 → 触发 speech_end
                if silence_duration >= self.silence_timeout:
                    if speech_duration >= self.min_speech_duration:
                        events.append({"type": "speech_end", "ts": ts})
                        # 关键：保留 buffer，调用方要取走这段音频去转录
                        self._reset(keep_buffer=True)
                    else:
                        # 语音太短，忽略（这段音频没有价值，直接丢弃）
                        logger.debug(
                            "Speech too short (%.2fs), ignored", speech_duration
                        )
                        self._reset()
            else:
                # 仍在说话，清除静默计时
                self._silence_start_time = None

                # 强制切分：超过最大语音段长度
                if speech_duration >= self.max_speech_duration:
                    events.append({"type": "speech_end", "ts": ts, "forced": True})
                    # 立即开始新段
                    self._speech_start_time = ts + 0.1
                    events.append({"type": "speech_start", "ts": ts + 0.1})

        self._current_time += frame_duration
        return events

    def get_buffer_and_reset(self) -> np.ndarray:
        """获取累积的音频 buffer 并清空"""
        if not self._buffer:
            return np.array([], dtype=np.float32)
        audio = np.concatenate(self._buffer)
        self._buffer = []
        return audio

    def is_speech(self) -> bool:
        """当前是否在语音中"""
        return self._state == VADState.SPEECH

    @property
    def state(self) -> VADState:
        return self._state

    @property
    def speech_duration(self) -> float:
        """当前语音段已持续秒数"""
        if self._speech_start_time is None:
            return 0.0
        return self._current_time - self._speech_start_time

    # ── 内部 ──

    def _append_frame(self, frame: np.ndarray, is_speech: bool) -> None:
        """按当前状态决定这一帧进哪里。

        - 正在说话：进正式 buffer
        - 静默（包括「说话后等待断句」的那段静音，以及说话前）：进滑动窗口

        注意不能简单用 `state == SPEECH` 判断：断句要等 silence_timeout
        秒静默才触发，期间 state 仍是 SPEECH，若无条件写入，
        每段尾巴都会拖上 1 秒静音，长录音里累积起来很可观。
        """
        in_speech = is_speech and self._silence_start_time is None
        if in_speech:
            self._buffer.append(frame)
        else:
            self._preroll.append(frame)
            self._trim_preroll()

    def _trim_preroll(self) -> None:
        """把前置窗口裁剪到 preroll_seconds 以内"""
        if self._preroll_samples <= 0:
            self._preroll = []
            return

        total = sum(len(f) for f in self._preroll)
        while len(self._preroll) > 1 and total - len(self._preroll[0]) >= self._preroll_samples:
            total -= len(self._preroll.pop(0))

    def _promote_preroll(self) -> None:
        """开始说话时，把前置窗口的帧并入 buffer（接住起头字）"""
        if self._preroll:
            self._buffer.extend(self._preroll)
            self._preroll = []

    def _reset(self, *, keep_buffer: bool = False):
        """重置状态机。

        keep_buffer=True 时保留音频缓冲 —— 触发 speech_end 后必须保留，
        调用方要拿这段音频去转录（get_buffer_and_reset 会取走并清空）。
        早期实现无条件清空 buffer，导致 speech_end 之后取到的是空音频，
        转录结果永远是空的。
        """
        self._state = VADState.SILENCE
        self._speech_start_time = None
        self._silence_start_time = None
        # 前置窗口每次都清：新的一段语音应有自己的起头缓冲，
        # 留着上一段的尾巴会把两句话粘在一起。
        self._preroll = []
        if not keep_buffer:
            self._buffer = []
