"""
系统音频捕获测试 — 回环抓取、格式转换、路由、错误处理

设计原则：
    不依赖真实声卡与真实 STT 服务。
    - 音频捕获用伪造的 soundcard 模块，保证在任何机器/CI 上稳定；
    - STT 连接用假的 websockets，重点校验**帧格式与协议**。

注意：SYSTEM_AUDIO_ENABLED 在 conftest.py 中于导入 main 之前设置
（路由是导入时条件注册的），不要在这里依赖外部环境变量。
"""

import asyncio
import json
import types

import numpy as np
import pytest

from services import system_audio as sa


# ══════════════════════════════════════════════════════════════
# 辅助：伪造 soundcard
# ══════════════════════════════════════════════════════════════


class _FakeRecorder:
    """伪造的录音器：每次 record() 返回一段可预测的音频"""

    def __init__(self, samplerate=48000, channels=2, value=0.5, length=None):
        self.samplerate = samplerate
        self.channels = None  # soundcard 的 recorder.channels 实际就是 None
        self._value = value
        self._length = length

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def record(self, numframes=None):
        n = self._length if self._length is not None else (numframes or 1600)
        if self.channels is None:
            ch = 2
        else:
            ch = self.channels
        data = np.full((n, ch), self._value, dtype=np.float32)
        return data


class _FakeMic:
    def __init__(self, name="假扬声器", samplerate=48000, channels=2, value=0.5):
        self.name = name
        self.id = f"fake-{name}"
        self.samplerate = samplerate
        self.channels = channels
        self._value = value
        self.isloopback = True

    def recorder(self, samplerate=None, blocksize=None, channels=None):
        return _FakeRecorder(
            samplerate=samplerate or self.samplerate,
            channels=self.channels,
            value=self._value,
        )


@pytest.fixture
def fake_soundcard(monkeypatch):
    """把 soundcard 替换成可预测的假实现"""
    mic = _FakeMic()

    speakers = [
        types.SimpleNamespace(id="spk-default", name="默认扬声器"),
        types.SimpleNamespace(id="spk-other", name="外接显示器"),
    ]

    monkeypatch.setattr(sa, "SC_AVAILABLE", True)
    monkeypatch.setattr(sa, "SC_IMPORT_ERROR", "")

    fake = types.SimpleNamespace(
        all_speakers=lambda: speakers,
        default_speaker=lambda: speakers[0],
        get_microphone=lambda device_id, include_loopback=True: mic,
    )
    monkeypatch.setattr(sa, "sc", fake)
    return {"mic": mic, "speakers": speakers, "device_name": mic.name}


# ══════════════════════════════════════════════════════════════
# 可用性与设备枚举
# ══════════════════════════════════════════════════════════════


def test_is_available_when_deps_present(monkeypatch):
    monkeypatch.setattr(sa, "IS_WINDOWS", True)
    monkeypatch.setattr(sa, "SC_AVAILABLE", True)
    assert sa.is_available() is True
    assert sa.availability_error() == ""


def test_unavailable_explains_missing_soundcard(monkeypatch):
    """缺 soundcard 时给出 pip 安装指引，而不是空白报错"""
    monkeypatch.setattr(sa, "IS_WINDOWS", True)
    monkeypatch.setattr(sa, "SC_AVAILABLE", False)
    monkeypatch.setattr(sa, "SC_IMPORT_ERROR", "ModuleNotFoundError: no soundcard")

    assert sa.is_available() is False
    assert "soundcard" in sa.availability_error()
    assert "pip install" in sa.availability_error()


def test_unavailable_on_non_windows(monkeypatch):
    monkeypatch.setattr(sa, "IS_WINDOWS", False)
    assert sa.is_available() is False
    assert "Windows" in sa.availability_error()


def test_list_devices_marks_default_first(fake_soundcard):
    """默认播放设备必须排在最前，方便前端直接取第一个"""
    devices = sa.list_loopback_devices()
    assert len(devices) == 2
    assert devices[0]["id"] == "spk-default"
    assert devices[0]["is_default"] is True
    assert devices[1]["is_default"] is False


