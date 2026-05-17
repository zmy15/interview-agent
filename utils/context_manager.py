"""上下文窗口管理 — Token 估算与消息裁剪"""

from typing import Union

from models.schemas import Message


def estimate_tokens(text: str) -> int:
    """
    粗略估算 token 数。
    中文：约 1.5 字符/token；英文：约 4 字符/token。
    这里取折中：字符数 / 2。
    """
    if not text:
        return 0
    return max(1, len(text) // 2)


def count_messages_tokens(messages: list[Union[Message, dict]]) -> int:
    """计算消息列表的估算 token 总数"""
    total = 0
    for msg in messages:
        if isinstance(msg, dict):
            content = msg.get("content", "")
        elif hasattr(msg, "content"):
            content = msg.content
        else:
            content = str(msg)
        total += estimate_tokens(content)
    return total


def trim_messages(
    messages: list[Union[Message, dict]],
    max_tokens: int = 6000,
) -> list[Union[Message, dict]]:
    """
    裁剪消息列表，使其不超过 max_tokens。
    保留 system 消息 + 最近 N 条非 system 消息。
    """
    if not messages:
        return messages

    # 分离 system 消息
    system_msgs = []
    other_msgs = []

    for msg in messages:
        role = msg.get("role", "") if isinstance(msg, dict) else getattr(msg, "role", "")
        if role == "system":
            system_msgs.append(msg)
        else:
            other_msgs.append(msg)

    # system 消息 token 开销
    system_tokens = count_messages_tokens(system_msgs)
    available_tokens = max_tokens - system_tokens

    # 从后往前保留非 system 消息
    kept = []
    current_tokens = 0
    for msg in reversed(other_msgs):
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        msg_tokens = estimate_tokens(content)
        if current_tokens + msg_tokens <= available_tokens:
            kept.insert(0, msg)
            current_tokens += msg_tokens
        else:
            break

    return system_msgs + kept
