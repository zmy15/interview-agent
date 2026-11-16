#!/usr/bin/env python3
"""把 Qwen3-ASR 权重下载到 `models/<名字>`，供 `STT_QWEN_MODEL` 指向本地目录。

为什么需要这个脚本
------------------
`STT_QWEN_MODEL` 指向**本地目录**时，服务不会自动下载 —— 本地就是本地。
想用 1.7B（比 0.6B 准，约 4GB）又不想让服务每次启动都跟 hub 打交道，
就先跑这个脚本把权重落到 `models/` 下，再把 `.env` 指向该目录。

对比：把 `STT_QWEN_MODEL` 直接写成 repo id（如 `Qwen/Qwen3-ASR-1.7B`）
也可以，服务首次启动时会自动下载到 HF 缓存 —— 但那样权重散在
`~/.cache/huggingface/hub` 里，备份/迁移时容易漏。

用法
----
    python scripts/download_qwen_asr.py                 # 0.6B（默认）
    python scripts/download_qwen_asr.py --model 1.7b    # 简写
    python scripts/download_qwen_asr.py --model Qwen/Qwen3-ASR-1.7B
    python scripts/download_qwen_asr.py --model Qwen/Qwen3-ASR-1.7B --dest models/asr-1.7b

国内默认走 hf-mirror（与 stt_service/main.py 一致），可用 HF_ENDPOINT 覆盖。
"""

from __future__ import annotations

import argparse
import os
import sys

# repo id 简写 → 完整 id
ALIASES = {
    "0.6b": "Qwen/Qwen3-ASR-0.6B",
    "1.7b": "Qwen/Qwen3-ASR-1.7B",
    "aligner": "Qwen/Qwen3-ForcedAligner-0.6B",
}

DEFAULT_MODEL = "Qwen/Qwen3-ASR-0.6B"
# 必须和项目根保持一致（scripts/ 的上一级）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DEST_ROOT = os.path.join(_PROJECT_ROOT, "models")


def resolve_repo_id(value: str) -> str:
    """把 `1.7b` 这类简写补全成完整 repo id；原样返回 `org/name`。"""
    raw = (value or "").strip()
    if not raw:
        return DEFAULT_MODEL
    return ALIASES.get(raw.lower(), raw)


def default_dest(repo_id: str) -> str:
    """默认落到 `models/<repo 名>`，例如 models/Qwen3-ASR-1.7B。"""
    name = repo_id.rstrip("/").split("/")[-1]
    return os.path.join(DEFAULT_DEST_ROOT, name)


def human_size(path: str) -> str:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return f"{total / (1024 ** 3):.2f}GB" if total >= 1024 ** 3 else f"{total / (1024 ** 2):.0f}MB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载 Qwen3-ASR 权重到本地目录")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"repo id 或简写（0.6b / 1.7b / aligner），默认 {DEFAULT_MODEL}",
    )
    parser.add_argument("--dest", default=None, help="目标目录，默认 models/<repo 名>")
    parser.add_argument(
        "--source",
        choices=("hf", "modelscope"),
        default="hf",
        help="hf=HuggingFace（默认走镜像）；modelscope=国内通常更快，但需要 pip install modelscope",
    )
    args = parser.parse_args(argv)

    repo_id = resolve_repo_id(args.model)
    dest = os.path.abspath(args.dest or default_dest(repo_id))

    print(f"[下载] {repo_id}")
    print(f"[下载] 目标目录: {dest}")

    if args.source == "modelscope":
        try:
            from modelscope import snapshot_download  # type: ignore
        except ImportError:
            print(
                "[错误] 未安装 modelscope。先执行：pip install modelscope",
                file=sys.stderr,
            )
            return 2
        snapshot_download(repo_id, local_dir=dest)
    else:
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        # 新版 hub 默认走 Xet 存储后端，国内会卡在 0 字节（详见 stt_service/main.py）
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            print(
                "[错误] 未安装 huggingface_hub。先执行：pip install huggingface_hub",
                file=sys.stderr,
            )
            return 2
        print(f"[下载] 使用 HF_ENDPOINT={os.environ['HF_ENDPOINT']}")
        snapshot_download(
            repo_id=repo_id,
            local_dir=dest,
            allow_patterns=[
                "*.json",
                "*.txt",
                "*.safetensors",
                "*.model",
                "*.jinja",
            ],
        )

    print(f"[完成] {human_size(dest)} → {dest}")
    print("[提示] 在 .env 里设置：")
    try:
        rel = os.path.relpath(dest, _PROJECT_ROOT).replace(os.sep, "/")
        print(f"        STT_QWEN_MODEL={rel}")
    except ValueError:  # 跨盘符时 relpath 会抛错，直接给绝对路径
        print(f"        STT_QWEN_MODEL={dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