def test_list_devices_empty_when_unavailable(monkeypatch):
    monkeypatch.setattr(sa, "IS_WINDOWS", False)
    assert sa.list_loopback_devices() == []


def test_resolve_uses_speaker_name_not_loopback_name(fake_soundcard):
    """展示名必须是扬声器名。

    回归：早期实现里「按 id 指定设备」返回的是回环麦克风名
    （soundcard 里叫「Loopback 扬声器 ...」），而不指定时返回扬声器名，
    两条路径名字不一致，界面上会看到两种叫法。
    """
    _, display = sa._resolve_loopback(None)
    assert display == "默认扬声器"

    _, display_by_id = sa._resolve_loopback("spk-default")
    assert display_by_id == "默认扬声器"

    _, display_other = sa._resolve_loopback("spk-other")
    assert display_other == "外接显示器"


# ══════════════════════════════════════════════════════════════
# 格式转换（48k 立体声 → 16k 单声道）
# ══════════════════════════════════════════════════════════════


def test_to_mono_averages_channels():
    stereo = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], dtype=np.float32)
    assert np.allclose(sa.to_mono(stereo), [0.5, 0.5, 0.5])


def test_to_mono_passthrough_for_1d():
    mono = np.array([0.1, 0.2], dtype=np.float32)
    assert np.allclose(sa.to_mono(mono), mono)


def test_resample_preserves_duration():
    """重采样必须保持时长，否则 STT 听到的语速会错乱"""
    src = np.sin(np.linspace(0, 10, 48000)).astype(np.float32)
    out = sa.resample_linear(src, 48000, 16000)
    assert len(out) == 16000


def test_resample_noop_when_rates_match():
    src = np.arange(100, dtype=np.float32)
    out = sa.resample_linear(src, 16000, 16000)
    assert len(out) == 100


def test_to_target_format_48k_stereo():
    """回环最常见的输入：48kHz 立体声 → 16kHz 单声道"""
    src = np.ones((48000, 2), dtype=np.float32) * 0.3
    out = sa.to_target_format(src, 48000)
    assert out.ndim == 1
    assert out.dtype == np.float32
    assert len(out) == 16000
    assert np.allclose(out, 0.3, atol=1e-6)


def test_to_target_format_is_16khz_mono():
    src = np.random.randn(24000, 2).astype(np.float32)
    out = sa.to_target_format(src, 48000)
    assert len(out) == 8000  # 0.5 秒 @ 16k


def test_pcm16_bytes_format():
    """int16 小端，正好是 stt_service 期望的帧格式"""
    out = sa.pcm16_bytes(np.array([0.0, 1.0, -1.0], dtype=np.float32))
    assert len(out) == 6
    values = np.frombuffer(out, dtype="<i2")
    assert list(values) == [0, 32767, -32767]


def test_pcm16_bytes_clips_out_of_range():
    """超出 [-1,1] 的样本必须被削顶，否则 int16 溢出会变成噪声"""
    out = sa.pcm16_bytes(np.array([5.0, -5.0], dtype=np.float32))
    values = np.frombuffer(out, dtype="<i2")
    assert list(values) == [32767, -32767]


# ══════════════════════════════════════════════════════════════
# 捕获会话
# ══════════════════════════════════════════════════════════════


def test_start_capture_delivers_frames(fake_soundcard):
    """启动后应持续回调 16k 单声道 PCM 帧，每帧约 100ms"""
    frames = []
    cap = sa.start_capture(on_frame=lambda pcm, s: frames.append((pcm, s)))
    try:
        import time
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and len(frames) < 3:
            time.sleep(0.05)
    finally:
        cap.stop()

    assert frames, "应至少收到一帧"
    pcm, samples = frames[0]
    # 100ms @ 16kHz mono int16 = 3200 字节
    assert len(pcm) == 3200
    assert samples.dtype == np.float32
    assert len(samples) == 1600


