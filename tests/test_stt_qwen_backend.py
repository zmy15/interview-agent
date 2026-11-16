"""
Qwen3-ASR 后端接入的单元测试

覆盖范围（**不加载真实权重、不联网**）：
  - STT_BACKEND / STT_QWEN_MODEL / STT_LANGUAGE 的解析与路径归一
  - StreamingTranscriber 的后端分派与 prompt 形态差异
  - asr_engine 的 whisper 兼容层：语言归一、返回结构、prompt 透传

真实推理（显存、精度、延迟）不在单测范围内，见 README「语音功能」。
"""

import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "stt_service"))

import stt_config  # noqa: E402
import streaming_transcriber as st  # noqa: E402
from stt_config import (  # noqa: E402
    BACKEND_QWEN,
    BACKEND_WHISPER,
    resolve_backend,
    resolve_model_path,
)


# ══════════════════════════════════════════════════════════════
# 配置解析
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("qwen3_asr", BACKEND_QWEN),
        ("qwen3-asr", BACKEND_QWEN),
        ("qwen3", BACKEND_QWEN),
        ("QWEN", BACKEND_QWEN),
        ("", BACKEND_QWEN),          # 默认走 Qwen
        ("faster_whisper", BACKEND_WHISPER),
        ("whisper", BACKEND_WHISPER),
        ("faster-whisper", BACKEND_WHISPER),
    ],
)
def test_resolve_backend(raw, expected):
    assert resolve_backend(raw) == expected


def test_resolve_backend_unknown_falls_back_to_qwen():
    """写错时回退到默认后端，而不是让服务起不来"""
    assert resolve_backend("whisper-large") == BACKEND_QWEN


def test_resolve_model_path_absolute_unchanged(tmp_path):
    target = str(tmp_path)
    assert resolve_model_path(target) == os.path.normpath(target)


def test_resolve_model_path_relative_uses_project_root(monkeypatch, tmp_path):
    """models/xxx 这类相对路径要按**项目根目录**解析，而不是 CWD"""
    local_dir = tmp_path / "models" / "Qwen3-ASR-0.6B"
    local_dir.mkdir(parents=True)
    monkeypatch.setattr(stt_config, "_PROJECT_ROOT", str(tmp_path))

    resolved = resolve_model_path("models/Qwen3-ASR-0.6B")

    assert resolved == str(local_dir)
    assert os.path.isabs(resolved)


def test_resolve_model_path_keeps_repo_id(monkeypatch, tmp_path):
    """本地不存在的 org/name 不能被当成相对路径拼到项目目录下"""
    monkeypatch.setattr(stt_config, "_PROJECT_ROOT", str(tmp_path))
    assert resolve_model_path("Qwen/Qwen3-ASR-0.6B") == "Qwen/Qwen3-ASR-0.6B"


def test_resolve_model_path_missing_dir_under_existing_parent(monkeypatch, tmp_path):
    """models/ 存在、子目录还没下载 → 仍按本地路径处理。

    回归：用户写 `models/Qwen3-ASR-1.7B` 却没下载时，旧逻辑按 repo id
    送去 hub，报「models/Qwen3-ASR-1.7B is not a valid model identifier」，
    既没下载也看不出怎么修。父目录存在就说明这是本地路径。
    """
    (tmp_path / "models").mkdir()
    monkeypatch.setattr(stt_config, "_PROJECT_ROOT", str(tmp_path))

    resolved = resolve_model_path("models/Qwen3-ASR-1.7B")

    assert resolved == os.path.join(str(tmp_path), "models", "Qwen3-ASR-1.7B")
    assert os.path.isabs(resolved)


def test_resolve_model_path_plain_name(monkeypatch, tmp_path):
    """单个目录名（无斜杠）一律按项目内相对路径处理"""
    monkeypatch.setattr(stt_config, "_PROJECT_ROOT", str(tmp_path))
    assert resolve_model_path("weights") == os.path.join(str(tmp_path), "weights")


def test_load_config_reads_qwen_settings(monkeypatch):
    monkeypatch.setenv("STT_BACKEND", "qwen3_asr")
    monkeypatch.setenv("STT_DEVICE", "cuda")
    monkeypatch.setenv("STT_QWEN_MODEL", "Qwen/Qwen3-ASR-1.7B")
    monkeypatch.setenv("STT_LANGUAGE", "zh")
    monkeypatch.setenv("STT_QWEN_MAX_NEW_TOKENS", "512")
    monkeypatch.setenv("STT_MODEL", "large-v3-turbo")

    cfg = stt_config.load_config()

    assert cfg.backend == BACKEND_QWEN
    assert cfg.qwen_model == "Qwen/Qwen3-ASR-1.7B"
    assert cfg.language == "zh"
    assert cfg.qwen_max_new_tokens == 512
    # model_name 应指向当前后端真正使用的权重
    assert cfg.model_name == "Qwen/Qwen3-ASR-1.7B"
    assert "backend=qwen3_asr" in cfg.describe()


def test_load_config_whisper_backend_keeps_model_name(monkeypatch):
    monkeypatch.setenv("STT_BACKEND", "faster_whisper")
    monkeypatch.setenv("STT_MODEL", "large-v3-turbo")
    monkeypatch.setenv("STT_DEVICE", "cpu")
    cfg = stt_config.load_config()
    assert cfg.backend == BACKEND_WHISPER
    assert cfg.model_name == "large-v3-turbo"


# ══════════════════════════════════════════════════════════════
# 转录器：后端分派与 prompt 形态
# ══════════════════════════════════════════════════════════════


