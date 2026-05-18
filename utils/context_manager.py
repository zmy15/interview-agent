"""上下文窗口管理 — 基于 LangChain trim_messages + tiktoken"""

from typing import Union

import tiktoken
from langchain_core.messages import (
    trim_messages as lc_trim_messages,
    SystemMessage,
    HumanMessage,
    AIMessage,
    BaseMessage,
)

from models.schemas import Message

# tiktoken 编码器（cl100k_base 与 DeepSeek/OpenAI 兼容）
_encoding = tiktoken.get_encoding("cl100k_base")


def estimate_tokens(text: str) -> int:
    """使用 tiktoken 精确计算 token 数（替代旧版字符数/2 估算）"""
    if not text:
        return 0
    return len(_encoding.encode(text))


def count_messages_tokens(messages: list[Union[Message, dict]]) -> int:
    """计算消息列表的精确 token 总数"""
    total = 0
    for msg in messages:
        if isinstance(msg, dict):
            content = msg.get("content", "")
        elif hasattr(msg, "content"):
            content = msg.content
        else:
            content = str(msg)
        total += estimate_tokens(content)
        # 每条消息额外开销约 4 tokens（role + 格式）
        total += 4
    return total


def _to_langchain_message(msg: Union[Message, dict]) -> BaseMessage:
    """将内部消息格式转换为 LangChain BaseMessage"""
    if isinstance(msg, dict):
        role = msg.get("role", "user")
        content = msg.get("content", "")
    elif hasattr(msg, "role"):
        role = msg.role
        content = getattr(msg, "content", "")
    else:
        role = "user"
        content = str(msg)

    if role == "system":
        return SystemMessage(content=content)
    elif role == "assistant":
        return AIMessage(content=content)
    else:
        return HumanMessage(content=content)


def _from_langchain_message(msg: BaseMessage) -> dict:
    """将 LangChain BaseMessage 转换回内部 dict 格式"""
    if isinstance(msg, SystemMessage):
        return {"role": "system", "content": msg.content}
    elif isinstance(msg, AIMessage):
        return {"role": "assistant", "content": msg.content}
    else:
        return {"role": "user", "content": msg.content}


def trim_messages(
    messages: list[Union[Message, dict]],
    max_tokens: int = 6000,
) -> list[Union[Message, dict]]:
    """
    使用 LangChain trim_messages 裁剪消息列表。

    策略：保留所有 system 消息 + 最近 N 条对话消息，总 token 数不超过 max_tokens。
    """
    if not messages:
        return messages

    # 转换为 LangChain 消息格式
    lc_messages = [_to_langchain_message(m) for m in messages]

    # 使用 LangChain 内置裁剪
    trimmed = lc_trim_messages(
        lc_messages,
        max_tokens=max_tokens,
        token_counter=_encoding,
        strategy="last",
        start_on="human",
        include_system=True,
    )

    # 转换回原始格式
    return [_from_langchain_message(m) for m in trimmed]