def test_capture_reports_source_format(fake_soundcard):
    """状态里要能看到回环设备的原生格式，便于排查「没声音」"""
    cap = sa.start_capture(on_frame=lambda pcm, s: None)
    try:
        assert cap.source_format["sample_rate"] == 48000
        assert cap.source_format["channels"] == 2
    finally:
        cap.stop()


def test_capture_stats_track_level(fake_soundcard):
    """有声音时 voiced 应为 True，且电平大于 0"""
    fake_soundcard["mic"]._value = 0.5
    cap = sa.start_capture(on_frame=lambda pcm, s: None)
    try:
        import time
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and cap.stats.frames < 3:
            time.sleep(0.05)
        assert cap.stats.voiced is True
        assert cap.stats.peak > 0
    finally:
        cap.stop()


def test_silence_is_not_voiced(fake_soundcard):
    """纯静音不应被判定为有声音"""
    fake_soundcard["mic"]._value = 0.0
    cap = sa.start_capture(on_frame=lambda pcm, s: None)
    try:
        import time
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and cap.stats.frames < 3:
            time.sleep(0.05)
        assert cap.stats.voiced is False
    finally:
        cap.stop()


def test_double_start_raises(fake_soundcard):
    """同一会话重复 start 应报错，而不是起两个抓取线程"""
    cap = sa.start_capture(on_frame=lambda pcm, s: None)
    try:
        with pytest.raises(sa.SystemAudioError):
            cap.start()
    finally:
        cap.stop()


def test_start_with_unknown_device_raises(monkeypatch, fake_soundcard):
    """指定不存在的设备要明确报错，而不是静默换成默认设备"""
    monkeypatch.setattr(
        sa, "sc",
        types.SimpleNamespace(
            all_speakers=lambda: [types.SimpleNamespace(id="a", name="A")],
            default_speaker=lambda: types.SimpleNamespace(id="a", name="A"),
            get_microphone=lambda device_id, include_loopback=True: None,
        ),
    )

    with pytest.raises(sa.SystemAudioError) as exc:
        sa.LoopbackCapture(device_id="ghost-device").start()
    assert "找不到指定的音频设备" in str(exc.value)


def test_stop_is_idempotent(fake_soundcard):
    """重复 stop 不应抛异常"""
    cap = sa.start_capture(on_frame=lambda pcm, s: None)
    cap.stop()
    cap.stop()
    assert cap.running is False


def test_capture_loop_survives_callback_error(fake_soundcard):
    """回调抛异常不能打断抓取循环"""
    calls = {"n": 0}

    def bad_callback(pcm, samples):
        calls["n"] += 1
        raise RuntimeError("回调炸了")

    cap = sa.start_capture(on_frame=bad_callback)
    try:
        import time
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and calls["n"] < 3:
            time.sleep(0.05)
    finally:
        cap.stop()

    assert calls["n"] >= 3, "循环应继续运行而不是被异常终止"


def test_device_error_reported_on_failure(monkeypatch):
    """设备打不开时，错误要通过 on_error 暴露出来"""
    errors = []

    class _BrokenMic:
        name = "坏设备"
        id = "broken"
        samplerate = 48000
        channels = 2

        def recorder(self, **kwargs):
            raise RuntimeError("设备被独占")

    monkeypatch.setattr(sa, "SC_AVAILABLE", True)
    monkeypatch.setattr(
        sa, "sc",
        types.SimpleNamespace(
            all_speakers=lambda: [types.SimpleNamespace(id="broken", name="坏设备")],
            default_speaker=lambda: types.SimpleNamespace(id="broken", name="坏设备"),
            get_microphone=lambda device_id, include_loopback=True: _BrokenMic(),
        ),
    )

    cap = sa.LoopbackCapture(on_frame=lambda p, s: None, on_error=errors.append)
    with pytest.raises(sa.SystemAudioError) as exc:
        cap.start()
    assert "回环捕获失败" in str(exc.value)


# ══════════════════════════════════════════════════════════════
# 转写结果缓冲
# ══════════════════════════════════════════════════════════════


