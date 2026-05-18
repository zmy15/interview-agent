"""文档分块服务 — LangChain Text Splitters + 自定义 Q&A/代码模式"""

import re

from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_faq_document(text: str) -> list[str]:
    """
    尝试识别 Q&A 模式分块，失败则回退到滑动窗口。
    支持的 Q&A 模式：Q:, 问：, Q1., 1., 等
    """
    # 尝试多种 Q&A 模式
    qa_patterns = [
        r"(?:Q\d*\s*[:：.。]\s*|问\d*\s*[:：.。]\s*|问题\d*\s*[:：.。]\s*)",  # Q: / 问：/ 问题1：
        r"(?:Q&A\s*\d+)",  # Q&A 1
        r"(?:\d+[.、]\s*)",  # 1. / 1、
    ]

    best_chunks = []

    for pattern in qa_patterns:
        # 找到所有 Q&A 起始位置
        matches = list(re.finditer(pattern, text, re.IGNORECASE))
        if len(matches) >= 2:
            chunks = []
            for i, match in enumerate(matches):
                start = match.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                chunk_text = text[start:end].strip()
                if chunk_text:
                    chunks.append(chunk_text)
            if len(chunks) > len(best_chunks):
                best_chunks = chunks

    if best_chunks and len(best_chunks) >= 2:
        # 合并太小的 chunk（仅当 chunk 数过多且单个 chunk 极小时才合并）
        avg_len = sum(len(c) for c in best_chunks) / len(best_chunks)
        if avg_len < 80 and len(best_chunks) > 3:
            merged = []
            buf = ""
            for c in best_chunks:
                if len(buf) + len(c) < 500:
                    buf += ("\n" + c) if buf else c
                else:
                    if buf:
                        merged.append(buf)
                    buf = c
            if buf:
                merged.append(buf)
            return merged if merged else best_chunks
        return best_chunks

    # 回退到滑动窗口
    return chunk_by_size(text)


def chunk_code_document(text: str) -> list[str]:
    """按函数/类边界或固定大小切分代码"""
    # 尝试按函数/类定义分割
    func_pattern = r"(?:(?:async\s+)?def\s+\w+|class\s+\w+|public\s+(?:static\s+)?(?:void|int|string|bool|var|\w+)\s+\w+\s*\()"
    matches = list(re.finditer(func_pattern, text))
    if len(matches) >= 2:
        chunks = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(chunk_text)
        return chunks if chunks else chunk_by_size(text, chunk_size=1000, overlap=200)

    return chunk_by_size(text, chunk_size=1000, overlap=200)


def chunk_by_size(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """按字符数滑动窗口分块（保留兼容性）"""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(chunk_text)
        start += (chunk_size - overlap)
    return chunks


# ========== LangChain Text Splitters（推荐使用） ==========

# FAQ 文档分句分块器
_faq_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100,
    separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", " ", ""],
)

# 代码文档分块器
_code_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=[
        "\nclass ", "\ndef ", "\nasync def ",
        "\npublic ", "\nprivate ", "\nprotected ",
        "\n\n", "\n", " ", ""
    ],
)

# 通用分块器
_generic_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100,
)


def chunk_document_langchain(text: str, doc_type: str) -> list[str]:
    """
    使用 LangChain RecursiveCharacterTextSplitter 进行智能分块。

    与 chunk_document() 的区别：
    - FAQ 文档：优先使用自定义 Q&A 模式匹配，失败后使用 LangChain splitter
    - 代码文档：优先使用自定义函数/类边界匹配，失败后使用 LangChain splitter
    - 其他类型：直接使用 LangChain splitter

    Args:
        text: 文档原始文本
        doc_type: "faq" / "code" / 其他

    Returns:
        分块后的文本列表
    """
    if doc_type == "faq":
        # 优先使用 Q&A 模式匹配
        chunks = chunk_faq_document(text)
        if len(chunks) >= 2:
            return chunks
        return _faq_splitter.split_text(text)

    elif doc_type == "code":
        # 优先使用函数/类边界匹配
        chunks = chunk_code_document(text)
        if chunks:
            return chunks
        return _code_splitter.split_text(text)

    else:
        return _generic_splitter.split_text(text)


def chunk_document(text: str, doc_type: str) -> list[str]:
    """
    统一分块入口（向后兼容）。
    内部委托给 chunk_document_langchain()。

    doc_type: "faq" / "code" / 其他
    """
    return chunk_document_langchain(text, doc_type)
