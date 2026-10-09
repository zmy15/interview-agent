"""
截图识别测试 — 整屏捕获、路由、参数校验、图像编码、视觉调用请求格式

设计原则：
    不依赖真实屏幕与真实 API Key。
    - 捕获层用 monkeypatch 替换成合成图片，保证测试在任何机器/CI 上稳定；
    - 视觉调用用假的 openai client，重点校验**请求体结构**是否符合
      官方规范（图片只能出现在 user 消息中，否则 API 返回 400）。
"""

import base64
import io
import types

import pytest
from PIL import Image

from services import screen_capture as sc


# ══════════════════════════════════════════════════════════════
# 辅助
# ══════════════════════════════════════════════════════════════


def _make_image(width: int = 800, height: int = 600) -> Image.Image:
    """生成一张有内容的测试图（纯色会被压缩得很小，不利于校验体积）"""
    img = Image.new("RGB", (width, height), "white")
    for x in range(0, width, 40):
        for y in range(0, height, 40):
            img.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
    return img


@pytest.fixture
def fake_capture(monkeypatch):
    """把捕获替换成合成图，避免依赖真实屏幕"""
    monkeypatch.setattr(sc, "is_available", lambda: True)
    monkeypatch.setattr(sc, "availability_error", lambda: "")

    def _grab_screen(**kwargs):
        return _make_image()

    monkeypatch.setattr(sc, "grab_screen", _grab_screen)
    return monkeypatch


@pytest.fixture
def fake_vision(monkeypatch):
    """替换 DeepSeek 客户端，记录请求体以便校验"""
    captured: dict = {}

    class _Completions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            msg = types.SimpleNamespace(
                content="## 识别到的题目\n测试题\n\n## 答案\n测试答案",
                reasoning_content="",
            )
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=msg, finish_reason="stop")],
                usage=types.SimpleNamespace(prompt_tokens=800, completion_tokens=30),
            )

    class _Models:
        async def list(self):
            return types.SimpleNamespace(
                data=[types.SimpleNamespace(id="deepseek-flash")]
            )

    class _Client:
        def __init__(self):
            self.chat = types.SimpleNamespace(completions=_Completions())
            self.models = _Models()

    client = _Client()

    import services.llm_client as llm

    monkeypatch.setattr(llm, "get_client", lambda api_key=None: client)
    sc.invalidate_model_cache()

    return captured


# ══════════════════════════════════════════════════════════════
# 图像编码
# ══════════════════════════════════════════════════════════════


def test_encode_image_returns_png_data_url():
    """编码结果是合法的 PNG data URL"""
    img = _make_image(400, 300)
    data_url, raw = sc.encode_image(img, max_edge=1280)

    assert data_url.startswith("data:image/png;base64,")
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    b64 = data_url.split(",", 1)[1]
    assert base64.b64decode(b64) == raw


def test_encode_image_resizes_to_max_edge():
    """超过最长边时按比例缩小，且保持宽高比"""
    img = _make_image(3000, 1500)
    _, raw = sc.encode_image(img, max_edge=1000)

    decoded = Image.open(io.BytesIO(raw))
    assert max(decoded.size) == 1000
    assert abs(decoded.size[0] / decoded.size[1] - 2.0) < 0.02


def test_encode_image_keeps_small_image():
    """小于上限的图片不放大"""
    img = _make_image(300, 200)
    _, raw = sc.encode_image(img, max_edge=1280)
    assert Image.open(io.BytesIO(raw)).size == (300, 200)


def test_encode_large_primary_screen_stays_under_limits():
    """2560x1440 这类真实主屏尺寸应能顺利编码（缩放后体积可控）"""
    img = _make_image(2560, 1440)
    data_url, raw = sc.encode_image(img, max_edge=1280)
    decoded = Image.open(io.BytesIO(raw))
    assert max(decoded.size) == 1280
    # 官方单图上限 32MiB，这里应远低于
    assert len(raw) < 8 * 1024 * 1024


