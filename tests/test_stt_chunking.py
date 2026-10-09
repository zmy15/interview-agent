"""方案 C 回归测试：VAD 断句与 Whisper 分块解耦

背景（真实故障）：
    一段约 150 秒、中途没有 1 秒以上停顿的自我介绍，
    被 VAD 的 max_speech_duration=30s 强制切成 6 段：
        24.9 / 28.6 / 26.1 / 26.7 / 26.9 / 12.8 秒
    切点落在任意位置（可能劈开一个词），且每段独立送 Whisper、
    互不共享上下文（condition_on_previous_text=False 且无 prompt 上文），
    表现为「被分成好几次才发送，中间不连贯，缺少信息」。

修法（方案 C）：
    VAD 只回答「有没有人在说话」，不再有 max_speech_duration 的硬切；
    「何时切块」交给 streaming_transcriber 的 chunk 逻辑：
      1. 自然停顿处优先收块（语义边界）；
      2. 连续语音超上限才硬切，硬切带 overlap 且不丢帧；
      3. 跨块注入上文（prompt）；
      4. 重叠部分文本去重。
"""

import asyncio
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "stt_service"))

import vad_processor  # noqa: E402

from streaming_transcriber import StreamingTranscriber  # noqa: E402
from vad_processor import VADProcessor  # noqa: E402

SR = 16000
FRAME = 1600  # 100ms


@pytest.fixture(autouse=True)
def _stub_silero(monkeypatch):
    """用假模型替换 Silero，避免测试真的去 torch.hub 下载。

    必须用 fixture + monkeypatch（而不是模块级赋值）：
    模块级替换会**污染整个 pytest 进程**，导致别的测试文件里
    「多个 VADProcessor 共享同一个 Silero 模型」的断言拿到两个
    不同的假对象而失败（实测 test_silero_model_shared 因此挂掉）。
    monkeypatch 会在每个测试结束后自动还原。
    """
    monkeypatch.setattr(
        vad_processor, "_get_shared_silero", lambda: (_SharedFakeModel(), None)
    )


