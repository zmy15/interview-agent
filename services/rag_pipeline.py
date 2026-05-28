"""RAG 检索管线 — 基于 LangChain LCEL (LangChain Expression Language)"""

import logging
from typing import Optional

from langchain_core.runnables import RunnableLambda

from config import settings

logger = logging.getLogger(__name__)


def _extract_doc_info(doc) -> dict:
    """从 Document/dict 中提取 content, score, metadata"""
    if hasattr(doc, "page_content"):
        content = doc.page_content
        meta = doc.metadata if hasattr(doc, "metadata") else {}
        score = meta.get("score", 0) if isinstance(meta, dict) else 0
    elif isinstance(doc, dict):
        content = doc.get("content", "")
        meta = doc.get("metadata", {})
        score = doc.get("score", 0)
    else:
        content = str(doc)
        meta = {}
        score = 0
    return {"content": content, "score": score, "metadata": meta}


def format_rag_docs(docs: list) -> str:
    """
    将检索到的文档格式化为上下文字符串（LangChain 风格）。

    支持两种输入格式：
    1. LangChain Document 对象列表（有 page_content 属性）
    2. dict 列表（有 content 键，兼容旧格式）

    Returns:
        格式化的参考知识库上下文字符串
    """
    if not docs:
        return ""

    parts = []
    for i, doc in enumerate(docs):
        info = _extract_doc_info(doc)
        content = info["content"]
        score = info["score"]

        # 日志：每条检索结果的摘要
        preview = content[:120].replace("\n", " ").strip()
        source = info["metadata"].get("source", "?") if isinstance(info["metadata"], dict) else "?"
        logger.info(
            "RAG hit #%d | score=%.4f | source=%s | preview=%s...",
            i + 1, score, source, preview
        )

        parts.append(f"[{i + 1}] (相关度: {score:.3f})\n{content}")

    if not parts:
        return ""

    return "\n\n---\n参考知识库：\n" + "\n\n".join(parts)


def create_rag_retriever(position_name: str, top_k: Optional[int] = None):
    """
    创建 LangChain 兼容的检索器（基于 FAISS 向量存储）。

    使用 LCEL RunnableLambda 包装 VectorStoreManager.search()，
    使检索器可以无缝接入 LangChain Chain。

    Args:
        position_name: 岗位名称
        top_k: 检索数量，默认使用配置值

    Returns:
        LangChain Runnable: 输入 query 字符串，输出 Document 列表
    """
    from services.vector_store import VectorStoreManager

    k = top_k or settings.VECTOR_SEARCH_TOP_K
    vms = VectorStoreManager(settings)

    def retrieve(query: str) -> list:
        """执行向量检索"""
        if not vms.available:
            logger.warning("Vector store not available, skipping RAG retrieval")
            return []
        try:
            results = vms.search(position_name, query, k)
            return results
        except Exception as e:
            logger.warning(f"RAG retrieval failed (non-blocking): {e}")
            return []

    # 包装为 LangChain Runnable
    return RunnableLambda(retrieve)


def build_rag_context(position_name: str, query: str, top_k: Optional[int] = None) -> str:
    """
    一站式 RAG 上下文构建：检索 + 格式化。

    检索岗位知识库（包含 FAQ、代码文档、项目文件等所有上传到该岗位的知识）。
    受 settings.RAG_ENABLED 开关控制，关闭时直接返回空字符串。

    Args:
        position_name: 岗位名称
        query: 用户查询（用于向量检索）
        top_k: 检索数量

    Returns:
        格式化的 RAG 上下文字符串，无结果时返回空字符串
    """
    if not position_name:
        return ""

    if not settings.RAG_ENABLED:
        logger.info("RAG is DISABLED — skipping retrieval")
        return ""

    k = top_k or settings.VECTOR_SEARCH_TOP_K

    # 日志：检索请求
    query_preview = query[:150].replace("\n", " ")
    logger.info(
        "RAG retrieval | position=%s | top_k=%d | query=%s",
        position_name, k, query_preview
    )

    from services.vector_store import VectorStoreManager

    vms = VectorStoreManager(settings)
    if not vms.available:
        logger.warning("Vector store not available, skipping RAG retrieval")
        return ""

    # 检索岗位知识库
    try:
        kb_results = vms.search(position_name, query, k)
    except Exception as e:
        logger.warning("RAG search failed (non-blocking): %s", e)
        kb_results = []

    if not kb_results:
        logger.info("RAG retrieval | position=%s | 0 hits", position_name)
        return ""

    logger.info("RAG retrieval | position=%s | %d hits total", position_name, len(kb_results))
    context = format_rag_docs(kb_results)
    return context
