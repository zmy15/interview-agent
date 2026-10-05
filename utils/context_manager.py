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


class _TokenCounter:
    """tiktoken 编码器封装。

    说明：tiktoken.get_encoding() 在本地缓存缺失时会联网下载词表。
    离线 / 网络受限环境下会抛异常，因此这里做惰性加载 + 降级：
    加载失败时退化为「约 4 字符 = 1 token」的估算，保证服务仍可启动。
    """

    def __init__(self, name: str = "cl100k_base"):
        self._name = name
        self._encoding = None
        self._failed = False

    @property
    def encoding(self):
        if self._encoding is None and not self._failed:
            try:
                self._encoding = tiktoken.get_encoding(self._name)
            except Exception:
                # 离线环境：不阻塞启动，交由 estimate_tokens 走估算分支
                self._failed = True
        return self._encoding

    def encode(self, text: str) -> list:
        enc = self.encoding
        if enc is None:
            # 降级估算：中文约 1 字符≈0.6 token，英文约 4 字符≈1 token，
            # 取 1 字符 ≈ 0.7 token 作为保守估计
            return [0] * max(1, int(len(text) * 0.7))
        return enc.encode(text)


# tiktoken 编码器（cl100k_base 与 DeepSeek/OpenAI 兼容）
_encoding = _TokenCounter("cl100k_base")


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
    # 注意：新版 langchain_core 要求 token_counter 是 BaseChatModel 或 callable，
    # 不能直接传 tiktoken.Encoding 对象
    trimmed = lc_trim_messages(
        lc_messages,
        max_tokens=max_tokens,
        token_counter=count_messages_tokens,
        strategy="last",
        start_on="human",
        include_system=True,
    )

    # 转换回原始格式
    return [_from_langchain_message(m) for m in trimmed]