def _make_transcriber(**kwargs):
    tr = st.StreamingTranscriber(sample_rate=16000, silence_timeout=1.0, **kwargs)
    tr._ensure_model = lambda: None
    return tr


def test_ensure_model_dispatches_to_qwen(monkeypatch):
    """qwen 后端必须走 get_shared_qwen，而不是继续加载 Whisper"""
    calls = {}

    def fake_qwen(model_path, device, compute_type, max_new_tokens=256):
        calls["qwen"] = (model_path, device, compute_type, max_new_tokens)
        return "QWEN"

    def fake_whisper(*a, **kw):
        calls["whisper"] = a
        return "WHISPER"

    monkeypatch.setattr(st, "get_shared_qwen", fake_qwen)
    monkeypatch.setattr(st, "get_shared_whisper", fake_whisper)

    tr = st.StreamingTranscriber(
        sample_rate=16000,
        silence_timeout=1.0,
        backend=BACKEND_QWEN,
        qwen_model="Qwen/Qwen3-ASR-0.6B",
        qwen_max_new_tokens=128,
    )
    tr._ensure_model()

    assert tr._model == "QWEN"
    assert calls["qwen"] == ("Qwen/Qwen3-ASR-0.6B", "cpu", "int8", 128)
    assert "whisper" not in calls


def test_ensure_model_dispatches_to_whisper(monkeypatch):
    calls = {}

    def fake_whisper(*a, **kw):
        calls["whisper"] = a
        return "WHISPER"

    monkeypatch.setattr(st, "get_shared_whisper", fake_whisper)
    tr = st.StreamingTranscriber(
        sample_rate=16000, silence_timeout=1.0,
        backend=BACKEND_WHISPER, model_size="base",
    )
    tr._ensure_model()

    assert tr._model == "WHISPER"
    assert calls["whisper"] == ("base", "cpu", "int8")


def test_build_prompt_qwen_is_context_only():
    """Qwen 的 prompt 是"上下文/热词"，不能混入 Whisper 的标点指令句"""
    tr = _make_transcriber(backend=BACKEND_QWEN, chunk_context_chars=10)
    tr._context_tail = "这是一段很长的前文内容ABCDE"

    prompt = tr._build_prompt()

    assert prompt == "的前文内容ABCDE"       # 只保留最后 10 个字符
    assert "标点" not in prompt
    assert tr.INITIAL_PROMPT not in prompt
    # 明确传入空上下文时不应回落到 _context_tail
    assert tr._build_prompt("") == ""


def test_build_prompt_whisper_keeps_instruction():
    tr = _make_transcriber(backend=BACKEND_WHISPER, chunk_context_chars=10)
    prompt = tr._build_prompt("上一句")
    assert prompt.startswith(tr.INITIAL_PROMPT)
    assert prompt.endswith("上一句")


def test_language_resolution():
    qwen_auto = _make_transcriber(backend=BACKEND_QWEN, language="auto")
    assert qwen_auto._language_for_model() is None      # 交给模型自判

    whisper_auto = _make_transcriber(backend=BACKEND_WHISPER, language="auto")
    assert whisper_auto._language_for_model() == "zh"   # 保持历史行为

    forced = _make_transcriber(backend=BACKEND_QWEN, language="zh")
    assert forced._language_for_model() == "zh"


# ══════════════════════════════════════════════════════════════
# asr_engine：whisper 兼容层
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Chinese", "zh"),
        ("chinese", "zh"),
        ("English", "en"),
        ("Cantonese", "yue"),
        (None, "zh"),
        ("zh", "zh"),
    ],
)
def test_normalize_language(raw, expected):
    from asr_engine import normalize_language

    assert normalize_language(raw) == expected


@pytest.mark.parametrize(
    "code,expected",
    [
        ("zh", "Chinese"),
        ("en", "English"),
        ("yue", "Cantonese"),
        ("auto", None),      # 交给模型自判
        (None, None),
        ("xx", None),        # 不认识的码不硬塞给模型
    ],
)
def test_to_model_language(code, expected):
    from asr_engine import to_model_language

    assert to_model_language(code) == expected


def test_qwen_transcribe_returns_whisper_compatible_result():
    """转写结果要能被 _transcribe_segment 无改动地消费：
    返回 (segments, info)，segment 有 .text，info 有 .language。"""
    from asr_engine import Qwen3AsrModel

    class _Result:
        language = "Chinese"
        text = "你好，世界。"

    class _FakeQwen:
        def __init__(self):
            self.calls = []

        def transcribe(self, audio, language=None):
            self.calls.append((len(audio[0]), audio[1], language))
            return [_Result()]

    obj = object.__new__(Qwen3AsrModel)
    obj._model = _FakeQwen()
    obj.device = "cpu"
    obj.dtype = "float32"
    obj.max_new_tokens = 256
    import threading

    obj._lock = threading.Lock()

    segments, info = obj.transcribe([0.0] * 16000, language="zh")

    assert [s.text for s in segments] == ["你好，世界。"]
    assert info.language == "zh"
    # 采样率与语种名要按 qwen-asr 的约定传进去
    assert obj._model.calls == [(16000, 16000, "Chinese")]


def test_qwen_transcribe_empty_audio():
    from asr_engine import Qwen3AsrModel

    obj = object.__new__(Qwen3AsrModel)
    obj._model = None
    obj.device = "cpu"
    obj.dtype = "float32"
    obj.max_new_tokens = 256
    import threading

    obj._lock = threading.Lock()

    segments, info = obj.transcribe([], language="zh")
    assert segments == []
    assert info.language == "zh"
