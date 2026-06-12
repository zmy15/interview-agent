"""
Silero VAD 流式处理器
实时检测语音活动（speech/silence），输出语音段边界事件。
"""

import logging
from typing import Optional
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)


class VADState(Enum):
    SILENCE = "silence"
    SPEECH = "speech"


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
    ):
        self.sample_rate = sample_rate
        self.speech_threshold = speech_threshold
        self.silence_timeout = silence_timeout
        self.min_speech_duration = min_speech_duration
        self.max_speech_duration = max_speech_duration

        # Silero VAD 模型（懒加载）
        self._model = None
        self._get_speech_timestamps = None

        # 状态机
        self._state: VADState = VADState.SILENCE
        self._speech_start_time: Optional[float] = None
        self._silence_start_time: Optional[float] = None
        self._current_time: float = 0.0

        # 音频缓冲
        self._buffer: list[np.ndarray] = []

    # ── 懒加载模型 ──

    def _ensure_model(self):
        """确保 Silero VAD 模型已加载"""
        if self._model is not None:
            return
        try:
            import torch
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=True,
            )
            self._model = model
            self._get_speech_timestamps = utils[0]
            logger.info("Silero VAD model loaded (ONNX)")
        except Exception as e:
            logger.error("Failed to load Silero VAD: %s", e)
            raise

    # ── 核心：逐帧处理 ──

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

        # 累积 buffer
        self._buffer.append(audio_frame)

        # VAD 检测：使用 Silero 模型判断当前帧是否为语音
        try:
            import torch
            audio_tensor = torch.from_numpy(audio_frame).float()
            speech_prob = self._model(audio_tensor, self.sample_rate).item()
        except Exception:
            speech_prob = 0.0

        is_speech = speech_prob > self.speech_threshold
        events = []

        if self._state == VADState.SILENCE:
            if is_speech:
                # 静默 → 语音：记录开始时间，但并不立即触发 speech_start
                # 等积累到 min_speech_duration 后才正式触发
                self._state = VADState.SPEECH
                self._speech_start_time = ts
                self._silence_start_time = None
        else:  # SPEECH
            speech_duration = ts - (self._speech_start_time or ts)
            if not is_speech:
                # 可能开始静默
                if self._silence_start_time is None:
                    self._silence_start_time = ts
                silence_duration = ts - self._silence_start_time
                # 静默超时 → 触发 speech_end
                if silence_duration >= self.silence_timeout:
                    if speech_duration >= self.min_speech_duration:
                        events.append({"type": "speech_end", "ts": ts})
                    else:
                        # 语音太短，忽略
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

    def _reset(self):
        """重置状态机"""
        self._state = VADState.SILENCE
        self._speech_start_time = None
        self._silence_start_time = None
        self._buffer = []
