"""稳定前缀缓存 — 让「prompt + 简历 + JD」在一次面试里只构建一次

为什么需要它
------------
发给模型的 messages 必须保持如下的字节顺序：

    系统指令 → 简历 → 岗位JD →（历史问答）→ 本轮尾部动态内容

服务端的前缀缓存（prompt caching）按 token 前缀匹配 KV：只要这一次请求的
前缀与上一次逐字节一致，就能复用已算好的 KV，省下重复的 prefill。
因此**每一轮请求里，system 消息必须是同一个字符串**。

而 system 的来源有两条路：

1. 前端把上一轮拿到的 system 原样回传（``req.system_fingerprint`` 匹配）；
2. 后端自己按指纹缓存一份（本模块）。

两条路都要求"同样的输入必然得到同样的输出"。模板里的静态文案、指导文本、
时间预算都由固定输入唯一决定，所以这一点成立；真正会漂移的只有两类东西：

* **RAG 检索结果** —— 每轮 query 不同，结果必然不同 → 一律放到尾部；
* **编程题 / 联网搜索** —— 取决于当前对话 → 也放到尾部。

本缓存不参与 token 裁剪（``trim_messages`` 会为了保住 system 把历史裁掉，
导致前缀变短、缓存失效）。system 是原样传递的，裁剪只发生在它之后的对话部分。

线程安全：路由跑在事件循环里，但截图的视觉问答跑在线程池中，所以这里加锁。
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Mapping, Optional

from config import settings
from utils.context_manager import estimate_tokens

logger = logging.getLogger(__name__)

# fingerprint -> (写入时间戳, system 文本, token 数)
_entries: "OrderedDict[str, tuple[float, str, int]]" = OrderedDict()
_lock = threading.Lock()


def signature(parts: Mapping[str, Any]) -> str:
    """由「整场面试期间不变」的请求字段算出指纹。

    调用方只需把那些字段塞进 dict：模式、岗位、JD id、简历、级别、轮次、
    补充说明、时间预算、题库、用户 id 等。指纹相同 ⇔ 这份 system 适用于同一场面试。

    注意：**不要把每轮变化的东西（RAG query、编程题、联网搜索）算进来**，
    否则指纹每轮都变，缓存永远不命中。
    """
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ttl_seconds() -> int:
    return int(getattr(settings, "PREFIX_CACHE_TTL_SECONDS", 1800))


def _max_tokens() -> int:
    return int(getattr(settings, "PREFIX_CACHE_MAX_TOKENS", 200000))


def _max_entries() -> int:
    return int(getattr(settings, "PREFIX_CACHE_MAX_ENTRIES", 64))


def get(fingerprint: str) -> Optional[str]:
    """取回缓存的前缀文本；未命中/已过期返回 None"""
    if not fingerprint:
        return None
    with _lock:
        entry = _entries.get(fingerprint)
        if entry is None:
            return None
        created_at, text, tokens = entry
        if time.time() - created_at > ttl_seconds():
            _entries.pop(fingerprint, None)
            logger.info("Prefix cache EXPIRED | fp=%s", fingerprint[:12])
            return None
        _entries.move_to_end(fingerprint)
    logger.info("Prefix cache HIT | fp=%s | %d chars / ~%d tokens", fingerprint[:12], len(text), tokens)
    return text


def put(fingerprint: str, text: str) -> None:
    """写入缓存。文本为空或超过 token 上限时跳过（宁可不缓存，也不打爆内存）"""
    if not fingerprint or not text:
        return
    tokens = estimate_tokens(text)
    limit = _max_tokens()
    if tokens > limit:
        logger.warning(
            "Prefix cache SKIP | fp=%s | ~%d tokens 超过上限 %d，不缓存（本场将每轮重建）",
            fingerprint[:12], tokens, limit,
        )
        return

    with _lock:
        _entries[fingerprint] = (time.time(), text, tokens)
        _entries.move_to_end(fingerprint)
        # 超出条目上限时淘汰最久未使用的
        while len(_entries) > _max_entries():
            old_fp, _ = _entries.popitem(last=False)
            logger.info("Prefix cache EVICT | fp=%s", old_fp[:12])
    logger.info("Prefix cache MISS→STORE | fp=%s | %d chars / ~%d tokens", fingerprint[:12], len(text), tokens)


def clear() -> None:
    """清空缓存（测试与热更新用）"""
    with _lock:
        _entries.clear()


def stats() -> dict:
    """当前缓存概况（调试用）"""
    with _lock:
        return {
            "entries": len(_entries),
            "tokens": sum(e[2] for e in _entries.values()),
        }