# ══════════════════════════════════════════════════════════════
# 显示器与整屏捕获
# ══════════════════════════════════════════════════════════════


def test_list_monitors_shape():
    """显示器列表结构完整，且只包含主显示器"""
    monitors = sc.list_monitors()
    if not sc.IS_WINDOWS:
        assert monitors == []
        return

    assert isinstance(monitors, list)
    for m in monitors:
        assert set(m) >= {"id", "name", "x", "y", "width", "height"}
        assert m["width"] > 0 and m["height"] > 0
        assert m["id"] in {"all", "primary"}


def test_list_monitors_returns_primary_only():
    """只提供主显示器一个目标"""
    monitors = sc.list_monitors()
    if not sc.IS_WINDOWS:
        assert monitors == []
        return

    assert len(monitors) == 1
    m = monitors[0]
    assert m["id"] == "primary"
    assert m["width"] > 0 and m["height"] > 0
    assert m["x"] == 0 and m["y"] == 0


def test_primary_size_matches_capture():
    """主显示器尺寸指标应与实际捕获结果一致（不缩放、无裁切）"""
    if not sc.is_available():
        pytest.skip("当前环境不支持截图")

    pw, ph = sc.primary_size()
    img = sc.grab_screen()
    assert img.size == (pw, ph)


def test_grab_screen_returns_image():
    """真实截图应返回一张正常的图"""
    if not sc.is_available():
        pytest.skip("当前环境不支持截图")

    img = sc.grab_screen()
    assert img.mode == "RGB"
    assert img.width > 0 and img.height > 0


def test_grab_screen_has_real_content():
    """截图不应是纯色（否则说明捕获没拿到画面）"""
    if not sc.is_available():
        pytest.skip("当前环境不支持截图")

    img = sc.grab_screen()
    colors = img.getcolors(maxcolors=100000)
    # getcolors 返回 None 表示颜色数超过上限，说明内容很丰富
    assert colors is None or len(colors) > 50


def test_capture_monitor_rejects_zero_index():
    """monitor_index 从 1 开始，0 属于非法值"""
    if not sc.is_available():
        pytest.skip("当前环境不支持截图")

    with pytest.raises(sc.CaptureError) as exc:
        sc.capture_monitor(0)
    assert "1" in str(exc.value)


def test_grab_screen_unavailable_raises(monkeypatch):
    """不可用时应抛 CaptureError 而不是崩溃"""
    monkeypatch.setattr(sc, "is_available", lambda: False)
    monkeypatch.setattr(sc, "availability_error", lambda: "缺少 pillow")
    with pytest.raises(sc.CaptureError) as exc:
        sc.grab_screen()
    assert "pillow" in str(exc.value)


# ══════════════════════════════════════════════════════════════
# 路由：截图信息
# ══════════════════════════════════════════════════════════════


def test_info_reports_unavailable_gracefully(client, monkeypatch):
    """不可用时返回 200 + available=False + 原因，而不是报错"""
    monkeypatch.setattr(sc, "is_available", lambda: False)
    monkeypatch.setattr(sc, "availability_error", lambda: "缺少 pillow")

    resp = client.get("/screenshot/info")
    assert resp.status_code == 200

    body = resp.json()
    assert body["available"] is False
    assert "pillow" in body["error"]
    assert body["monitors"] == []


def test_info_returns_monitors(client, monkeypatch):
    """正常时返回截图目标（仅主显示器）"""
    monkeypatch.setattr(sc, "is_available", lambda: True)
    monkeypatch.setattr(
        sc, "list_monitors",
        lambda: [{"id": "primary", "name": "主显示器（2560×1440）",
                  "x": 0, "y": 0, "width": 2560, "height": 1440}],
    )

    resp = client.get("/screenshot/info")
    assert resp.status_code == 200

    body = resp.json()
    assert body["available"] is True
    assert len(body["monitors"]) == 1
    assert body["monitors"][0]["id"] == "primary"
    assert body["monitors"][0]["width"] == 2560


