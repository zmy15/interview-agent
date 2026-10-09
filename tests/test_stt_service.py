"""
STT 微服务的 VAD 与流式转录测试

背景：这一层曾有**四个叠加的静默 bug**，导致整条流式识别链路完全失效
（客户端永远收不到任何文字，且没有任何报错）：

  1. Silero VAD 只接受固定窗口（16kHz→512 样本），而代码直接喂 100ms
     （1600 样本）的帧，每次调用都抛 ValueError；异常被 `except
     Exception: speech_prob = 0.0` 吞掉，于是**永远检测不到语音**。
  2. VAD 触发 speech_end 后调用 `_reset()` 清空了音频缓冲，
     调用方随后 `get_buffer_and_reset()` 拿到的是**空音频**。
  3. `_transcribe_segment(...)` 没有传 final=True，`on_final` 从不触发，
     转写结果只累积在内部、从不推给客户端。
  4. `speech_duration = ts - (self._speech_start_time or ts)`：
     语音从第 0 秒开始时 `_speech_start_time == 0.0`（falsy），
     被替换成 ts，算出时长为 0，整段语音被当成「太短」丢弃。

这四个都是「不报错但功能全废」的类型，因此这里逐条钉住。

注意：项目未安装 pytest-asyncio，异步用例统一用 asyncio.run() 驱动。
"""

import asyncio
import os
import sys

import numpy as np
import pytest

# stt_service 是独立目录，按官方文档以脚本方式导入
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stt_service"),
)

from vad_processor import VADProcessor, VAD_WINDOW_SAMPLES  # noqa: E402
from streaming_transcriber import StreamingTranscriber  # noqa: E402


SR = 16000
FRAME = 1600  # 100ms @ 16kHz，与客户端发送的帧长一致


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SR * seconds), dtype=np.float32)


# ══════════════════════════════════════════════════════════════
# bug 1：Silero 的窗口尺寸约束
# ══════════════════════════════════════════════════════════════


def test_vad_window_matches_silero_requirement():
    """16kHz 必须是 512 样本窗口（Silero 的硬性要求）"""
    assert VAD_WINDOW_SAMPLES[16000] == 512
    assert VAD_WINDOW_SAMPLES[8000] == 256


def test_speech_probability_does_not_raise_on_100ms_frame():
    """回归：100ms（1600 样本）的帧不能因为窗口不匹配而抛异常。

    早期实现直接喂 1600 样本，Silero 抛
    "Provided number of samples is 1600 (Supported values: 512)"，
    被 except 吞掉后概率恒为 0。
    """
    vad = VADProcessor(sample_rate=SR)
    frame = np.random.randn(FRAME).astype(np.float32) * 0.1

    prob = vad._speech_probability(frame)
    assert 0.0 <= prob <= 1.0, "应返回合法概率而不是因异常变成 0"


def test_speech_probability_handles_short_frame():
    """不足一个窗口的帧应安全返回 0，而不是抛异常"""
    vad = VADProcessor(sample_rate=SR)
    assert vad._speech_probability(np.zeros(100, dtype=np.float32)) == 0.0


def test_speech_probability_on_silence_is_low():
    """静音必须判为低概率（否则会一直处于「说话中」）"""
    vad = VADProcessor(sample_rate=SR)
    assert vad._speech_probability(_silence(0.1)) < 0.5


# ══════════════════════════════════════════════════════════════
# bug 2：speech_end 之后音频不能被丢掉
# ══════════════════════════════════════════════════════════════


def _feed_until_speech_end(vad, speech_seconds=1.0):
    """喂入一段「像语音」的信号 + 静音，直到触发 speech_end。

    直接用正弦波 Silero 不会判为语音（它是语音检测器，不是声音检测器），
    因此这里 monkeypatch 掉概率计算，专注验证状态机与缓冲行为。
    真实语音的端到端路径由 tests/test_system_audio.py 与手工验证覆盖。
    """
    vad._speech_probability = lambda frame: 0.9  # 始终「在说话」
    for _ in range(int(speech_seconds * 10)):
        vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)

    vad._speech_probability = lambda frame: 0.0  # 转为静音
    events = []
    for _ in range(int((vad.silence_timeout + 0.3) * 10)):
        events.extend(vad.process_frame(np.zeros(FRAME, dtype=np.float32)))
    return events