class _SharedFakeModel:
    """进程级共享的假 Silero：保证同一进程只构造一次

    本文件只驱动 VAD 的状态机（_speech_probability 被逐个测试替换掉），
    因此假模型不需要真的能推理，只需可被共享、可被赋值给 _model。
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


# ══════════════════════════════════════════════════════════════
# VAD 不再做分块决策
# ══════════════════════════════════════════════════════════════


def test_vad_does_not_force_split_on_max_duration():
    """VAD 不得因为「说得太久」而自行切分。

    回归：早期 max_speech_duration=30s 到点就发 speech_end，
    把一段连续语流每 30 秒剁一刀（实测 24.9/28.6/26.1/26.7/26.9s），
    切点落在词中间且丢掉跨切点的字。
    """
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0)
    vad._speech_probability = lambda f: 0.9

    events = []
    # 连续说话 90 秒，远超旧上限 30s
    for _ in range(900):
        events.extend(vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1))

    forced = [e for e in events if e.get("forced")]
    assert not forced, f"VAD 仍在按 max_speech_duration 强制切分: {forced[:3]}"
    assert not any(e["type"] == "speech_end" for e in events), (
        "连续语音未出现静默，不应触发 speech_end"
    )
    # 音频应完整保留在缓冲里（没被切走）
    assert vad.buffered_duration() > 88.0, (
        f"连续语音的音频被切走/丢失，仅剩 {vad.buffered_duration():.1f}s"
    )


def test_vad_emits_pause_hint_without_consuming_audio():
    """停顿提示是「软」的：只通知，不动缓冲。"""
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0, pause_hint=0.4)

    vad._speech_probability = lambda f: 0.9
    for _ in range(30):  # 说话 3s
        vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)
    buffered_before = vad.buffered_duration()

    vad._speech_probability = lambda f: 0.0
    events = []
    for _ in range(6):  # 静音 0.6s（>= pause_hint，< silence_timeout）
        events.extend(vad.process_frame(np.zeros(FRAME, dtype=np.float32)))

    assert any(e["type"] == "speech_pause" for e in events), "应有停顿提示"
    assert not any(e["type"] == "speech_end" for e in events), "未到断句阈值"
    # 关键：软提示不得消费音频
    assert vad.buffered_duration() == pytest.approx(buffered_before), (
        "停顿提示不应改变缓冲内容"
    )


def test_pause_hint_fires_only_once_per_pause():
    """一次停顿只提示一次，避免每帧重复通知"""
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0, pause_hint=0.4)
    vad._speech_probability = lambda f: 0.9
    for _ in range(30):
        vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)

    vad._speech_probability = lambda f: 0.0
    events = []
    for _ in range(9):  # 0.9s 静音，全程未到 1.0s 断句
        events.extend(vad.process_frame(np.zeros(FRAME, dtype=np.float32)))

    pauses = [e for e in events if e["type"] == "speech_pause"]
    assert len(pauses) == 1, f"停顿提示重复触发 {len(pauses)} 次"


def test_speech_resume_after_pause():
    """停顿后继续说话应给出 resume 事件"""
    vad = VADProcessor(sample_rate=SR, silence_timeout=1.0, pause_hint=0.4)
    vad._speech_probability = lambda f: 0.9
    for _ in range(30):
        vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)

    vad._speech_probability = lambda f: 0.0
    for _ in range(6):
        vad.process_frame(np.zeros(FRAME, dtype=np.float32))

    vad._speech_probability = lambda f: 0.9
    events = vad.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)
    assert any(e["type"] == "speech_resume" for e in events), "恢复说话应有 resume 事件"


# ══════════════════════════════════════════════════════════════
# 分块：不丢音频 + 不劈词
# ══════════════════════════════════════════════════════════════


class _RecordingWhisper:
    """记录每次送进来的音频与 prompt"""

    def __init__(self, text="识别内容。"):
        self.text = text
        self.audio_calls = []
        self.prompts = []

    def transcribe(self, audio, **kwargs):
        self.audio_calls.append(np.asarray(audio).copy())
        self.prompts.append(kwargs.get("initial_prompt", ""))
        seg = type("Seg", (), {"text": self.text})()
        info = type("Info", (), {"language": "zh"})()
        return iter([seg]), info


def _make_tr(model, **kw):
    tr = StreamingTranscriber(sample_rate=SR, silence_timeout=1.0, **kw)
    tr._model = model
    tr._ensure_model = lambda: None
    tr.on_partial = lambda t: None
    tr.on_final = lambda t: None
    tr.vad._speech_probability = lambda f: 0.0
    return tr


def test_continuous_speech_audio_is_conserved():
    """连续语音硬切后，送出去的音频总量必须等于输入（不丢帧）。

    回归：早期强制切分只挪计时器、不保留跨切点音频，切点附近的字丢掉。
    """
    model = _RecordingWhisper()
    tr = _make_tr(model)

    async def run():
        tr.vad._speech_probability = lambda f: 0.9
        total = 0
        for _ in range(900):  # 90s 连续语音
            frame = np.ones(FRAME, dtype=np.float32) * 0.1
            total += len(frame)
            await tr.process_frame(frame)
        tr.vad._speech_probability = lambda f: 0.0
        for _ in range(20):
            await tr.process_frame(np.zeros(FRAME, dtype=np.float32))
        if tr._pending_tasks:
            await asyncio.gather(*tr._pending_tasks, return_exceptions=True)
        return total

    total_in = asyncio.run(run())
    total_out = sum(len(a) for a in model.audio_calls)

    assert model.audio_calls, "应有块被送出转录"
    assert total_out == total_in, (
        f"音频丢失: 送入 {total_in} 样本，转出 {total_out} 样本，"
        f"差 {total_in - total_out}"
    )


def test_hard_split_keeps_overlap():
    """硬切处必须保留 overlap，保证切点的字至少被识别一次"""
    model = _RecordingWhisper()
    tr = _make_tr(model, chunk_overlap_seconds=0.5, chunk_max_seconds=10.0)

    async def run():
        tr.vad._speech_probability = lambda f: 0.9
        for _ in range(300):  # 30s 连续，会触发多次硬切
            await tr.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)
        tr.vad._speech_probability = lambda f: 0.0
        for _ in range(20):
            await tr.process_frame(np.zeros(FRAME, dtype=np.float32))
        if tr._pending_tasks:
            await asyncio.gather(*tr._pending_tasks, return_exceptions=True)

    asyncio.run(run())
    # 相邻块应有重叠（后块开头 == 前块结尾）
    assert len(model.audio_calls) >= 2, "应至少切出 2 块"
    for i in range(1, len(model.audio_calls)):
        prev_tail = model.audio_calls[i - 1][-int(0.5 * SR):]
        cur_head = model.audio_calls[i][: len(prev_tail)]
        assert len(cur_head) == len(prev_tail)
        assert np.array_equal(cur_head, prev_tail), f"第 {i} 块与前块无重叠"


def test_no_forced_30s_boundary_chunks():
    """不再出现「每段都贴着 30 秒」的碎片切分（原始症状）"""
    model = _RecordingWhisper()
    tr = _make_tr(model, chunk_max_seconds=25.0)

    async def run():
        # 模拟真实自介绍：连续说话，中途有 0.5s 换气
        for _ in range(10):
            tr.vad._speech_probability = lambda f: 0.9
            for _ in range(150):  # 15s
                await tr.process_frame(np.ones(FRAME, dtype=np.float32) * 0.1)
            tr.vad._speech_probability = lambda f: 0.0
            for _ in range(5):  # 0.5s 换气
                await tr.process_frame(np.zeros(FRAME, dtype=np.float32))
        tr.vad._speech_probability = lambda f: 0.0
        for _ in range(20):
            await tr.process_frame(np.zeros(FRAME, dtype=np.float32))
        if tr._pending_tasks:
            await asyncio.gather(*tr._pending_tasks, return_exceptions=True)

    asyncio.run(run())
    secs = [len(a) / SR for a in model.audio_calls]
    # 不应再出现一堆 29.5~30.0s 的整齐碎片
    at_30 = [s for s in secs if 29.0 <= s <= 30.5]
    assert not at_30, f"仍存在 30 秒硬切碎片: {[round(s,1) for s in secs]}"


# ══════════════════════════════════════════════════════════════
# 跨块上下文与重叠去重
# ══════════════════════════════════════════════════════════════


def test_cross_chunk_context_is_injected():
    """后续块的 prompt 必须带上文（解决「语义不连贯」）"""
    model = _RecordingWhisper("我独立负责整个RAG系统。")
    tr = _make_tr(model)

    async def run():
        for _ in range(3):
            await tr._transcribe_segment(
                np.ones(SR * 2, dtype=np.float32) * 0.1, 0.0,
                final=True, chunk_seq=tr._next_chunk_seq(),
            )

    asyncio.run(run())
    assert len(model.prompts) == 3
    # 第一块无上文；第二、三块应包含上文的尾部文本
    assert model.prompts[0] == StreamingTranscriber.INITIAL_PROMPT
    for p in model.prompts[1:]:
        assert p != StreamingTranscriber.INITIAL_PROMPT, "后续块的 prompt 没带上文"
        assert "RAG" in p, f"上文内容未注入: {p!r}"


def test_context_chain_is_ordered_under_concurrency():
    """并发切块时，上下文仍按切出顺序串联（而非按完成顺序）"""
    model = _RecordingWhisper("内容。")
    tr = _make_tr(model)

    async def run():
        # 同时起 4 块（模拟同一轮事件循环里连续切出）
        tasks = [
            asyncio.create_task(tr._transcribe_segment(
                np.ones(SR, dtype=np.float32) * 0.1, 0.0,
                final=True, chunk_seq=tr._next_chunk_seq(),
            ))
            for _ in range(4)
        ]
        await asyncio.gather(*tasks)

    asyncio.run(run())
    assert model.prompts[0] == StreamingTranscriber.INITIAL_PROMPT
    # 第 2 块起都应有上文（说明确实等到了前块）
    for p in model.prompts[1:]:
        assert p != StreamingTranscriber.INITIAL_PROMPT, "并发下上下文链断了"


def test_overlap_text_deduplicated():
    """重叠区间被重复识别的文本应被去掉"""
    tr = _make_tr(_RecordingWhisper())
    # 上文结尾是「我觉得这个项目」，本块开头重复了「这个项目」
    out = tr._dedupe_overlap("这个项目最大的难点是并发。", "我觉得这个项目")
    assert out == "最大的难点是并发。", f"重叠未去重: {out!r}"


def test_dedupe_keeps_legitimate_repetition():
    """正常表达不能被误删"""
    tr = _make_tr(_RecordingWhisper())
    out = tr._dedupe_overlap("这个项目很好。", "我觉得那个方案")
    assert out == "这个项目很好。"


def test_prompt_length_is_capped():
    """prompt 不能无限长（Whisper 有 224 token 上限）"""
    tr = _make_tr(_RecordingWhisper(), chunk_context_chars=120)
    tr._context_tail = "甲" * 500
    prompt = tr._build_prompt()
    assert len(prompt) <= len(StreamingTranscriber.INITIAL_PROMPT) + 120


def test_reset_clears_chunk_state():
    """reset 必须清掉分块相关状态，避免下一场录音串上下文"""
    tr = _make_tr(_RecordingWhisper())
    tr._full_text = "上一场的内容"
    tr._context_tail = "上一场"
    tr._chunk_texts = {0: "x"}
    tr._chunk_seq = 5

    tr.reset()

    assert tr._context_tail == ""
    assert tr._full_text == ""
    assert tr._chunk_texts == {}
    assert tr._chunk_seq == 0