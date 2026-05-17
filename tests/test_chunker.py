"""文档分块器单元测试"""

from services.chunker import chunk_faq_document, chunk_code_document, chunk_by_size, chunk_document


class TestChunkBySize:
    """固定大小分块"""

    def test_small_text(self):
        text = "短文本"
        chunks = chunk_by_size(text, chunk_size=500)
        assert len(chunks) == 1
        assert chunks[0] == "短文本"

    def test_large_text(self):
        text = "A" * 1200
        chunks = chunk_by_size(text, chunk_size=500, overlap=100)
        assert len(chunks) >= 2
        # 所有 chunk 拼接后包含原文
        combined = "".join(chunks)
        assert len(combined) >= len(text) - 100  # 允许 overlap 导致的部分缺失

    def test_empty_text(self):
        chunks = chunk_by_size("")
        assert len(chunks) == 0


class TestChunkFAQ:
    """FAQ 分块"""

    def test_qa_pattern_q_colon(self):
        text = (
            "Q: 什么是 Python？\n"
            "A: Python 是一种编程语言。\n\n"
            "Q: 什么是 GIL？\n"
            "A: GIL 是全局解释器锁。"
        )
        chunks = chunk_faq_document(text)
        assert len(chunks) >= 2, f"Expected >= 2 chunks, got {len(chunks)}: {chunks}"

    def test_qa_pattern_chinese(self):
        text = (
            "问：什么是 FastAPI？\n"
            "答：FastAPI 是一个现代 Web 框架。\n\n"
            "问：如何安装？\n"
            "答：使用 pip install fastapi。"
        )
        chunks = chunk_faq_document(text)
        assert len(chunks) >= 2

    def test_fallback_to_size(self):
        """无法识别 Q&A 时回退到固定大小"""
        text = "这是一段普通的文本，没有任何问答格式。\n" * 50
        chunks = chunk_faq_document(text)
        assert len(chunks) > 0


class TestChunkCode:
    """代码分块"""

    def test_python_functions(self):
        code = (
            "def func1():\n    pass\n\n"
            "def func2():\n    pass\n\n"
            "class MyClass:\n    pass\n\n"
            "def func3():\n    pass\n"
        )
        chunks = chunk_code_document(code)
        assert len(chunks) >= 2

    def test_no_functions(self):
        code = "x = 1\ny = 2\nprint(x + y)"
        chunks = chunk_code_document(code)
        assert len(chunks) == 1


class TestChunkDocument:
    """统一入口"""

    def test_faq_type(self):
        text = "Q: 测试？\nA: 是的。"
        chunks = chunk_document(text, "faq")
        assert len(chunks) > 0

    def test_code_type(self):
        text = "def test():\n    pass"
        chunks = chunk_document(text, "code")
        assert len(chunks) > 0

    def test_unknown_type(self):
        text = "普通文本"
        chunks = chunk_document(text, "unknown")
        assert len(chunks) > 0
