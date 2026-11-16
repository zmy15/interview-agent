"""
Qwen3-ASR 推理后端（基于官方 `qwen-asr` 包）

对上层暴露与 faster-whisper 完全一致的接口：

    segments, info = model.transcribe(audio, language=..., initial_prompt=...)

其中 `segments` 是带 `.text` 的对象列表、`info` 带 `.language`。
这样 streaming_transcriber 与 /transcribe 路由都不需要为换模型写分支，
faster-whisper 与 Qwen3-ASR 可以按环境变量互换。

为什么用 `qwen-asr` 包，而不是直接调 transformers
--------------------------------------------------
官方包的 `transformers==4.57.6` 里**并没有** Qwen3ASR 模型类，
权重用的是 `thinker.` 前缀（Qwen-Omni 系），必须由包内自带的实现加载；
换用别的 transformers 版本（如主环境的 5.x）会整份权重对不上号
（实测全部 key 都是 UNEXPECTED，等于随机初始化），所以：
  - 依赖必须装进独立虚拟环境（.venv-stt），不能污染主环境；
  - 走 `qwen_asr.Qwen3ASRModel`，不要自己拼 processor。

与 Whisper 的行为差异（上层需要知道的三点）
------------------------------------------
1. **自带标点、默认简体**：不需要 `initial_prompt` 去唤标点，
   也不需要繁转简。
2. **prompt 的语义不同**：Whisper 的 `initial_prompt` 是"续写提示"，
   而 Qwen3-ASR 的 prompt 是"上下文/热词"（system message）。
   因此上层对 Qwen 后端只应传上一块的真实文本，不要传指令句。
3. **语言可自动识别**：`language=None` 时模型自行判定并输出语种标签，
   中英混说场景比强制 zh 更稳。
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# 模型固定按 16kHz 单声道推理
SAMPLE_RATE = 16000

# 两位语言码 → Qwen3-ASR 接受的语种名（模型卡里用的是全名）
_LANGUAGE_NAMES = {
    "zh": "Chinese",
    "en": "English",
    "yue": "Cantonese",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "ru": "Russian",
    "pt": "Portuguese",
    "it": "Italian",
    "th": "Thai",
    "vi": "Vietnamese",
    "ar": "Arabic",
    "tr": "Turkish",
    "hi": "Hindi",
    "ms": "Malay",
    "id": "Indonesian",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "pl": "Polish",
    "cs": "Czech",
    "fil": "Filipino",
    "fa": "Persian",
    "el": "Greek",
    "hu": "Hungarian",
    "mk": "Macedonian",
    "ro": "Romanian",
}

# 模型输出里的语种名 → 两位码（与原 whisper 路径的返回值对齐）
_LANGUAGE_CODES = {name.lower(): code for code, name in _LANGUAGE_NAMES.items()}


class _Segment:
    """与 faster-whisper 的 Segment 对齐（只用到 text）"""

    __slots__ = ("text", "start", "end")

    def __init__(self, text: str):
        self.text = text
        self.start = 0.0
        self.end = 0.0

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"_Segment(text={self.text!r})"


class _Info:
    """与 faster-whisper 的 TranscriptionInfo 对齐（只用到 language）"""

    __slots__ = ("language", "language_probability")

    def __init__(self, language: Optional[str]):
        self.language = language or "zh"
        self.language_probability = 1.0


def normalize_language(tag: Optional[str], fallback: Optional[str] = None) -> str:
    """把 'Chinese' / 'zh' / 'ZH' 统一成两位码。"""
    if not tag:
        return (fallback or "zh").lower()[:2] or "zh"
    key = str(tag).strip().lower()
    if key in _LANGUAGE_CODES:
        return _LANGUAGE_CODES[key]
    if key in _LANGUAGE_NAMES:
        return key
    return key[:2] or (fallback or "zh").lower()[:2] or "zh"


def to_model_language(code: Optional[str]) -> Optional[str]:
    """两位码 → 模型接受的语种名；None/auto 原样返回（交给模型自判）。"""
    if not code:
        return None
    key = str(code).strip().lower()
    if key in ("", "auto"):
        return None
    return _LANGUAGE_NAMES.get(key, None)


def cuda_available() -> bool:
    """探测 torch 的 CUDA 可用性（只用于日志/告警，不抛异常）"""
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # pragma: no cover - 未安装 torch
        return False


class Qwen3AsrModel:
    """Qwen3-ASR 的 whisper 兼容封装。

    线程安全：同一模型实例并发 generate 并不安全（KV cache 与显存峰值
    都会出问题），这里用一把锁把推理串行化。GPU 上一段 10s 音频约 1s，
    串行带来的排队远小于重新加载模型。
    """

    def __init__(
        self,
        model_path: str,
        device: str = "cuda",
        compute_type: str = "float16",
        max_new_tokens: int = 256,
    ):
        import torch
        from qwen_asr import Qwen3ASRModel as _Qwen3ASRModel

        self._torch = torch
        self.model_path = model_path
        self.max_new_tokens = max(32, int(max_new_tokens))

        # 本地目录不存在时，直接给出可操作的提示。
        # 否则 transformers 会把这串路径当成 repo id 去 hub 上找，报
        # 「models/Qwen3-ASR-1.7B is not a valid model identifier」——
        # 既没下载，也看不出下一步该干什么。
        if os.path.isabs(model_path) and not os.path.isdir(model_path):
            raise FileNotFoundError(
                f"Qwen3-ASR 权重目录不存在: {model_path}\n"
                "  二选一：\n"
                "    a) 想让它自动下载 —— 把 .env 的 STT_QWEN_MODEL 改成 repo id，"
                "例如 Qwen/Qwen3-ASR-1.7B（首次启动会下载）；\n"
                "    b) 想用本地目录 —— 先执行 "
                "python scripts/download_qwen_asr.py --model Qwen/Qwen3-ASR-1.7B"
            )

        if device == "cuda" and not torch.cuda.is_available():
            logger.warning(
                "STT_DEVICE=cuda 但 torch 检测不到 CUDA（是否装成了 CPU 版？），"
                "Qwen3-ASR 将回退到 CPU，速度会明显变慢"
            )
            self.device = "cpu"
        else:
            self.device = "cuda:0" if device == "cuda" else "cpu"

        # CPU 上用 float32：fp16 在 CPU 上缺算子，会退化成极慢的模拟实现
        self.dtype = torch.float32 if self.device == "cpu" else torch.float16

        logger.info(
            "加载 Qwen3-ASR（path=%s device=%s dtype=%s）…",
            model_path, self.device, self.dtype,
        )
        if self.device != "cpu":
            try:
                free, total = torch.cuda.mem_get_info()
                logger.info(
                    "显存：可用 %.1fGB / 共 %.1fGB（0.6B 约需 1.8GB，1.7B 约需 4.3GB）",
                    free / 2**30, total / 2**30,
                )
            except Exception:  # pragma: no cover - 老驱动/受限环境拿不到
                pass

        try:
            self._model = _Qwen3ASRModel.from_pretrained(
                model_path,
                dtype=self.dtype,
                device_map=self.device,
                max_new_tokens=self.max_new_tokens,
            )
        except Exception as exc:
            # 8GB 显卡上 1.7B 很容易在开了浏览器/壁纸引擎时 OOM，
            # 原始报错只有一行 "CUDA out of memory"，看不出该换模型
            if "out of memory" in str(exc).lower():
                raise RuntimeError(
                    f"加载 Qwen3-ASR 显存不足（{model_path}）。\n"
                    "  1.7B 约需 4.3GB 空闲显存，8GB 卡同时开着浏览器/壁纸引擎时很容易不够；\n"
                    "  处理方式：换回 0.6B（STT_QWEN_MODEL=models/Qwen3-ASR-0.6B，约 1.8GB），"
                    "或关掉占用显存的程序后重试。"
                ) from exc
            raise
        self._lock = threading.Lock()
        logger.info("Qwen3-ASR 加载完成")

    # ── 对外接口：与 faster-whisper 一致 ──

    def transcribe(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
        beam_size: Optional[int] = None,
        vad_filter: Optional[bool] = None,
        initial_prompt: Optional[str] = None,
        condition_on_previous_text: Optional[bool] = None,
        **kwargs: Any,
    ):
        """转录一段 16kHz 单声道 float32 音频。

        参数里 beam_size / vad_filter / condition_on_previous_text 是为了
        兼容 faster-whisper 的调用点而保留的，Qwen3-ASR 不使用（贪婪解码），
        显式忽略比让调用方写分支更省事。
        """
        del beam_size, vad_filter, condition_on_previous_text, kwargs

        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return [], _Info(language)

        model_language = to_model_language(language)

        with self._lock:
            results = self._model.transcribe(
                audio=(audio, SAMPLE_RATE),
                language=model_language,
            )

        first = results[0] if results else None
        text = (getattr(first, "text", "") or "").strip()
        lang = normalize_language(getattr(first, "language", None), fallback=language)

        return ([_Segment(text)] if text else []), _Info(lang)

    def describe(self) -> str:
        return f"qwen3_asr:{self.model_path}@{self.device}/{self.dtype}"
