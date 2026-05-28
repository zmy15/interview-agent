"""LLM 客户端单元测试"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.llm_client import get_client, generate_report


# ============================================================
#  get_client — 客户端获取
# ============================================================

class TestGetClient:
    """获取 OpenAI 客户端"""

    def test_returns_new_client_with_api_key(self):
        """提供 api_key 时创建新客户端"""
        with patch("services.llm_client.AsyncOpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            client = get_client(api_key="sk-test-key")
            assert client is not None
            mock_openai.assert_called_once_with(
                api_key="sk-test-key",
                base_url=pytest.importorskip("config").settings.DEEPSEEK_BASE_URL,
            )

    def test_reuses_global_client(self):
        """无 api_key 时复用全局客户端"""
        import services.llm_client as llm
        llm._client = MagicMock()

        with patch("services.llm_client.AsyncOpenAI") as mock_openai:
            client = get_client()
            assert client is llm._client
            mock_openai.assert_not_called()

        llm._client = None  # 恢复

    def test_creates_global_client_on_first_call(self):
        """首次无 api_key 调用时创建全局客户端"""
        import services.llm_client as llm
        llm._client = None

        with patch("services.llm_client.AsyncOpenAI") as mock_openai:
            mock_openai.return_value = MagicMock()
            client = get_client()
            assert client is not None
            mock_openai.assert_called_once()

        llm._client = None


# ============================================================
#  辅助：收集异步生成器事件
# ============================================================

async def _collect_stream_events(messages, **kwargs):
    """收集 stream_chat 的所有事件"""
    from services.llm_client import stream_chat
    events = []
    async for event in stream_chat(messages, **kwargs):
        events.append(event)
    return events


# ============================================================
#  stream_chat — 流式对话（异步）
# ============================================================

class TestStreamChat:
    """流式聊天（异步生成器，通过 asyncio.run 运行）"""

    def test_yields_content_events(self):
        """正常流式响应 yield content 事件"""
        import services.llm_client as llm

        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock()
        mock_chunk.choices[0].delta.content = "你好"
        mock_chunk.choices[0].delta.reasoning_content = None
        mock_chunk.choices[0].finish_reason = None

        mock_stream = MagicMock()
        mock_stream.__aiter__.return_value = [mock_chunk]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)

        with patch.object(llm, "get_client", return_value=mock_client):
            events = asyncio.run(_collect_stream_events(
                [{"role": "user", "content": "你好"}]
            ))
            assert any(e["type"] in ("content", "done") for e in events)

    def test_yields_reasoning_events(self):
        """思考模式 yield reasoning 事件"""
        import services.llm_client as llm

        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock()
        mock_chunk.choices[0].delta.reasoning_content = "让我想想..."
        mock_chunk.choices[0].delta.content = None
        mock_chunk.choices[0].finish_reason = None

        mock_done_chunk = MagicMock()
        mock_done_chunk.choices = [MagicMock()]
        mock_done_chunk.choices[0].delta = MagicMock()
        mock_done_chunk.choices[0].delta.content = None
        mock_done_chunk.choices[0].delta.reasoning_content = None
        mock_done_chunk.choices[0].finish_reason = "stop"

        mock_stream = MagicMock()
        mock_stream.__aiter__.return_value = [mock_chunk, mock_done_chunk]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)

        with patch.object(llm, "get_client", return_value=mock_client):
            events = asyncio.run(_collect_stream_events(
                [{"role": "user", "content": "?"}],
                thinking_enabled=True,
            ))
            reasoning = [e for e in events if e["type"] == "reasoning"]
            assert len(reasoning) > 0
            assert reasoning[0]["content"] == "让我想想..."

    def test_handles_api_error(self):
        """API 错误时 yield error 事件"""
        import services.llm_client as llm
        from openai import APIError

        # 构造一个真实的 APIError 实例（需要 httpx.Request 参数）
        import httpx
        mock_request = httpx.Request("POST", "https://api.example.com")
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=APIError("服务不可用", request=mock_request, body=None)
        )

        with patch.object(llm, "get_client", return_value=mock_client):
            events = asyncio.run(_collect_stream_events(
                [{"role": "user", "content": "hi"}]
            ))
            errors = [e for e in events if e["type"] == "error"]
            assert len(errors) > 0
            assert "API 调用失败" in errors[0]["content"]

    def test_handles_generic_exception(self):
        """通用异常时 yield error 事件"""
        import services.llm_client as llm

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("未知错误")
        )

        with patch.object(llm, "get_client", return_value=mock_client):
            events = asyncio.run(_collect_stream_events(
                [{"role": "user", "content": "hi"}]
            ))
            errors = [e for e in events if e["type"] == "error"]
            assert len(errors) > 0
            assert "未知错误" in errors[0]["content"]

    def test_handles_pydantic_messages(self):
        """Pydantic model 消息被转为 dict"""
        import services.llm_client as llm

        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock()
        mock_chunk.choices[0].delta.content = "回答"
        mock_chunk.choices[0].delta.reasoning_content = None
        mock_chunk.choices[0].finish_reason = "stop"

        mock_stream = MagicMock()
        mock_stream.__aiter__.return_value = [mock_chunk]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)

        # 模拟 Pydantic model
        mock_msg = MagicMock()
        mock_msg.model_dump.return_value = {"role": "user", "content": "你好"}

        with patch.object(llm, "get_client", return_value=mock_client):
            events = asyncio.run(_collect_stream_events([mock_msg]))

            mock_client.chat.completions.create.assert_called_once()
            call_args = mock_client.chat.completions.create.call_args[1]
            assert call_args["messages"] == [{"role": "user", "content": "你好"}]


# ============================================================
#  generate_report — 报告生成
# ============================================================

class TestGenerateReport:
    """非流式报告生成"""

    def test_returns_report_content(self):
        """正常返回报告内容"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "面试报告：候选人表现优秀"

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("services.llm_client.get_client", return_value=mock_client):
            result = asyncio.run(generate_report([
                {"role": "system", "content": "生成报告"},
                {"role": "user", "content": "面试记录..."},
            ]))
            assert "候选人表现优秀" in result

    def test_handles_error(self):
        """生成失败返回错误信息"""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("生成失败")
        )

        with patch("services.llm_client.get_client", return_value=mock_client):
            result = asyncio.run(generate_report([{"role": "user", "content": "test"}]))
            assert "生成失败" in result

    def test_empty_response_returns_empty_string(self):
        """空响应返回空字符串"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("services.llm_client.get_client", return_value=mock_client):
            result = asyncio.run(generate_report([{"role": "user", "content": "test"}]))
            assert result == ""
