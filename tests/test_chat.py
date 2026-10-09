"""聊天接口测试"""

import json

import pytest


class TestModelsEndpoint:
    """GET /models — 模型列表（由后端调用官方 /models 动态获取）"""

    def test_list_models(self, client, monkeypatch):
        response = client.get("/chat/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert len(data["models"]) > 0

        # 每个模型都要带视觉能力标记，前端据此决定能否截图答题
        for m in data["models"]:
            assert "supports_thinking" in m
            assert "supports_vision" in m

    def test_list_models_reflects_remote_api(self, client, monkeypatch):
        """模型列表来自官方接口，而不是代码里写死的清单"""
        import types

        import services.llm_client as llm
        from services import model_registry as registry

        class _Models:
            async def list(self):
                return types.SimpleNamespace(
                    data=[
                        types.SimpleNamespace(
                            id="some-future-model",
                            name="未来模型",
                            input_modalities=["text", "image"],
                        )
                    ]
                )

        class _Client:
            models = _Models()

        monkeypatch.setattr(llm, "get_client", lambda api_key=None: _Client())
        registry.invalidate_cache()

        response = client.get("/chat/models?refresh=true")
        assert response.status_code == 200
        models = response.json()["models"]
        assert [m["id"] for m in models] == ["some-future-model"]
        assert models[0]["supports_vision"] is True

    def test_list_models_falls_back_when_api_unavailable(self, client, monkeypatch):
        """远端不可用时回退到 AVAILABLE_MODELS，保证界面仍能选模型"""
        import services.llm_client as llm
        from services import model_registry as registry

        class _Models:
            async def list(self):
                raise RuntimeError("network unreachable")

        class _Client:
            models = _Models()

        monkeypatch.setattr(llm, "get_client", lambda api_key=None: _Client())
        registry.invalidate_cache()

        response = client.get("/chat/models?refresh=true")
        assert response.status_code == 200
        body = response.json()
        assert body["models"], "回退列表不能为空"
        assert body["source"] == "fallback"


class TestChatStream:
    """POST /chat/stream — SSE 流式对话"""

    def test_stream_basic(self, client):
        """基础流式对话测试"""
        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "messages": [{"role": "user", "content": "说一个字：好"}],
                "model": "deepseek-v4-flash",
                "thinking_enabled": False,
            },
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            # 读取 SSE 流
            events = []
            for line in response.iter_lines():
                if line:
                    decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        if data_str == "[DONE]":
                            events.append({"type": "done"})
                            break
                        try:
                            events.append(json.loads(data_str))
                        except json.JSONDecodeError:
                            pass

            # 至少有一条 content 或 error 事件（API key 无效时返回 error 事件）
            content_events = [e for e in events if e.get("type") == "content"]
            error_events = [e for e in events if e.get("type") == "error"]
            assert len(content_events) > 0 or len(error_events) > 0, \
                f"No content or error events in stream. Events: {events}"

    def test_stream_with_mode(self, client):
        """带 mode 参数的流式对话"""
        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "messages": [{"role": "user", "content": "你好"}],
                "mode": "interviewer",
                "model": "deepseek-v4-flash",
                "thinking_enabled": False,
            },
        ) as response:
            assert response.status_code == 200

    def test_stream_invalid_model(self, client):
        """使用无效模型名"""
        with client.stream(
            "POST",
            "/chat/stream",
            json={
                "messages": [{"role": "user", "content": "你好"}],
                "model": "invalid-model",
            },
        ) as response:
            assert response.status_code == 200  # SSE 连接建立
            # 流中应该有错误信息
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
            body_str = body.decode("utf-8")
            assert "不可用" in body_str or "error" in body_str
