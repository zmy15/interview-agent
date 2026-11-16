"""
`scripts/download_qwen_asr.py` 的轻量测试（不联网、不真的下载）。

脚本主体是调用 huggingface_hub 的薄封装，值得测的是「简写补全」与
「默认落到哪个目录」——这两处错了，用户会把权重下到意想不到的位置。
"""

import importlib.util
import os
import sys

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "download_qwen_asr.py",
)


def _load():
    spec = importlib.util.spec_from_file_location("download_qwen_asr", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


m = _load()


def test_alias_expansion():
    assert m.resolve_repo_id("1.7b") == "Qwen/Qwen3-ASR-1.7B"
    assert m.resolve_repo_id("0.6B") == "Qwen/Qwen3-ASR-0.6B"
    assert m.resolve_repo_id("aligner") == "Qwen/Qwen3-ForcedAligner-0.6B"


def test_repo_id_passthrough():
    assert m.resolve_repo_id("Qwen/Qwen3-ASR-1.7B") == "Qwen/Qwen3-ASR-1.7B"
    assert m.resolve_repo_id("some-org/custom-asr") == "some-org/custom-asr"


def test_empty_falls_back_to_default():
    assert m.resolve_repo_id("") == m.DEFAULT_MODEL
    assert m.resolve_repo_id(None) == m.DEFAULT_MODEL


def test_default_dest_uses_repo_name():
    dest = m.default_dest("Qwen/Qwen3-ASR-1.7B")
    assert dest == os.path.join(m.DEFAULT_DEST_ROOT, "Qwen3-ASR-1.7B")
    assert os.path.basename(m.DEFAULT_DEST_ROOT) == "models"


def test_human_size(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * (1024 * 1024 * 3))
    assert m.human_size(str(tmp_path)) == "3MB"


def test_dest_root_is_project_models_dir():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.normpath(m.DEFAULT_DEST_ROOT) == os.path.join(root, "models")