def test_transcript_store_incremental_fetch():
    """前端按 seq 增量拉取，不应重复拿到旧行"""
    from services.audio_transcribe import TranscriptStore

    store = TranscriptStore(maxlen=10)
    store.add("第一句", "final")
    store.add("第二句", "final")

    assert len(store.since(0)) == 2
    assert len(store.since(1)) == 1
    assert store.since(1)[0]["text"] == "第二句"
    assert store.since(2) == []


def test_transcript_store_respects_maxlen():
    """缓冲区有上限，长时间运行不会无限增长"""
    from services.audio_transcribe import TranscriptStore

    store = TranscriptStore(maxlen=5)
    for i in range(20):
        store.add(f"第{i}句", "final")

    lines = store.since(0)
    assert len(lines) == 5
    assert lines[-1]["text"] == "第19句"


def test_transcript_store_clear_empties_content_but_keeps_seq_monotonic():
    """clear 只清内容，**不重置序号**。

    回归：早期 clear 会把序号归零。而前端按「上次拿到的最大 seq」
    增量拉取且游标只增不减（见 useSystemAudioListener），
    序号一旦倒退，之后所有新行的 `seq > since` 都不成立，
    前端会永远拉不到内容 —— 表现为日志里持续 `transcript?since=N` 不推进。
    """
    from services.audio_transcribe import TranscriptStore

    store = TranscriptStore()
    first = store.add("a", "final")
    assert store.latest_seq() == first.seq

    store.clear()
    assert store.since(0) == [], "内容应被清空"

    # 清空后新产生的行，序号必须仍然大于清空前已消费的值
    second = store.add("b", "final")
    assert second.seq > first.seq, "clear 后序号必须继续递增，不能归零"
    assert [l["text"] for l in store.since(first.seq)] == ["b"]


def test_seq_monotonic_across_store_recreated():
    """会话重建（新建 TranscriptStore）后序号也不能倒退。

    后端每次 start 都可能新建会话与 store；若序号各自从 1 开始，
    前端已推进到 N 之后就会永远拉不到新内容。
    """
    from services.audio_transcribe import TranscriptStore

    s1 = TranscriptStore()
    a = s1.add("旧会话", "final")
    b = s1.add("旧会话2", "final")

    # 模拟会话重建
    s2 = TranscriptStore()
    c = s2.add("新会话", "final")

    assert c.seq > b.seq, "新会话的序号必须大于旧会话"
    assert [l["text"] for l in s2.since(b.seq)] == ["新会话"]


# ══════════════════════════════════════════════════════════════
# 累积文本去重
# ══════════════════════════════════════════════════════════════
#
# STT 微服务的 partial/final 都是「累积全文」，每次断句都会把
# 已经推过的前缀再推一遍。不做归一化的话，前端会看到同一句话刷三遍。


@pytest.mark.parametrize(
    "prev,current,expected",
    [
        # 第一次：全是新增
        ("", "你好", "你好"),
        # 完全相同：重复推送，丢弃
        ("你好", "你好", ""),
        # 递增：只取新增部分
        ("你好", "你好世界", "世界"),
        ("你好世界", "你好世界再见", "再见"),
        # 回退（重识别导致变短）：等下一次完整输出
        ("你好世界", "你好", ""),
        # 不是前缀关系：当成全新内容
        ("你好", "完全不同的话", "完全不同的话"),
    ],
)
def test_new_suffix_dedup(prev, current, expected):
    from services.audio_transcribe import AudioTranscribeSession

    sess = AudioTranscribeSession()
    sess._last_text = prev
    assert sess._new_suffix(current) == expected


def test_dedup_across_full_sequence():
    """模拟真实推送序列：final 全文 + partial 全文 + final 全文"""
    from services.audio_transcribe import AudioTranscribeSession

    sess = AudioTranscribeSession()
    pushed = [
        "你好",
        "你好，請介紹一下你的項目經驗。",   # 变长 -> 取新增
        "你好，請介紹一下你的項目經驗。",   # 完全重复 -> 丢弃
        "你好，請介紹一下你的項目經驗。",   # 再重复 -> 丢弃
    ]

    kept = []
    for text in pushed:
        added = sess._new_suffix(text)
        if added:
            sess._last_text = text
            kept.append(added)

    assert kept == ["你好", "，請介紹一下你的項目經驗。"]
    # 拼起来应等于最终全文，没有重复
    assert "".join(kept) == "你好，請介紹一下你的項目經驗。"


