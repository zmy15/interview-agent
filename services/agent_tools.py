"""联网搜索工具 — DuckDuckGo"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_search_instance = None


def _get_ddgs():
    global _search_instance
    if _search_instance is None:
        try:
            from duckduckgo_search import DDGS
            _search_instance = DDGS()
        except ImportError:
            logger.warning("duckduckgo_search not installed")
            return None
    return _search_instance


def search_web(query: str, max_results: int = 5, timeout: int = 10) -> Optional[str]:
    """
    使用 DuckDuckGo 搜索网页。

    Args:
        query: 搜索关键词
        max_results: 最大结果数
        timeout: 超时秒数

    Returns:
        拼接的搜索结果字符串，失败返回 None
    """
    ddgs = _get_ddgs()
    if ddgs is None:
        return None

    try:
        results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return None

        parts = []
        for i, r in enumerate(results):
            title = r.get("title", "无标题")
            href = r.get("href", "")
            body = r.get("body", "")
            parts.append(f"[{i + 1}] {title}\n{body}\n来源: {href}")

        return "\n\n".join(parts)

    except Exception as e:
        logger.warning(f"Web search failed: {e}")
        return None
