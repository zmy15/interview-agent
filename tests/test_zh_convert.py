"""
繁简转换测试

背景：faster-whisper 的中文输出**默认是繁体**（实测「请介绍一下你的项目经验」
会输出成「請介紹一下你的項目經驗」），而界面与 Prompt 都按简体使用，
因此需要统一转换。

转换必须发生在 STT 服务内部的**累积之前**：
partial/final 都是「累积全文」语义，主进程的增量前缀比对
（_new_suffix）依赖繁简一致，否则会重复推送或丢字。
"""

import os
import sys

import pytest

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stt_service"),
)

# zhconv 是可选依赖：未安装时应降级为「不转换」，而不是让服务起不来
zhconv = pytest.importorskip("zhconv", reason="需要 zhconv 才能验证繁简转换")

from zh_convert import to_simplified  # noqa: E402


# ══════════════════════════════════════════════════════════════
# 基本转换
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "traditional,expected",
    [
        # 实测中 Whisper 真实输出过的句子
        ("請介紹一下你的項目經驗", "请介绍一下你的项目经验"),
        ("你好,請介紹一下你的項目經驗。", "你好,请介绍一下你的项目经验。"),
        ("這個問題我會從三個角度來回答", "这个问题我会从三个角度来回答"),
        ("我們只要截然相反的意见吧", "我们只要截然相反的意见吧"),
        # 常见面试词汇
        ("數據結構與算法", "数据结构与算法"),
        ("軟件工程師", "软件工程师"),
        ("網絡協議", "网络协议"),
        ("異步編程", "异步编程"),
    ],
)
def test_traditional_to_simplified(traditional, expected):
    assert to_simplified(traditional) == expected


def test_already_simplified_is_unchanged():
    """已经是简体时不能改动"""
    text = "请介绍一下你的项目经验"
    assert to_simplified(text) == text


def test_mixed_english_and_chinese():
    """中英混合只转中文部分"""
    assert to_simplified("Hello 混合 English 與中文") == "Hello 混合 English 与中文"


def test_conversion_is_idempotent():
    """重复转换结果稳定（增量比对依赖这一点）"""
    once = to_simplified("請介紹一下你的項目經驗")
    twice = to_simplified(once)
    assert once == twice


# ══════════════════════════════════════════════════════════════
# 边界与容错
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize("value", ["", None])
def test_empty_input_safe(value):
    """空串 / None 不能抛异常"""
    assert to_simplified(value) == value


def test_whitespace_and_punctuation_preserved():
    """标点与空白应保留，不能影响后续按标点切句"""
    text = "你好，世界！這是一個測試。"
    out = to_simplified(text)
    assert "，" in out and "！" in out and "。" in out


def test_long_text_conversion():
    """长文本（累积全文）也要能正常转换"""
    text = "請介紹一下你的項目經驗" * 50
    out = to_simplified(text)
    assert "請" not in out
    assert len(out) == len(text), "转换不应改变长度"


# ══════════════════════════════════════════════════════════════
# 与流式转录器集成：转换发生在累积之前
# ══════════════════════════════════════════════════════════════


class _FakeWhisper:
    """假模型：返回指定的繁体文本"""

    def __init__(self, text):
        self.text = text

    def transcribe(self, audio, **kwargs):
        seg = type("Seg", (), {"text": self.text})()
        info = type("Info", (), {"language": "zh"})()
        return iter([seg]), info


def test_transcriber_converts_before_accumulating():
    """转录器输出的 partial/final 都必须是简体。

    回归：若在累积之后才转换，_full_text 里仍是繁体，
    主进程的增量前缀比对会因繁简不一致而错乱。
    """
    import asyncio

    from streaming_transcriber import StreamingTranscriber

    finals, partials = [], []
    tr = StreamingTranscriber(
        sample_rate=16000,
        silence_timeout=1.0,
        on_final=finals.append,
        on_partial=partials.append,
    )
    tr._model = _FakeWhisper("請介紹一下你的項目經驗")
    tr._ensure_model = lambda: None

    async def run():
        tr.vad._speech_probability = lambda frame: 0.9
        for _ in range(10):
            await tr.process_frame(__import__("numpy").ones(1600, dtype="float32") * 0.1)
        tr.vad._speech_probability = lambda frame: 0.0
        for _ in range(15):
            await tr.process_frame(__import__("numpy").zeros(1600, dtype="float32"))
        if tr._pending_tasks:
            await asyncio.gather(*tr._pending_tasks, return_exceptions=True)

    asyncio.run(run())

    assert finals, "应有 final 输出"
    assert finals[-1] == "请介绍一下你的项目经验", f"未转简体: {finals[-1]}"
    assert partials and partials[-1] == "请介绍一下你的项目经验"
    # 内部累积文本也必须是简体（增量比对依赖它）
    assert tr._full_text == "请介绍一下你的项目经验"