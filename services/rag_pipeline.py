"""RAG 检索管线 — 基于 LangChain LCEL (LangChain Expression Language)"""

import logging
from typing import Optional

from langchain_core.runnables import RunnableLambda

from config import settings

logger = logging.getLogger(__name__)


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
        # 兼容 LangChain Document 和旧格式 dict
        if hasattr(doc, "page_content"):
            content = doc.page_content
        elif isinstance(doc, dict):
            content = doc.get("content", "")
        else:
            content = str(doc)

        # 兼容两种 score 格式
        if hasattr(doc, "metadata") and isinstance(doc.metadata, dict):
            score = doc.metadata.get("score", 0)
        elif isinstance(doc, dict):
            score = doc.get("score", 0)
        else:
            score = 0

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

    使用 LCEL 链：query → retriever → format_docs → context string

    Args:
        position_name: 岗位名称
        query: 用户查询（用于向量检索）
        top_k: 检索数量

    Returns:
        格式化的 RAG 上下文字符串，无结果时返回空字符串
    """
    if not position_name:
        return ""

    k = top_k or settings.VECTOR_SEARCH_TOP_K

    # 构建 LCEL 链：检索 → 格式化
    retriever = create_rag_retriever(position_name, k)

    # 链式调用
    try:
        docs = retriever.invoke(query)
        return format_rag_docs(docs)
    except Exception as e:
        logger.warning(f"RAG context build failed (non-blocking): {e}")
        return ""
