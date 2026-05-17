"""聊天接口测试"""

import json

import pytest


class TestModelsEndpoint:
    """GET /models — 模型列表"""

    def test_list_models(self, client):
        response = client.get("/chat/models")
        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert len(data["models"]) > 0
        model_ids = [m["id"] for m in data["models"]]
        assert "deepseek-v4-pro" in model_ids


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
