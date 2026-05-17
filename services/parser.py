"""文档解析服务 — PDF / Word / 代码文件"""

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 延迟导入，避免缺失依赖时阻止模块加载

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """使用 PyMuPDF (fitz) 解析 PDF"""
    import fitz  # pymupdf
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text_parts = []
    for page in doc:
        text = page.get_text()
        if text:
            text_parts.append(text)
    doc.close()
    return "\n".join(text_parts)


def extract_text_from_docx(file_bytes: bytes) -> str:
    """使用 python-docx 解析 Word 文档"""
    from docx import Document
    doc = Document(io.BytesIO(file_bytes))
    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text)
    return "\n".join(paragraphs)


def extract_text_from_txt(file_bytes: bytes) -> str:
    """解析纯文本文件，自动处理编码"""
    # 优先尝试常见中文编码，UTF-16 放在最后以避免误识别
    for encoding in ["utf-8", "gbk", "gb2312", "utf-16", "latin-1"]:
        try:
            return file_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return file_bytes.decode("utf-8", errors="replace")


def extract_code(file_bytes: bytes) -> str:
    """解析代码文件"""
    return extract_text_from_txt(file_bytes)


# 支持的文件扩展名
RESUME_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".cpp", ".c",
    ".h", ".hpp", ".rs", ".rb", ".php", ".swift", ".kt", ".scala",
    ".cs", ".vue", ".html", ".css", ".scss", ".sql", ".sh", ".bash",
    ".yaml", ".yml", ".json", ".xml", ".md", ".r", ".m",
}


def parse_file(file_bytes: bytes, filename: str) -> str:
    """
    统一文件解析入口。
    根据扩展名分发到不同的解析器。
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext in (".docx", ".doc"):
        return extract_text_from_docx(file_bytes)
    elif ext == ".txt":
        return extract_text_from_txt(file_bytes)
    elif ext in CODE_EXTENSIONS:
        return extract_code(file_bytes)
    else:
        # 尝试作为文本文件解析
        return extract_text_from_txt(file_bytes)