# ══════════════════════════════════════════════════════════════
# final 必须无条件入库（曾导致「识别成功但从不发送」）
# ══════════════════════════════════════════════════════════════
#
# 回归背景：早期实现让 partial 与 final 共用同一个 _last_text 去重。
# 而 STT 常先推 partial("你好") 再推内容**完全相同**的 final("你好")，
# 于是 final 被判为「重复」丢弃 —— 库里只有 partial、一条 final 都没有。
# 前端只把 final 交给 AI，因此表现为「STT 明明识别出来了，
# 程序却从不发送」，日志里 since 长期停滞。


class _FakeWS:
    """按顺序回放消息的假 WebSocket"""

    def __init__(self, messages):
        self._messages = [json.dumps(m) for m in messages]

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)


def _run_recv(messages):
    """把消息喂给 _recv_loop，返回收集到的 (kind, text)"""
    import asyncio

    from services.audio_transcribe import AudioTranscribeSession

    sess = AudioTranscribeSession()
    sess._ws = _FakeWS(messages)
    asyncio.run(sess._recv_loop())
    return [(l["kind"], l["text"]) for l in sess.store.since(0)]


def test_final_with_same_text_as_partial_is_kept():
    """partial 与 final 内容相同时，final 也必须入库

    这是最真实的形态：STT 先推 partial，紧接着推内容相同的 final。
    """
    got = _run_recv([
        {"type": "partial", "text": "你好"},
        {"type": "final", "text": "你好"},
    ])

    kinds = [k for k, _ in got]
    assert "final" in kinds, f"final 被丢弃了: {got}"


def test_final_always_kept_even_if_repeated():
    """重复的 final 也不做去重：它代表一句话结束，必须产出"""
    got = _run_recv([
        {"type": "final", "text": "请介绍一下你的项目经验"},
        {"type": "final", "text": "请介绍一下你的项目经验"},
    ])

    finals = [t for k, t in got if k == "final"]
    assert len(finals) == 2, f"final 被去重了: {got}"


def test_partial_still_deduplicated():
    """partial 仍要去重：STT 会反复推同样的内容，不去重会刷重复行"""
    got = _run_recv([
        {"type": "partial", "text": "你好"},
        {"type": "partial", "text": "你好"},          # 完全重复 -> 丢
        {"type": "partial", "text": "你好世界"},      # 变长 -> 取新增
    ])

    partials = [t for k, t in got if k == "partial"]
    assert partials == ["你好", "世界"], f"partial 去重异常: {got}"


def test_final_does_not_disturb_partial_cursor():
    """final 不应推进 partial 的前缀游标（两者语义不同）"""
    got = _run_recv([
        {"type": "partial", "text": "你好"},
        {"type": "final", "text": "你好，请你自我介绍"},
        # final 之后的新 partial 不应被 final 的文本影响
        {"type": "partial", "text": "你好，请说一下项目"},
    ])

    partials = [t for k, t in got if k == "partial"]
    # 游标基于上一条 partial("你好")，因此新增部分是「，请说一下项目」
    assert partials[-1] == "，请说一下项目", f"游标被 final 干扰: {partials}"


# ══════════════════════════════════════════════════════════════
# STT 地址推导
# ══════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "service_url,expected",
    [
        ("http://stt:8000", "ws://stt:8000/stream"),
        ("http://127.0.0.1:8000", "ws://127.0.0.1:8000/stream"),
        ("https://stt.example.com", "wss://stt.example.com/stream"),
        ("http://stt:8000/", "ws://stt:8000/stream"),
    ],
)
def test_stt_ws_url_derivation(monkeypatch, service_url, expected):
    """http(s) 服务地址要能正确转成 ws(s)"""
    from config import settings
    from services.audio_transcribe import AudioTranscribeSession

    monkeypatch.setattr(settings, "STT_WS_URL", "")
    monkeypatch.setattr(settings, "STT_SERVICE_URL", service_url)

    assert AudioTranscribeSession()._stt_ws_url() == expected