# ══════════════════════════════════════════════════════════════
# 路由：截图识别
# ══════════════════════════════════════════════════════════════


def test_capture_uses_primary_monitor(client, fake_capture, fake_vision):
    """截图固定使用主显示器"""
    resp = client.post("/screenshot/capture", json={"save": False})
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["monitor"] == "primary"
    assert body["model"] == "deepseek-flash"
    assert body["answer"]
    assert body["width"] == 800 and body["height"] == 600
    assert body["image_bytes"] > 0
    assert body["image_path"] is None


def test_capture_ignores_monitor_field(client, fake_capture, fake_vision, monkeypatch):
    """即使传入 monitor 也应固定截主显示器（该参数已废弃）"""
    seen = {}

    def _spy(**kwargs):
        seen.update(kwargs)
        return _make_image()

    monkeypatch.setattr(sc, "grab_screen", _spy)

    resp = client.post(
        "/screenshot/capture",
        json={"save": False, "monitor": "2"},
    )
    assert resp.status_code == 200, resp.text
    # 捕获层不应收到任何显示器参数
    assert "monitor" not in seen
    assert resp.json()["monitor"] == "primary"


def test_capture_request_body_matches_deepseek_spec(client, fake_capture, fake_vision):
    """请求体必须符合 DeepSeek 图像理解规范"""
    resp = client.post(
        "/screenshot/capture",
        json={"save": False, "prompt": "只给答案"},
    )
    assert resp.status_code == 200, resp.text

    msgs = fake_vision["messages"]
    assert fake_vision["model"] == "deepseek-flash"

    # 1) 图片只能出现在 user 消息中（放 system/assistant 会返回 400）
    for m in msgs:
        if isinstance(m["content"], list):
            assert m["role"] == "user", f"图片出现在 {m['role']} 消息里，API 会返回 400"

    user_msgs = [m for m in msgs if m["role"] == "user"]
    assert user_msgs, "缺少 user 消息"

    blocks = user_msgs[-1]["content"]
    img_blocks = [b for b in blocks if b.get("type") == "image_url"]
    assert len(img_blocks) == 1
    assert img_blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")

    # 2) 文本块应带上用户填写的提问
    text_blocks = [b for b in blocks if b.get("type") == "text"]
    assert "只给答案" in text_blocks[0]["text"]

    # 3) system 提示词不能残留 "System: " 前缀
    sys_msgs = [m for m in msgs if m["role"] == "system"]
    assert sys_msgs, "应注入 system 提示词"
    assert not sys_msgs[0]["content"].startswith("System: ")
    assert "题目" in sys_msgs[0]["content"]


def test_capture_capture_failure_returns_400(client, monkeypatch, fake_vision):
    """截图失败应返回 400，而不是 500"""
    monkeypatch.setattr(sc, "is_available", lambda: True)

    def _boom(monitor="all", **kwargs):
        raise sc.CaptureError("BitBlt 拷贝屏幕失败")

    monkeypatch.setattr(sc, "grab_screen", _boom)

    resp = client.post("/screenshot/capture", json={"save": False})
    assert resp.status_code == 400
    assert "BitBlt" in resp.json()["detail"]


def test_capture_vision_failure_returns_502(client, fake_capture, monkeypatch):
    """模型侧失败（如无视觉模型）返回 502"""
    monkeypatch.setattr(sc, "is_available", lambda: True)
    monkeypatch.setattr(sc, "grab_screen", lambda *a, **k: _make_image())

    async def _boom(*args, **kwargs):
        raise sc.CaptureError("当前 API Key 下没有可用的视觉模型")

    monkeypatch.setattr(sc, "ask_vision", _boom)

    resp = client.post("/screenshot/capture", json={"save": False})
    assert resp.status_code == 502
    assert "视觉模型" in resp.json()["detail"]


