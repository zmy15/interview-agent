"""
`scripts/detect_stt_env.py` 的单元测试。

它决定「首次启动时复制出来的 .env 用哪个 STT 后端」：有可用 NVIDIA 显卡
走 Qwen3-ASR，否则退回 Whisper + CPU。判错的代价很直接 —— 没有独显却选
了 Qwen3-ASR，用户会觉得语音识别卡死（一句十几秒）。

这里不真的调用 nvidia-smi：解析与判定都是纯函数，喂字符串即可。
"""

import importlib.util
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT = os.path.join(_ROOT, "scripts", "detect_stt_env.py")


def _load():
    spec = importlib.util.spec_from_file_location("detect_stt_env", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # 必须先登记到 sys.modules：@dataclass 在解析注解时会回查
    # sys.modules[cls.__module__]，没登记会 AttributeError: 'NoneType'
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


d = _load()


# ══════════════════════════════════════════════════════════════
# 解析 nvidia-smi 输出
# ══════════════════════════════════════════════════════════════


def test_parse_gpus_real_output():
    out = "NVIDIA GeForce RTX 4060 Laptop GPU, 8188, 610.74\n"
    gpus = d.parse_gpus(out)
    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA GeForce RTX 4060 Laptop GPU"
    assert gpus[0].memory_mb == 8188
    assert gpus[0].driver == "610.74"


def test_parse_gpus_multiple_and_blank_lines():
    out = (
        "NVIDIA GeForce RTX 3090, 24576, 550.54\n"
        "\n"
        "NVIDIA GeForce GTX 1050, 2048, 536.23\n"
    )
    gpus = d.parse_gpus(out)
    assert [g.memory_mb for g in gpus] == [24576, 2048]


def test_parse_gpus_ignores_malformed():
    out = "garbage line\nNVIDIA X, not-a-number, 550.1\nNVIDIA Y, 8192, 550.1\n"
    gpus = d.parse_gpus(out)
    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA Y"


# ══════════════════════════════════════════════════════════════
# 判定
# ══════════════════════════════════════════════════════════════


def test_no_gpu_falls_back_to_whisper():
    dec = d.decide([])
    assert dec.backend == "faster_whisper"
    assert dec.device == "cpu"
    assert dec.whisper_model == "small"


def test_8gb_gpu_uses_qwen():
    dec = d.decide([d.GpuInfo("RTX 4060", 8188, "610.74")])
    assert dec.backend == "qwen3_asr"
    assert dec.device == "cuda"


def test_small_gpu_falls_back_to_whisper():
    """4GB 卡能加载 0.6B，但桌面合成一挤就 OOM，不作为默认方案"""
    dec = d.decide([d.GpuInfo("GTX 1650", 4096, "560.1")])
    assert dec.backend == "faster_whisper"
    assert "显存" in dec.reason


def test_old_driver_falls_back_to_whisper():
    """CUDA 12 需要 525+ 驱动；更早的驱动装了 torch cu126 也跑不起来"""
    dec = d.decide([d.GpuInfo("RTX 2080", 8192, "470.86")])
    assert dec.backend == "faster_whisper"
    assert "驱动" in dec.reason


def test_picks_gpu_with_most_memory():
    gpus = [
        d.GpuInfo("GTX 1050", 2048, "536.23"),
        d.GpuInfo("RTX 4090", 24564, "550.54"),
    ]
    dec = d.decide(gpus)
    assert dec.backend == "qwen3_asr"
    assert dec.gpu == "RTX 4090"


@pytest.mark.parametrize("driver,ok", [("525.0", True), ("524.99", False), ("610.74", True), ("", False)])
def test_driver_threshold(driver, ok):
    assert d._meets_driver(driver) is ok


# ══════════════════════════════════════════════════════════════
# 写回 .env
# ══════════════════════════════════════════════════════════════

_TEMPLATE = """# STT 语音识别
STT_ENABLED=false
STT_BACKEND=qwen3_asr
# Qwen3-ASR 权重：repo id 或本地目录
STT_QWEN_MODEL=Qwen/Qwen3-ASR-0.6B
STT_LANGUAGE=auto
STT_MODEL=base
STT_DEVICE=cpu
STT_COMPUTE_TYPE=int8
"""


def _write(tmp_path, text, newline="\n"):
    path = tmp_path / ".env"
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(text)
    return str(path)


def test_patch_env_cpu_decision(tmp_path):
    path = _write(tmp_path, _TEMPLATE)
    dec = d.decide([])

    assert d.patch_env(path, dec) is True

    text = open(path, encoding="utf-8").read()
    assert "STT_BACKEND=faster_whisper" in text
    assert "STT_DEVICE=cpu" in text
    assert "STT_MODEL=small" in text
    # 其余配置与注释必须原样保留
    assert "STT_QWEN_MODEL=Qwen/Qwen3-ASR-0.6B" in text
    assert "# Qwen3-ASR 权重：repo id 或本地目录" in text
    assert "STT_ENABLED=false" in text


def test_patch_env_gpu_decision(tmp_path):
    path = _write(tmp_path, _TEMPLATE)
    dec = d.decide([d.GpuInfo("RTX 4060", 8188, "610.74")])

    d.patch_env(path, dec)

    text = open(path, encoding="utf-8").read()
    assert "STT_BACKEND=qwen3_asr" in text
    assert "STT_DEVICE=cuda" in text
    # 选 Qwen 时不该动 Whisper 的模型配置（它在 Qwen 后端下无效）
    assert "STT_MODEL=base" in text


def test_patch_env_keeps_crlf(tmp_path):
    """Windows 上 .env 通常是 CRLF，改写后不能把整个文件变成 LF"""
    path = _write(tmp_path, _TEMPLATE.replace("\n", "\r\n"), newline="")

    d.patch_env(path, d.decide([]))

    with open(path, "rb") as fh:
        raw = fh.read()
    assert b"\r\n" in raw
    assert raw.count(b"\n") == raw.count(b"\r\n"), "混入了只有 LF 的行"


def test_patch_env_appends_missing_keys(tmp_path):
    path = _write(tmp_path, "STT_ENABLED=false\n")
    d.patch_env(path, d.decide([]))

    text = open(path, encoding="utf-8").read()
    assert "STT_BACKEND=faster_whisper" in text
    assert "STT_DEVICE=cpu" in text
    assert "STT_MODEL=small" in text


def test_patch_env_missing_file_is_not_fatal(tmp_path):
    """探测失败/文件不可写都不应阻断启动"""
    assert d.patch_env(str(tmp_path / "nope.env"), d.decide([])) is False
