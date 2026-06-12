"""
流式转录器 — VAD 分段 → faster-whisper 异步转录
边说边出字：前一段 final 文本累积 + 当前段 partial 输出
"""

import asyncio
import logging
from typing import Callable, Optional

import numpy as np

from vad_processor import VADProcessor

logger = logging.getLogger(__name__)


class StreamingTranscriber:
    """流式转录器

    工作流程：
    1. 接收 PCM 音频帧 → 送入 VAD 检测语音边界
    2. VAD 检测到 speech_end → 取该段音频 → 异步调用 whisper 转录
    3. 转录结果通过回调输出：partial（累积文本）+ final（完整句）
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        sample_rate: int = 16000,
        silence_timeout: float = 1.0,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_vad: Optional[Callable[[str], None]] = None,
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.sample_rate = sample_rate

        # 回调
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_vad = on_vad

        # VAD 处理器
        self.vad = VADProcessor(
            sample_rate=sample_rate,
            silence_timeout=silence_timeout,
        )

        # Whisper 模型（懒加载）
        self._model = None

        # 累积的全部转录文本
        self._full_text: str = ""

        # 后台转录任务
        self._pending_tasks: list[asyncio.Task] = []

    # ── 懒加载 Whisper ──

    def _ensure_model(self):
        """确保 faster-whisper 模型已加载"""
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info(
                "Whisper model loaded: size=%s device=%s compute=%s",
                self.model_size,
                self.device,
                self.compute_type,
            )
        except Exception as e:
            logger.error("Failed to load Whisper model: %s", e)
            raise

    # ── 核心：逐帧处理 ──

    async def process_frame(self, audio_frame: np.ndarray) -> None:
        """
        处理一帧音频。

        Args:
            audio_frame: float32 numpy array, 16kHz mono
        """
        # 送入 VAD
        vad_events = self.vad.process_frame(audio_frame)

        for event in vad_events:
            etype = event["type"]
            ts = event.get("ts", 0.0)

            if etype == "speech_end":
                # 取该段音频 → 异步转录
                audio_segment = self.vad.get_buffer_and_reset()
                if len(audio_segment) > 0:
                    task = asyncio.create_task(
                        self._transcribe_segment(audio_segment, ts)
                    )
                    self._pending_tasks.append(task)

                if self.on_vad:
                    self.on_vad("speech_end")

    async def flush(self) -> Optional[str]:
        """
        强制转录当前 buffer（用于手动停止录音时）。
        返回最终完整文本。
        """
        audio_segment = self.vad.get_buffer_and_reset()
        if len(audio_segment) > 0:
            await self._transcribe_segment(audio_segment, final=True)

        # 等待所有后台任务
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
            self._pending_tasks.clear()

        return self._full_text.strip() if self._full_text else ""

    # ── 转录逻辑 ──

    async def _transcribe_segment(
        self, audio: np.ndarray, timestamp: float = 0.0, final: bool = False
    ):
        """异步转录一段音频"""
        self._ensure_model()

        try:
            # faster-whisper 需要 float32 输入
            audio_float32 = audio.astype(np.float32)

            segments, info = self._model.transcribe(
                audio_float32,
                language="zh",
                beam_size=5,
                vad_filter=False,
            )

            segment_texts = []
            for segment in segments:
                segment_texts.append(segment.text)
                # 输出 partial
                partial = self._full_text + "".join(segment_texts)
                if self.on_partial:
                    self.on_partial(partial)

            # 最终文本
            new_text = "".join(segment_texts)
            if new_text:
                self._full_text += new_text
                if final:
                    if self.on_final:
                        self.on_final(self._full_text.strip())

            logger.debug(
                "Transcribed segment: %.1fs audio → '%s' (lang=%s)",
                len(audio) / self.sample_rate,
                new_text[:80],
                info.language,
            )

        except Exception as e:
            logger.error("Transcription failed: %s", e)

    def reset(self):
        """重置会话（新录音开始前调用）"""
        self._full_text = ""
        self._pending_tasks.clear()
        self.vad._reset()