def test_capture_passes_cursor_flag(client, fake_capture, fake_vision, monkeypatch):
    """include_cursor=true 时应把光标开关传给捕获层"""
    seen = {}

    def _spy(monitor="all", **kwargs):
        seen["monitor"] = monitor
        seen.update(kwargs)
        return _make_image()

    monkeypatch.setattr(sc, "grab_screen", _spy)

    resp = client.post("/screenshot/capture", json={"save": False, "include_cursor": True})
    assert resp.status_code == 200, resp.text
    assert seen.get("cursor") is True


def test_capture_disabled_returns_503(client, monkeypatch):
    """总开关关闭时返回 503 并说明原因"""
    from config import settings

    monkeypatch.setattr(settings, "SCREENSHOT_ENABLED", False)

    resp = client.post("/screenshot/capture", json={})
    assert resp.status_code == 503
    assert "SCREENSHOT_ENABLED" in resp.json()["detail"]

    resp = client.get("/screenshot/info")
    assert resp.status_code == 503


# ══════════════════════════════════════════════════════════════
# 思考模式与输出长度（回答被截断的回归测试）
# ══════════════════════════════════════════════════════════════


def test_vision_disables_thinking_by_default(client, fake_capture, fake_vision):
    """默认必须显式关闭思考模式。

    背景：DeepSeek 思考模式默认开启且 effort=high，思维链与正文共享
    max_tokens 预算，导致截图问答的正文被截断（写到一半突然中断）。
    因此请求体必须带上 thinking=disabled，不能依赖服务端默认值。
    """
    resp = client.post("/screenshot/capture", json={"save": False})
    assert resp.status_code == 200, resp.text

    extra = fake_vision.get("extra_body")
    assert extra, "必须传 extra_body，否则会走服务端默认（思考开启）"
    assert extra.get("thinking") == {"type": "disabled"}


def test_vision_can_enable_thinking(client, fake_capture, fake_vision, monkeypatch):
    """需要时可显式开启思考模式，并带上 reasoning_effort"""
    from config import settings

    monkeypatch.setattr(settings, "SCREENSHOT_THINKING_ENABLED", True)

    resp = client.post("/screenshot/capture", json={"save": False})
    assert resp.status_code == 200, resp.text

    extra = fake_vision["extra_body"]
    assert extra.get("thinking") == {"type": "enabled"}
    assert extra.get("reasoning_effort")


def test_vision_does_not_send_temperature(client, fake_capture, fake_vision):
    """思考模式下 temperature 会被忽略，不应再传（避免误导）"""
    resp = client.post("/screenshot/capture", json={"save": False})
    assert resp.status_code == 200, resp.text
    assert "temperature" not in fake_vision


def test_vision_max_tokens_is_generous(client, fake_capture, fake_vision):
    """输出预算应足够大，不能被推理挤光"""
    resp = client.post("/screenshot/capture", json={"save": False})
    assert resp.status_code == 200, resp.text
    assert fake_vision["max_tokens"] >= 4096


def test_truncated_answer_is_flagged(client, fake_capture, monkeypatch):
    """finish_reason=length 时应明确提示被截断，而不是假装回答完整"""
    import services.llm_client as llm
    from services import screen_capture as sc_mod

    class _TruncatedCompletions:
        async def create(self, **kwargs):
            msg = types.SimpleNamespace(content="## 答案\n写到一半就断了", reasoning_content="")
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=msg, finish_reason="length")],
                usage=types.SimpleNamespace(prompt_tokens=100, completion_tokens=8192),
            )

    class _Models:
        async def list(self):
            return types.SimpleNamespace(data=[types.SimpleNamespace(id="deepseek-flash")])

    class _Client:
        def __init__(self):
            self.chat = types.SimpleNamespace(completions=_TruncatedCompletions())
            self.models = _Models()

    monkeypatch.setattr(llm, "get_client", lambda api_key=None: _Client())
    sc_mod.invalidate_model_cache()

    resp = client.post("/screenshot/capture", json={"save": False})
    assert resp.status_code == 200, resp.text

    answer = resp.json()["answer"]
    assert "截断" in answer
    assert "SCREENSHOT_MAX_TOKENS" in answer