def test_buffer_survives_speech_end():
    """回归：触发 speech_end 后必须还能取到那段音频。

    早期 `_reset()` 无条件清空 buffer，导致 speech_end 之后
    get_buffer_and_reset() 返回空数组，转录结果永远为空。
    """
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0)
    events = _feed_until_speech_end(vad)

    assert any(e["type"] == "speech_end" for e in events), "应触发 speech_end"

    audio = vad.get_buffer_and_reset()
    assert len(audio) > 0, "speech_end 后取到的音频不能为空"
    # 至少包含那段「语音」
    assert len(audio) >= SR * 1.0


def test_buffer_cleared_after_consuming():
    """取走之后 buffer 必须清空，避免下一段重复转录"""
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0)
    _feed_until_speech_end(vad)

    first = vad.get_buffer_and_reset()
    assert len(first) > 0
    assert len(vad.get_buffer_and_reset()) == 0


# ══════════════════════════════════════════════════════════════
# 静音不得进入转录（识别慢 / 空白也被转录）
# ══════════════════════════════════════════════════════════════
#
# 早期实现把**每一帧**都塞进 buffer，静音也不例外。后果：
#   - 用户说完一句话，前面的几十秒静音也一起送去 Whisper，
#     既慢又容易产生与内容无关的幻觉文本（实测出现过 44s/77s 的片段）；
#   - 两次说话之间只要没断句就被并成一大段。


def test_silence_before_speech_not_buffered():
    """说话前的长时间静音不能进入 buffer"""
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0)
    vad._speech_probability = lambda frame: 0.0

    # 5 秒静音
    for _ in range(50):
        vad.process_frame(np.zeros(FRAME, dtype=np.float32))

    assert len(vad._buffer) == 0, "静音被放进了待转录缓冲"


def test_preroll_keeps_small_window_only():
    """静默期间只保留一小段前置缓冲（用于接住起头字）"""
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0, preroll_seconds=0.3)
    vad._speech_probability = lambda frame: 0.0

    for _ in range(50):
        vad.process_frame(np.zeros(FRAME, dtype=np.float32))

    buffered = sum(len(f) for f in vad._preroll)
    # 0.3s @16k = 4800 样本，允许一帧的误差
    assert FRAME <= buffered <= FRAME * 4, f"前置缓冲长度异常: {buffered}"


def test_segment_audio_excludes_silence_tail():
    """取到的音频不应含断句前那 1 秒静音尾巴"""
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0, preroll_seconds=0.3)

    # 说话 2 秒
    vad._speech_probability = lambda frame: 0.9
    for _ in range(20):
        vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)

    # 1.5 秒静音触发断句
    vad._speech_probability = lambda frame: 0.0
    for _ in range(15):
        vad.process_frame(np.zeros(FRAME, dtype=np.float32))

    audio = vad.get_buffer_and_reset()
    duration = len(audio) / SR
    # 期望 ≈ 0.3s 前置 + 2s 语音 = 2.3s；若把静音尾巴算进来会到 3.5s+
    assert 2.0 <= duration <= 2.8, f"音频时长异常（含静音尾巴？）: {duration:.2f}s"


def test_consecutive_segments_do_not_bleed():
    """连续两段语音必须各自独立，不能互相粘连"""
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0)

    def speak(seconds):
        vad._speech_probability = lambda frame: 0.9
        for _ in range(int(seconds * 10)):
            vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)
        vad._speech_probability = lambda frame: 0.0
        for _ in range(15):
            vad.process_frame(np.zeros(FRAME, dtype=np.float32))

    speak(2.0)
    first = vad.get_buffer_and_reset()
    speak(1.0)
    second = vad.get_buffer_and_reset()

    assert 1.8 <= len(first) / SR <= 2.8, f"第一段时长异常: {len(first)/SR:.2f}s"
    assert 0.8 <= len(second) / SR <= 1.8, f"第二段时长异常: {len(second)/SR:.2f}s"


def test_short_speech_is_discarded():
    """短于 min_speech_duration 的噪声应被丢弃，不触发 speech_end"""
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0, min_speech_duration=0.3)

    vad._speech_probability = lambda frame: 0.9
    vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)  # 仅 0.1s

    vad._speech_probability = lambda frame: 0.0
    events = []
    for _ in range(15):
        events.extend(vad.process_frame(np.zeros(FRAME, dtype=np.float32)))

    assert not any(e["type"] == "speech_end" for e in events)


