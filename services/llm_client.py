"""DeepSeek LLM 客户端 — 流式对话 + 报告生成"""

import logging
from typing import AsyncGenerator, Optional

import openai
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

# 全局客户端
_client: Optional[AsyncOpenAI] = None


def get_client(api_key: Optional[str] = None) -> AsyncOpenAI:
    """获取 OpenAI 客户端。如果提供 api_key，则使用该 key 创建新客户端；否则复用全局客户端。"""
    global _client
    if api_key:
        return AsyncOpenAI(
            api_key=api_key,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    return _client


async def stream_chat(
    messages: list[dict],
    model: Optional[str] = None,
    thinking_enabled: Optional[bool] = None,
    reasoning_effort: Optional[str] = None,
    api_key: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """
    流式调用 DeepSeek，yield 统一格式 dict：
    - {"type": "reasoning", "content": "..."}  思考链
    - {"type": "content", "content": "..."}    最终回答
    - {"type": "done", "content": ""}          结束
    """
    client = get_client(api_key=api_key)
    _model = model or settings.DEEPSEEK_MODEL
    _thinking = thinking_enabled if thinking_enabled is not None else settings.DEEPSEEK_THINKING_ENABLED
    _effort = reasoning_effort or settings.DEEPSEEK_REASONING_EFFORT

    # 将 Pydantic models 转为 dict
    msgs = []
    for m in messages:
        if hasattr(m, "model_dump"):
            msgs.append(m.model_dump())
        elif isinstance(m, dict):
            msgs.append(m)
        else:
            msgs.append({"role": getattr(m, "role", "user"), "content": getattr(m, "content", str(m))})

    extra_body = {}
    if _thinking:
        extra_body["thinking"] = {"type": "enabled"}
        extra_body["reasoning_effort"] = _effort

    try:
        stream = await client.chat.completions.create(
            model=_model,
            messages=msgs,
            stream=True,
            extra_body=extra_body if extra_body else None,
        )

        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta

                # 思考模式的 reasoning_content
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield {"type": "reasoning", "content": reasoning}

                # 正常 content
                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "content", "content": content}

            # 检查是否结束
            if chunk.choices and chunk.choices[0].finish_reason:
                yield {"type": "done", "content": ""}
                return

        yield {"type": "done", "content": ""}

    except openai.APIError as e:
        logger.error(f"DeepSeek API error: {e}")
        yield {"type": "error", "content": f"API 调用失败: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in stream_chat: {e}")
        yield {"type": "error", "content": f"发生错误: {str(e)}"}


async def generate_report(
    messages: list[dict],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """非流式调用，用于报告生成"""
    client = get_client(api_key=api_key)
    _model = model or settings.DEEPSEEK_MODEL

    msgs = []
    for m in messages:
        if hasattr(m, "model_dump"):
            msgs.append(m.model_dump())
        elif isinstance(m, dict):
            msgs.append(m)
        else:
            msgs.append({"role": getattr(m, "role", "user"), "content": getattr(m, "content", str(m))})

    try:
        response = await client.chat.completions.create(
            model=_model,
            messages=msgs,
            stream=False,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        return f"报告生成失败: {str(e)}"
