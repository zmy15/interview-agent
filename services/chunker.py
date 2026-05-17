"""文档分块服务 — Q&A 拆分 / 滑动窗口"""

import re


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
    """按字符数滑动窗口分块"""
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


def chunk_document(text: str, doc_type: str) -> list[str]:
    """
    统一分块入口。
    doc_type: "faq" / "code"
    """
    if doc_type == "faq":
        return chunk_faq_document(text)
    elif doc_type == "code":
        return chunk_code_document(text)
    else:
        return chunk_by_size(text)