def test_speech_starting_at_zero_second_is_not_dropped():
    """回归：语音从第 0 秒开始（_speech_start_time == 0.0）不能被丢弃。

    0.0 是 falsy，早期写法 `_speech_start_time or ts` 会把它替换成 ts，
    算出 speech_duration=0，于是整段语音被当成「太短」静默丢弃。
    """
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0, min_speech_duration=0.3)

    # 第一帧就是语音 -> _speech_start_time 恰好是 0.0
    vad._speech_probability = lambda frame: 0.9
    for _ in range(10):  # 1 秒
        vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)
    assert vad._speech_start_time == 0.0

    vad._speech_probability = lambda frame: 0.0
    events = []
    for _ in range(15):
        events.extend(vad.process_frame(np.zeros(FRAME, dtype=np.float32)))

    assert any(e["type"] == "speech_end" for e in events), "从 0 秒开始的语音不应被丢弃"
    assert len(vad.get_buffer_and_reset()) > 0


# ══════════════════════════════════════════════════════════════
# bug 3：断句结果必须推给客户端
# ══════════════════════════════════════════════════════════════


class _FakeWhisper:
    """假的 faster-whisper 模型：固定返回一段中文"""

    def __init__(self, text="这是识别结果"):
        self.text = text
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append({"samples": len(audio), **kwargs})
        seg = type("Seg", (), {"text": self.text})()
        info = type("Info", (), {"language": "zh"})()
        return iter([seg]), info


def _make_transcriber(model, finals=None, partials=None, silence_timeout=1.0):
    """构造一个用假模型替代 Whisper 的转录器"""
    tr = StreamingTranscriber(
        sample_rate=SR,
        silence_timeout=silence_timeout,
        on_final=(finals.append if finals is not None else None),
        on_partial=(partials.append if partials is not None else None),
    )
    tr._model = model
    tr._ensure_model = lambda: None
    return tr


async def _drive_speech_then_silence(tr, speech_frames=10, silence_frames=15):
    """喂入一段语音再喂静音，触发断句并等后台转录完成"""
    tr.vad._speech_probability = lambda frame: 0.9
    for _ in range(speech_frames):
        await tr.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)

    tr.vad._speech_probability = lambda frame: 0.0
    for _ in range(silence_frames):
        await tr.process_frame(np.zeros(FRAME, dtype=np.float32))

    if tr._pending_tasks:
        await asyncio.gather(*tr._pending_tasks, return_exceptions=True)


def test_speech_end_emits_final_to_client():
    """回归：断句完成后必须触发 on_final，把文本推给客户端。

    早期 process_frame 调 _transcribe_segment 时没传 final=True，
    on_final 从不触发 —— 转写虽然做了，客户端却一个字都收不到。
    """
    finals, partials = [], []
    tr = _make_transcriber(_FakeWhisper("请介绍一下你的项目"), finals, partials)

    asyncio.run(_drive_speech_then_silence(tr))

    assert finals, "断句后必须把结果推给客户端（on_final）"
    assert "项目" in finals[-1]


def test_transcription_receives_non_empty_audio():
    """转录时拿到的音频不能是空的（bug 1 + bug 2 的组合后果）"""
    model = _FakeWhisper()
    tr = _make_transcriber(model)

    asyncio.run(_drive_speech_then_silence(tr))

    assert model.calls, "应至少调用一次转录"
    assert model.calls[0]["samples"] > 0, "送给模型的音频不能为空"


def test_flush_transcribes_pending_buffer():
    """手动停止时应把缓冲里剩下的音频转录出来"""
    finals = []
    tr = _make_transcriber(_FakeWhisper("最后一句"), finals)

    async def run():
        tr.vad._speech_probability = lambda frame: 0.9
        for _ in range(10):
            tr.vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)
        return await tr.flush()

    text = asyncio.run(run())
    assert "最后一句" in (text or "")
    assert finals, "flush 也应触发 on_final"


def test_final_is_per_segment_not_cumulative():
    """final 只推本段，不能把前面所有句子累积进来。

    回归：早期实现把 _full_text（跨断句不断累积）当 final 推送，
    于是第二句话的 final = "第一句话 + 第二句话"。前端表现为
    「第二次的内容和第一次连在一起且重复」。
    """
    finals = []
    tr = _make_transcriber(_FakeWhisper("第一句话。"), finals)

    async def go():
        # 第一段
        tr._model = _FakeWhisper("第一句话。")
        await _drive_speech_then_silence(tr)
        # 第二段（换模型输出，模拟识别到不同内容）
        tr._model = _FakeWhisper("第二句话。")
        await _drive_speech_then_silence(tr)

    asyncio.run(go())

    assert finals == ["第一句话。", "第二句话。"], f"final 出现累积: {finals}"


def test_partial_is_per_segment_not_cumulative():
    """partial 同样只反映本段，不累积前文"""
    partials = []
    tr = _make_transcriber(_FakeWhisper("第一句话。"), partials=partials)

    async def go():
        tr._model = _FakeWhisper("第一句话。")
        await _drive_speech_then_silence(tr)
        tr._model = _FakeWhisper("第二句话。")
        await _drive_speech_then_silence(tr)

    asyncio.run(go())

    assert partials == ["第一句话。", "第二句话。"], f"partial 出现累积: {partials}"


