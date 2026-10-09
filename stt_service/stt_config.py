"""
STT 配置解析 — 把环境变量/`.env` 归一成 faster-whisper 需要的参数

单独成模块的原因：
    这些决策（用哪个设备、什么精度）会直接影响速度与稳定性，
    值得单独测试；放在 main.py 里会因为导入即启动 FastAPI 而难以覆盖。
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

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
    model: str
    device: str
    compute_type: str
    vad_silence_timeout: float

    def describe(self) -> str:
        return f"model={self.model} device={self.device} compute={self.compute_type}"


def load_config() -> STTConfig:
    """从环境变量读取配置（.env 由调用方先行加载）"""
    device = os.getenv("STT_DEVICE", "cpu").strip() or "cpu"
    model = os.getenv("STT_MODEL", "base").strip() or "base"
    compute = resolve_compute_type(device, os.getenv("STT_COMPUTE_TYPE", ""))

    try:
        silence = float(os.getenv("VAD_SILENCE_TIMEOUT", "1.0"))
    except ValueError:
        silence = 1.0

    cfg = STTConfig(
        model=model,
        device=device,
        compute_type=compute,
        vad_silence_timeout=silence,
    )
    logger.info("STT 配置: %s", cfg.describe())

    # 常见配置错误提前提示，避免用户对着「识别结果差」无从下手
    if device == "cuda":
        try:
            import torch

            if not torch.cuda.is_available():
                logger.warning(
                    "STT_DEVICE=cuda 但当前环境的 torch 检测不到 CUDA，"
                    "将回退到 CPU（速度会明显变慢）"
                )
        except ImportError:
            pass

    if model in ("tiny", "base") :
        logger.warning(
            "当前模型 %s 体积很小，中文识别准确率偏低；"
            "建议改用 large-v3-turbo（准确率接近 large-v3，速度快约 8 倍）",
            model,
        )

    return cfg