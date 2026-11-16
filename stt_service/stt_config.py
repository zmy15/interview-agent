"""
STT 配置解析 — 把环境变量/`.env` 归一成推理后端需要的参数

单独成模块的原因：
    这些决策（用哪个设备、什么精度）会直接影响速度与稳定性，
    值得单独测试；放在 main.py 里会因为导入即启动 FastAPI 而难以覆盖。

支持两种后端（STT_BACKEND）：
    faster_whisper  CTranslate2 的 Whisper（历史默认，兼容旧配置）
    qwen3_asr       Qwen3-ASR（中文明显更准，见 asr_engine.py）
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

BACKEND_WHISPER = "faster_whisper"
BACKEND_QWEN = "qwen3_asr"
SUPPORTED_BACKENDS = (BACKEND_WHISPER, BACKEND_QWEN)

# 项目根目录（stt_service 的上一级）：用于把 .env 里的相对模型路径补全。
# 本服务可能是被主进程以别的工作目录拉起的，不能依赖 CWD。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Qwen3-ASR 的默认权重（HF repo id，也可填本地目录）
DEFAULT_QWEN_MODEL = "Qwen/Qwen3-ASR-0.6B"


def resolve_model_path(value: str) -> str:
    """把 .env 里的模型路径归一成"绝对路径"或"HF repo id"。

    规则（按顺序判断）：
      1. 绝对路径 → 原样
      2. 相对项目根目录能命中已有目录 → 补成绝对路径
      3. `org/name` 形式且本地不存在 → 当作 HF repo id，交给 transformers 下载
      4. 其余（如 `models/xxx`） → 按项目根目录补全

    为什么要区分 3 和 4：repo id 与相对路径长得一样（都含 "/"），
    只能靠"本地是否真的存在"来判断；不存在时按 repo id 处理才能让首次
    下载走通，同时打一条日志说明这不是笔误。
    """
    raw = (value or "").strip()
    if not raw:
        return DEFAULT_QWEN_MODEL
    if os.path.isabs(raw):
        return os.path.normpath(raw)

    candidate = os.path.normpath(os.path.join(_PROJECT_ROOT, raw.replace("\\", os.sep)))
    if os.path.isdir(candidate):
        return candidate

    parts = raw.replace("\\", "/").split("/")
    looks_like_repo_id = (
        len(parts) == 2
        and all(parts)
        and not raw.startswith(".")
        and not os.path.splitdrive(raw)[0]
    )
    if looks_like_repo_id:
        logger.info("STT_QWEN_MODEL=%s 本地不存在，按 HF repo id 处理", raw)
        return raw

    return candidate


# 各设备的默认精度
_DEVICE_COMPUTE = {
    "cuda": "float16",   # 半精度：速度与显存占用都最优
    "cpu": "int8",       # 量化：比 float32 快数倍且省内存
}


def resolve_compute_type(device: str, raw: str = "") -> str:
    """决定推理精度。

    留空（或 auto）时按设备选择，而不是交给 faster-whisper 的 auto：
        GPU → float16，CPU → int8

    为什么不用 faster-whisper 的 auto：
        它会在显存不足时**静默回退**到更慢的精度，表现为
        「GPU 跑得比预期慢很多」且日志里看不出原因。
        显式指定后行为可预测。
    """
    value = (raw or "").strip().lower()
    if value and value != "auto":
        return value

    resolved = _DEVICE_COMPUTE.get((device or "").strip().lower(), "int8")
    return resolved


@dataclass(frozen=True)
class STTConfig:
    """一次 STT 服务运行的配置"""
    backend: str
    model: str
    device: str
    compute_type: str
    # ── Qwen3-ASR 专有 ──
    qwen_model: str
    qwen_max_new_tokens: int
    # ── 识别语言：auto 时 Whisper 仍强制 zh（历史行为），Qwen 交给模型自判 ──
    language: str
    vad_silence_timeout: float
    # ── 分块参数（方案 C：VAD 断句与模型分块解耦）──
    chunk_max_seconds: float
    chunk_overlap_seconds: float
    chunk_context_chars: int

    @property
    def model_name(self) -> str:
        """当前后端实际使用的模型标识（/health 与日志用）"""
        return self.qwen_model if self.backend == BACKEND_QWEN else self.model

    def describe(self) -> str:
        return (
            f"backend={self.backend} model={self.model_name} device={self.device} "
            f"compute={self.compute_type} lang={self.language} "
            f"chunk<= {self.chunk_max_seconds}s overlap={self.chunk_overlap_seconds}s"
        )


def resolve_backend(raw: str) -> str:
    """把 STT_BACKEND 的各种写法归一成受支持的标识。

    留空时用 qwen3_asr：本项目的中文场景下它比 Whisper 更准，
    且 0.6B 的显存占用比 large-v3-turbo 还小。
    """
    value = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if value in ("", "qwen", "qwen3", "qwen_asr", "qwen3asr", BACKEND_QWEN):
        return BACKEND_QWEN
    if value in ("whisper", "fasterwhisper", BACKEND_WHISPER):
        return BACKEND_WHISPER
    logger.warning("未知的 STT_BACKEND=%r，回退 %s", raw, BACKEND_QWEN)
    return BACKEND_QWEN


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("%s 不是合法数字，回退默认值 %s", name, default)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        logger.warning("%s 不是合法整数，回退默认值 %s", name, default)
        return default


def load_config() -> STTConfig:
    """从环境变量读取配置（.env 由调用方先行加载）"""
    device = os.getenv("STT_DEVICE", "cpu").strip() or "cpu"
    backend = resolve_backend(os.getenv("STT_BACKEND", ""))
    model = os.getenv("STT_MODEL", "base").strip() or "base"
    compute = resolve_compute_type(device, os.getenv("STT_COMPUTE_TYPE", ""))
    language = os.getenv("STT_LANGUAGE", "auto").strip() or "auto"

    qwen_model = resolve_model_path(
        os.getenv("STT_QWEN_MODEL", DEFAULT_QWEN_MODEL) or DEFAULT_QWEN_MODEL
    )
    qwen_max_new_tokens = _env_int("STT_QWEN_MAX_NEW_TOKENS", 256)

    silence = _env_float("VAD_SILENCE_TIMEOUT", 1.0)

    # 分块上限（兜底）：语音连续不停时最多攒这么久。
    # 默认 25s：一段正常的中文长回答（自我介绍 2~3 分钟）中途总有换气，
    # 因此绝大多数块会在自然停顿处收，这个上限只在极连续语流时兜底。
    chunk_max = _env_float("STT_CHUNK_MAX_SECONDS", 25.0)
    # 硬切时的重叠：保证切点附近的字不被劈掉（配合文本层去重）
    chunk_overlap = _env_float("STT_CHUNK_OVERLAP_SECONDS", 0.5)
    # 跨块上下文长度（字符）：注入上一块尾部文本作为 prompt 补充
    chunk_ctx = _env_int("STT_CHUNK_CONTEXT_CHARS", 120)

    cfg = STTConfig(
        backend=backend,
        model=model,
        device=device,
        compute_type=compute,
        qwen_model=qwen_model,
        qwen_max_new_tokens=qwen_max_new_tokens,
        language=language,
        vad_silence_timeout=silence,
        chunk_max_seconds=chunk_max,
        chunk_overlap_seconds=chunk_overlap,
        chunk_context_chars=chunk_ctx,
    )
    logger.info("STT 配置: %s", cfg.describe())

    # 常见配置错误提前提示，避免用户对着「识别结果差」无从下手
    if device == "cuda" and backend == BACKEND_WHISPER:
        # 这里必须查 **CTranslate2** 的 CUDA，而不是 torch 的。
        #
        # 旧实现 import torch 后看 torch.cuda.is_available()，是错的：
        # Whisper 推理走的是 CTranslate2（faster-whisper），它自带
        # CUDA 运行库、与 torch 完全独立。两者结论经常不一致 ——
        # 没装 torch 时旧代码直接 ImportError 静默跳过（等于没检查），
        # 装了 CPU 版 torch 时又会误报「将回退到 CPU」，
        # 而实际上 CT2 好端端地跑在 GPU 上。
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() < 1:
                logger.warning(
                    "STT_DEVICE=cuda 但 CTranslate2 检测不到 CUDA 设备"
                    "（可能缺 cuBLAS/cuDNN），将回退到 CPU，速度会明显变慢"
                )
        except Exception as exc:  # 未安装或探测失败都不该影响启动
            logger.warning("无法探测 CTranslate2 的 CUDA 可用性: %s", exc)

    if backend == BACKEND_QWEN:
        # Qwen3-ASR 走 torch，和 Whisper 的 CT2 完全独立，必须单独探测
        try:
            import torch

            if not torch.cuda.is_available():
                logger.warning(
                    "STT_BACKEND=qwen3_asr 但 torch 检测不到 CUDA"
                    "（是否装成了 CPU 版？）。会回退 CPU 推理，速度明显变慢"
                )
        except ImportError:
            logger.warning("STT_BACKEND=qwen3_asr 但未安装 torch，模型无法加载")

        if model and model != "base" and not os.getenv("STT_QWEN_MODEL"):
            logger.info(
                "STT_MODEL=%s 属于 Whisper 后端，当前后端是 qwen3_asr，该值不生效",
                model,
            )

    if backend == BACKEND_WHISPER and model in ("tiny", "base"):
        logger.warning(
            "当前模型 %s 体积很小，中文识别准确率偏低；"
            "建议改用 large-v3-turbo（准确率接近 large-v3，速度快约 8 倍）",
            model,
        )

    return cfg
