"""
幻觉与配置解析测试

两类问题都来自实测（large-v3-turbo + 国内网络环境）：

1. Whisper 训练集幻觉
   Whisper 的语料主要来自带字幕的视频，在静音/低信噪比片段上会复读
   字幕套话。实测 large-v3-turbo 比 base **更容易**触发：
       请不吝点赞 订阅 转发 打赏支持明镜与点点栏目
       字幕由 amara.org 社区提供
   这些内容与面试无关，必须丢掉，否则会污染对话。

2. HuggingFace Xet 下载卡死
   huggingface_hub 新版默认走 Xet 存储后端，权重从
   cas-bridge.xethub.hf.co 下载，该域名不受 HF_ENDPOINT 影响。
   实测：启用 Xet 时 30 秒下载 0 MB；禁用后 1.5GB 模型 146 秒完成。
"""

import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stt_service"),
)

from streaming_transcriber import StreamingTranscriber  # noqa: E402
from stt_config import resolve_compute_type  # noqa: E402


def _clean(text: str) -> str:
    """走与转录器相同的清洗链路"""
    tr = StreamingTranscriber()
    return tr._strip_prompt_leak(tr._strip_hallucination_spans(text))


# ══════════════════════════════════════════════════════════════
# 幻觉过滤
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "hallucination",
    [
        "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
        "请不吝点赞订阅转发打赏支持明镜与点点栏目",
        "字幕由 amara.org 社区提供",
        "字幕志愿者 李宗盛",
        "MING PAO CANADA",
        "谢谢大家观看",
        # 提示词泄漏（与幻觉同一条清洗链路）
        "请使用简体中文并加上标点符号。",
        "。。。。。。。。",
    ],
)
def test_hallucination_dropped(hallucination):
    """整段就是幻觉/泄漏时，应被完全丢弃"""
    assert _clean(hallucination) == "", f"未过滤: {hallucination!r}"


@pytest.mark.parametrize(
    "source,expected",
    [
        # 实测形态：幻觉接在正常内容后面
        ("那天选者，请不吝点赞 订阅 转发 打赏支持明镜与点点栏目", "那天选者"),
        ("这华为笔记本你们，字幕由 amara.org 社区提供", "这华为笔记本你们"),
    ],
)
def test_hallucination_span_trimmed(source, expected):
    """句内幻觉应被截掉，保留前面的正常内容"""
    assert _clean(source) == expected


@pytest.mark.parametrize(
    "normal",
    [
        "鼠标的天选我们。",
        "我们测过很多了。",
        "那天选者",
        "游戏本你见过没?",
        "这华为笔记本你们",
        "你们听说过吗?",
        "请介绍一下你的项目经验。",
        # 单独出现的「谢谢」「感谢」是正常表达，不能当幻觉误杀
        "谢谢",
        "感谢",
    ],
)
def test_normal_speech_not_dropped(normal):
    """正常内容不能被误过滤"""
    assert _clean(normal) == normal


def test_sentence_punctuation_preserved():
    """回归：句末标点不能被清洗逻辑吃掉

    早期实现对结尾做了无差别 strip("，,。.、；;：:")，
    把正常句号也去掉了（'鼠标的天选我们。' -> '鼠标的天选我们'）。
    现在只去连接性标点，保留句末标点。
    """
    assert _clean("鼠标的天选我们。").endswith("。")
    assert _clean("游戏本你见过没?").endswith("?")


def test_leading_punctuation_stripped_after_trim():
    """截断后残留的悬挂逗号应被清掉"""
    out = _clean("那天选者，请不吝点赞 订阅 转发")
    assert not out.endswith("，")


# ══════════════════════════════════════════════════════════════
# 计算精度解析
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "device,raw,expected",
    [
        # 留空 / auto 时按设备决定
        ("cuda", "", "float16"),
        ("cuda", "auto", "float16"),
        ("cpu", "", "int8"),
        ("cpu", "auto", "int8"),
        # 显式指定要尊重
        ("cuda", "int8", "int8"),
        ("cpu", "float32", "float32"),
        ("cuda", "float16", "float16"),
        # 未知设备保守用 int8
        ("", "", "int8"),
        ("mps", "", "int8"),
        # 大小写与空白容错
        ("CUDA", "  ", "float16"),
    ],
)
def test_resolve_compute_type(device, raw, expected):
    assert resolve_compute_type(device, raw) == expected


# ══════════════════════════════════════════════════════════════
# HuggingFace 下载通道
# ══════════════════════════════════════════════════════════════


def test_xet_disabled_in_stt_service():
    """STT 微服务必须禁用 Xet，否则国内下载权重会卡死

    回归：未禁用时元数据请求全部 200，但 model.bin 停在 0 字节
    （Xet 走 cas-bridge.xethub.hf.co，不受 HF_ENDPOINT 影响）。

    这里用**读取源码**的方式验证，而不是 import stt_service.main ——
    导入会启动 FastAPI 应用并加载模型，污染其他测试的全局状态
    （实测会导致 test_stt_service.py 里的用例互相干扰而失败）。
    """
    main_py = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "stt_service", "main.py",
    )
    source = open(main_py, encoding="utf-8").read()

    assert "HF_HUB_DISABLE_XET" in source, "未禁用 Xet，国内下载会卡死"
    # 必须在任何 HF 导入之前设置
    assert source.index("HF_HUB_DISABLE_XET") < source.index("from streaming_transcriber")


def test_hf_endpoint_set_before_hf_import():
    """HF_ENDPOINT 必须在导入任何 HF 相关模块之前设置"""
    main_py = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "stt_service", "main.py",
    )
    source = open(main_py, encoding="utf-8").read()

    assert "HF_ENDPOINT" in source
    assert source.index('os.environ["HF_ENDPOINT"]') < source.index(
        "from streaming_transcriber"
    )