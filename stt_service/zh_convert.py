"""
繁简转换 — 把 Whisper 输出的繁体中文转成简体

为什么需要：
    faster-whisper 的中文输出**默认是繁体**（训练语料以繁体为主），
    实测「请介绍一下你的项目经验」会输出成
    「請介紹一下你的項目經驗」。界面与后续 Prompt 都按简体使用，
    因此在写入结果前统一转换。

为什么放在 STT 服务里而不是主进程：
    partial/final 都是「累积全文」语义（见 streaming_transcriber），
    累积发生在 STT 服务内部。若只在主进程转换，累积文本里仍是繁体，
    后续增量比对（_new_suffix 的前缀匹配）会因为繁简不一致而错乱。

实现：zhconv（纯 Python，无需编译）。转换失败时**原样返回**，
绝不因为一个转换问题把整条识别链路搞挂。
"""

import logging
import warnings

logger = logging.getLogger(__name__)

# zhconv 内部 import pkg_resources，在新版 setuptools 上会打弃用警告。
# 这与功能无关，屏蔽掉以免刷屏掩盖真正的日志。
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    try:
        import zhconv

        AVAILABLE = True
    except ImportError:  # pragma: no cover
        zhconv = None  # type: ignore[assignment]
        AVAILABLE = False
        logger.warning(
            "未安装 zhconv，繁体中文将不会被转成简体。"
            "安装：pip install zhconv"
        )


def to_simplified(text: str) -> str:
    """繁体 → 简体。

    - 已经是简体时返回原文（zhconv 幂等）
    - 空串、None 安全
    - 转换异常时返回原文（宁可显示繁体，也不能丢字）
    """
    if not text:
        return text
    if not AVAILABLE or zhconv is None:
        return text

    try:
        return zhconv.convert(text, "zh-cn")
    except Exception as exc:  # pragma: no cover
        logger.warning("繁简转换失败，保留原文: %s", exc)
        return text