# ══════════════════════════════════════════════════════════════
# 标点：短片段上必须带 initial_prompt
# ══════════════════════════════════════════════════════════════
#
# Whisper 在缺乏上下文的 1~2 秒碎片上**完全不输出标点**。
# 实测（1.5 秒碎片）：
#     无 prompt -> 1/9 段有标点
#     有 prompt -> 4/5 段有标点
# 靠加长片段无法解决（试到 12 秒仍不稳定），只有 initial_prompt 有效。


class _CapturingWhisper:
    """记录 transcribe 调用参数的假模型"""

    def __init__(self, text="测试。"):
        self.text = text
        self.kwargs = {}

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        seg = type("Seg", (), {"text": self.text})()
        info = type("Info", (), {"language": "zh"})()
        return iter([seg]), info


def test_transcribe_passes_initial_prompt():
    """必须传 initial_prompt，否则短片段会丢失标点"""
    model = _CapturingWhisper()
    tr = _make_transcriber(model)

    asyncio.run(_drive_speech_then_silence(tr))

    assert model.kwargs, "transcribe 未被调用"
    assert model.kwargs.get("initial_prompt") == StreamingTranscriber.INITIAL_PROMPT


def test_transcribe_disables_previous_text_conditioning():
    """每段是独立音频块，不应依赖上一段文本"""
    model = _CapturingWhisper()
    tr = _make_transcriber(model)

    asyncio.run(_drive_speech_then_silence(tr))

    assert model.kwargs.get("condition_on_previous_text") is False


# ══════════════════════════════════════════════════════════════
# 静音防护：能量门限 + 提示词泄漏过滤
# ══════════════════════════════════════════════════════════════
#
# initial_prompt 有副作用：在静音/噪声片段上 Whisper 会把提示词本身
# 吐出来（实测输出 '。。。。。。。。' 或 '请使用简体中文并加上标'）。
# 而空提示词又会让 Whisper 在静音上产生幻觉
# （实测输出 '我认识你我认识你我认识你'）。
# 因此必须两道防线：能量门限挡住静音，文本层过滤兜底。


def test_silence_segment_skipped_before_transcribe():
    """接近纯静音的片段不应送进 Whisper"""
    model = _CapturingWhisper()
    tr = _make_transcriber(model)
    tr._ensure_model = lambda: None

    silence = np.zeros(int(SR * 1.5), dtype=np.float32)
    asyncio.run(tr._transcribe_segment(silence, final=True))

    assert not model.kwargs, "静音片段被送进了 Whisper"


def test_low_level_noise_skipped():
    """极低电平（底噪）也应被跳过"""
    model = _CapturingWhisper()
    tr = _make_transcriber(model)
    tr._ensure_model = lambda: None

    noise = (np.random.randn(SR) * 0.0005).astype(np.float32)
    asyncio.run(tr._transcribe_segment(noise, final=True))

    assert not model.kwargs, "底噪片段被送进了 Whisper"


def test_normal_speech_level_not_skipped():
    """正常语音电平不能被误杀"""
    model = _CapturingWhisper("正常内容。")
    tr = _make_transcriber(model)
    tr._ensure_model = lambda: None

    speech = (np.random.randn(SR) * 0.05).astype(np.float32)
    asyncio.run(tr._transcribe_segment(speech, final=True))

    assert model.kwargs, "正常语音被误判为静音"


@pytest.mark.parametrize(
    "leaked",
    [
        "。。。。。。。。",          # 纯标点（实测形态）
        "请使用简体中文并加上标",     # 提示词片段（实测形态）
        "以下是普通话的句子",         # 提示词片段
        "请使用简体中文并加上标点符号。",  # 完整提示词
    ],
)
def test_prompt_leak_filtered(leaked):
    """提示词泄漏的几种形态都要被过滤掉"""
    tr = _make_transcriber(_FakeWhisper())
    assert tr._strip_prompt_leak(leaked) == ""


@pytest.mark.parametrize(
    "normal",
    [
        "鼠标的天选我们测过很多了。",
        "你好，请介绍一下你的项目经验。",
        "这个问题的答案是需要考虑三个方面的。",
    ],
)
def test_normal_text_not_filtered(normal):
    """正常转写内容不能被误过滤"""
    tr = _make_transcriber(_FakeWhisper())
    assert tr._strip_prompt_leak(normal) == normal