def test_stt_ws_url_uses_explicit_setting(monkeypatch):
    """显式配置 STT_WS_URL 时优先用它"""
    from config import settings
    from services.audio_transcribe import AudioTranscribeSession

    monkeypatch.setattr(settings, "STT_WS_URL", "ws://custom:9999/stream")
    assert AudioTranscribeSession()._stt_ws_url() == "ws://custom:9999/stream"


# ══════════════════════════════════════════════════════════════
# 路由
# ══════════════════════════════════════════════════════════════


@pytest.fixture
def enabled(monkeypatch):
    """打开系统音频开关（路由注册与 503 判断都依赖它）"""
    from config import settings

    monkeypatch.setattr(settings, "SYSTEM_AUDIO_ENABLED", True)
    return settings


def test_disabled_returns_503(client, monkeypatch):
    """总开关关闭时返回 503 并说明如何开启"""
    from config import settings

    monkeypatch.setattr(settings, "SYSTEM_AUDIO_ENABLED", False)

    resp = client.get("/system-audio/info")
    assert resp.status_code == 503
    assert "SYSTEM_AUDIO_ENABLED" in resp.json()["detail"]


def test_info_degrades_gracefully(client, enabled, monkeypatch):
    """不可用时返回 200 + available=False + 原因，而不是红色报错"""
    monkeypatch.setattr(sa, "IS_WINDOWS", False)

    resp = client.get("/system-audio/info")
    assert resp.status_code == 200

    body = resp.json()
    assert body["available"] is False
    assert "Windows" in body["error"]
    assert body["devices"] == []


def test_info_lists_devices(client, enabled, fake_soundcard, monkeypatch):
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    resp = client.get("/system-audio/info")
    assert resp.status_code == 200

    body = resp.json()
    assert body["available"] is True
    assert len(body["devices"]) == 2
    assert body["devices"][0]["is_default"] is True
    assert body["sample_rate"] == 16000
    assert body["running"] is False


def test_devices_endpoint(client, enabled, fake_soundcard, monkeypatch):
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    resp = client.get("/system-audio/devices")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_status_when_idle(client, enabled, monkeypatch):
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    resp = client.get("/system-audio/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running"] is False
    assert body["transcript_count"] == 0


def test_transcript_when_idle(client, enabled, monkeypatch):
    """没有会话时返回空列表，而不是报错"""
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    resp = client.get("/system-audio/transcript")
    assert resp.status_code == 200
    body = resp.json()
    assert body["lines"] == []
    assert body["latest_seq"] == 0


def test_clear_when_idle(client, enabled, monkeypatch):
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    resp = client.post("/system-audio/clear")
    assert resp.status_code == 200
    assert resp.json()["cleared"] is False


def test_stop_when_idle_is_ok(client, enabled, monkeypatch):
    """重复 stop 应当幂等，不报错"""
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    resp = client.post("/system-audio/stop")
    assert resp.status_code == 200
    assert resp.json()["running"] is False


def test_start_rejects_bad_device(client, enabled, monkeypatch):
    """设备不存在时返回 400（用户侧问题），而不是 500"""
    monkeypatch.setattr(sa, "IS_WINDOWS", True)
    monkeypatch.setattr(sa, "SC_AVAILABLE", True)
    monkeypatch.setattr(
        sa, "sc",
        types.SimpleNamespace(
            all_speakers=lambda: [types.SimpleNamespace(id="a", name="A")],
            default_speaker=lambda: types.SimpleNamespace(id="a", name="A"),
            get_microphone=lambda device_id, include_loopback=True: None,
        ),
    )

    resp = client.post("/system-audio/start", json={"device_id": "ghost"})
    assert resp.status_code == 400
    assert "找不到指定的音频设备" in resp.json()["detail"]


