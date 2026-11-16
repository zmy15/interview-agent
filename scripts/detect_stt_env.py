#!/usr/bin/env python3
"""按本机环境决定 STT 后端，并把结果写回 `.env`。

背景
----
首次启动时 `start.ps1` / `start_app.ps1` / `start.sh` 会把 `.env.example`
复制成 `.env`，但模板里的默认值对**所有**机器都一样。而两个后端对硬件的
要求完全不同：

    qwen3_asr       需要一块像样的 NVIDIA 显卡（0.6B 约占 1.8GB 显存）
    faster_whisper  纯 CPU 就能跑（int8），只是精度差一些

没有独显的机器如果沿用模板默认的 qwen3_asr，一句 6 秒的话要十几秒，
表现为「语音识别卡死」。所以在「刚复制完 .env」这个时点探测一次硬件，
按结果改写三行配置：

    有可用 GPU → STT_BACKEND=qwen3_asr, STT_DEVICE=cuda
    否则       → STT_BACKEND=faster_whisper, STT_DEVICE=cpu, STT_MODEL=small

判定刻意保守（宁可退回 Whisper，也不要让首启体验崩掉）：
显存 >= 6GB 且驱动 >= 525（CUDA 12 的最低要求；cu126 轮子靠 minor
version compatibility 在 525+ 驱动上也能跑）。

只改上述三行，注释、API Key 等其余内容原样保留。也可以手动单独跑：

    python scripts/detect_stt_env.py              # 只打印判定结果
    python scripts/detect_stt_env.py --patch .env # 顺便写回 .env
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from typing import Optional

# Qwen3-ASR-0.6B 权重约 1.8GB，还要留给 KV cache / 桌面合成；
# 4GB 卡（如 GTX 1650）能加载但很容易 OOM，因此门槛定在 6GB。
MIN_VRAM_MB = 6000
# CUDA 12 的最低驱动版本（minor version compatibility）
MIN_DRIVER = (525, 0)

# nvidia-smi 不一定在 PATH 里（尤其是精简安装的驱动）
_NVSMI_CANDIDATES = (
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    r"C:\Windows\System32\nvidia-smi.exe",
)

_PATCH_KEYS = ("STT_BACKEND", "STT_DEVICE", "STT_MODEL")


@dataclass(frozen=True)
class GpuInfo:
    name: str
    memory_mb: int
    driver: str


@dataclass(frozen=True)
class Decision:
    backend: str
    device: str
    whisper_model: str
    reason: str
    gpu: Optional[str] = None
    vram_mb: int = 0
    driver: str = ""

    def describe(self) -> str:
        if self.backend == "qwen3_asr":
            return (
                f"检测到 {self.gpu}（{self.vram_mb}MB，驱动 {self.driver}）"
                f"→ 使用 Qwen3-ASR（GPU）"
            )
        return f"{self.reason} → 使用 faster-whisper（CPU，模型 {self.whisper_model}）"


def find_nvidia_smi() -> Optional[str]:
    """定位 nvidia-smi；找不到说明大概率没有 NVIDIA 驱动。"""
    exe = shutil.which("nvidia-smi")
    if exe:
        return exe
    for path in _NVSMI_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def parse_gpus(stdout: str) -> list[GpuInfo]:
    """解析 `--query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits`。

    输出形如：NVIDIA GeForce RTX 4060 Laptop GPU, 8188, 610.74
    显卡名里可能带逗号（少见），因此只按**最后两个**逗号切分。
    """
    gpus: list[GpuInfo] = []
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        driver = parts[-1]
        memory_raw = parts[-2]
        name = ", ".join(parts[:-2])
        try:
            memory_mb = int(float(memory_raw))
        except ValueError:
            continue
        gpus.append(GpuInfo(name=name, memory_mb=memory_mb, driver=driver))
    return gpus


def query_gpus(exe: str, timeout: float = 10.0) -> list[GpuInfo]:
    """调用 nvidia-smi；任何失败都返回空列表（缺驱动/驱动坏了/超时）。"""
    try:
        proc = subprocess.run(
            [
                exe,
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return parse_gpus(proc.stdout)


def _driver_tuple(driver: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in driver.split("."))
    except (ValueError, AttributeError):
        return (0,)


def _meets_driver(driver: str) -> bool:
    got = _driver_tuple(driver)
    # 补齐长度再比较，避免 "610" 与 (525, 0) 维度不一致
    size = max(len(got), len(MIN_DRIVER))
    padded = got + (0,) * (size - len(got))
    want = MIN_DRIVER + (0,) * (size - len(MIN_DRIVER))
    return padded >= want


def decide(gpus: list[GpuInfo]) -> Decision:
    """根据显卡信息给出后端方案（纯函数，便于测试）。"""
    if not gpus:
        return Decision(
            backend="faster_whisper",
            device="cpu",
            whisper_model="small",
            reason="未检测到 NVIDIA 显卡",
        )

    best = max(gpus, key=lambda g: g.memory_mb)
    if best.memory_mb < MIN_VRAM_MB:
        return Decision(
            backend="faster_whisper",
            device="cpu",
            whisper_model="small",
            reason=f"显存仅 {best.memory_mb}MB（Qwen3-ASR 建议 ≥{MIN_VRAM_MB}MB）",
            gpu=best.name,
            vram_mb=best.memory_mb,
            driver=best.driver,
        )
    if not _meets_driver(best.driver):
        return Decision(
            backend="faster_whisper",
            device="cpu",
            whisper_model="small",
            reason=f"驱动 {best.driver} 过旧（CUDA 12 需 ≥{'.'.join(map(str, MIN_DRIVER))}）",
            gpu=best.name,
            vram_mb=best.memory_mb,
            driver=best.driver,
        )
    return Decision(
        backend="qwen3_asr",
        device="cuda",
        whisper_model="small",
        reason="GPU 可用",
        gpu=best.name,
        vram_mb=best.memory_mb,
        driver=best.driver,
    )


def detect() -> Decision:
    exe = find_nvidia_smi()
    return decide(query_gpus(exe) if exe else [])


def patch_env(path: str, decision: Decision) -> bool:
    """把判定结果写回 .env（只动必要的行，保留注释与其它配置）。

    - 选 Qwen 时只改 STT_BACKEND / STT_DEVICE；
    - 退回 Whisper 时才顺带把 STT_MODEL 设成 small（Qwen 后端下该值无效，
      但日后手动切回 Whisper 时它决定了 CPU 上的体验）。

    返回是否真的改写了文件。键不存在时追加到末尾。
    """
    values = {
        "STT_BACKEND": decision.backend,
        "STT_DEVICE": decision.device,
    }
    if decision.backend != "qwen3_asr":
        values["STT_MODEL"] = decision.whisper_model

    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            lines = fh.readlines()
    except OSError as exc:
        print(f"[语音] 读取 {path} 失败，跳过自动配置: {exc}", file=sys.stderr)
        return False

    seen = set()
    out = []
    for line in lines:
        stripped = line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else None
        if key in values:
            seen.add(key)
            ending = "\r\n" if line.endswith("\r\n") else "\n"
            out.append(f"{key}={values[key]}{ending}")
        else:
            out.append(line)

    missing = [k for k in values if k not in seen]
    if missing:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.extend(f"{k}={values[k]}\n" for k in missing)

    try:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.writelines(out)
    except OSError as exc:
        print(f"[语音] 写入 {path} 失败: {exc}", file=sys.stderr)
        return False
    return True


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="探测本机是否适合跑 Qwen3-ASR")
    parser.add_argument("--patch", metavar="ENV_FILE", help="把结果写回该 .env 文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON（供脚本调用）")
    args = parser.parse_args(argv)

    decision = detect()

    if args.json:
        print(json.dumps(asdict(decision), ensure_ascii=False))
    else:
        print(f"[语音] {decision.describe()}")

    if args.patch:
        if patch_env(args.patch, decision):
            keys = "STT_BACKEND/STT_DEVICE"
            if decision.backend != "qwen3_asr":
                keys += "/STT_MODEL"
            print(f"[语音] 已写入 {args.patch}（{keys}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