def test_start_and_stop_roundtrip(client, enabled, fake_soundcard, monkeypatch):
    """完整的 start → status → transcript → stop 流程"""
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    # STT 连得上连不上都不能阻断捕获：连不上时只记录 stt_error。
    # 这里不断言 stt_connected 的具体取值 —— 它取决于本机 8001
    # 上是否恰好跑着 STT 服务，断言会把测试变成环境相关的。
    resp = client.post("/system-audio/start", json={})
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["running"] is True
    # 展示名用扬声器名（用户视角），而不是 soundcard 的内部回环名
    assert body["device"] == "默认扬声器"
    assert body["sample_rate"] == 16000
    # 字段必须存在；连接失败时要给出原因，成功时为 None
    assert "stt_connected" in body
    if not body["stt_connected"]:
        assert body["stt_error"], "未连上 STT 时必须说明原因"

    st = client.get("/system-audio/status").json()
    assert st["running"] is True

    tr = client.get("/system-audio/transcript").json()
    assert tr["running"] is True
    assert isinstance(tr["lines"], list)

    stop = client.post("/system-audio/stop")
    assert stop.status_code == 200
    assert stop.json()["running"] is False

    # 停止后状态应立刻反映
    assert client.get("/system-audio/status").json()["running"] is False


def test_clear_after_start(client, enabled, fake_soundcard, monkeypatch):
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    client.post("/system-audio/start", json={})
    try:
        resp = client.post("/system-audio/clear")
        assert resp.status_code == 200
        assert resp.json()["cleared"] is True
    finally:
        client.post("/system-audio/stop")


# ══════════════════════════════════════════════════════════════
# start 的幂等性
# ══════════════════════════════════════════════════════════════
#
# 界面重挂载（路由切换、React StrictMode 的挂载-卸载-再挂载、
# persist 水合）都会再调一次 start。早期实现每次都把旧会话停掉重建，
# 导致捕获被反复拆装：日志里密集的「已停止 / 已启动」，
# 且每次都丢失已识别的文字。


def test_repeated_start_reuses_session(client, enabled, fake_soundcard, monkeypatch):
    """连续多次 start 不应重建捕获（秒数持续增长而非归零）"""
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    client.post("/system-audio/stop")
    first = client.post("/system-audio/start", json={})
    assert first.status_code == 200, first.text

    # 给捕获一点时间累积
    import time

    time.sleep(0.4)
    elapsed_before = client.get("/system-audio/status").json()["seconds"]
    assert elapsed_before > 0

    # 再调三次（模拟重挂载）
    for _ in range(3):
        again = client.post("/system-audio/start", json={})
        assert again.status_code == 200
        assert again.json()["running"] is True

    elapsed_after = client.get("/system-audio/status").json()["seconds"]
    # 关键断言：秒数没有被重置。若每次 start 都重建，这里会回到接近 0
    assert elapsed_after >= elapsed_before, (
        f"重复 start 重建了捕获会话（{elapsed_before} -> {elapsed_after}）"
    )

    client.post("/system-audio/stop")


def test_start_with_different_device_restarts(client, enabled, monkeypatch):
    """指定了不同的设备时才允许重建"""
    monkeypatch.setattr(sa, "IS_WINDOWS", True)

    mic = _FakeMic()
    speakers = [
        types.SimpleNamespace(id="spk-a", name="A 扬声器"),
        types.SimpleNamespace(id="spk-b", name="B 扬声器"),
    ]
    monkeypatch.setattr(sa, "SC_AVAILABLE", True)

    def _get_mic(device_id, include_loopback=True):
        # 只认识 spk-a / spk-b，其它视为不存在
        return mic if device_id in ("spk-a", "spk-b") else None

    monkeypatch.setattr(
        sa, "sc",
        types.SimpleNamespace(
            all_speakers=lambda: speakers,
            default_speaker=lambda: speakers[0],
            get_microphone=_get_mic,
        ),
    )

    client.post("/system-audio/stop")
    r1 = client.post("/system-audio/start", json={"device_id": "spk-a"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["device"] == "A 扬声器"

    # 换设备 → 应切换到新设备
    r2 = client.post("/system-audio/start", json={"device_id": "spk-b"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["device"] == "B 扬声器"

    client.post("/system-audio/stop")