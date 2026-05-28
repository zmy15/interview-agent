"""RAG 检索管线单元测试"""

from unittest.mock import MagicMock, patch

import pytest

from services.rag_pipeline import (
    _extract_doc_info,
    build_rag_context,
    create_rag_retriever,
    format_rag_docs,
)


# ============================================================
#  _extract_doc_info
# ============================================================

class TestExtractDocInfo:
    """从 Document/dict 提取 content / score / metadata"""

    def test_from_langchain_document(self):
        """LangChain Document 对象（有 page_content / metadata 属性）"""
        doc = MagicMock()
        doc.page_content = "这是文档内容"
        doc.metadata = {"score": 0.95, "source": "faq.txt"}

        result = _extract_doc_info(doc)
        assert result["content"] == "这是文档内容"
        assert result["score"] == 0.95
        assert result["metadata"] == {"score": 0.95, "source": "faq.txt"}

    def test_from_dict(self):
        """普通 dict 格式（兼容旧格式）"""
        doc = {
            "content": "字典格式的内容",
            "score": 0.88,
            "metadata": {"source": "code.py"},
        }

        result = _extract_doc_info(doc)
        assert result["content"] == "字典格式的内容"
        assert result["score"] == 0.88
        assert result["metadata"] == {"source": "code.py"}

    def test_from_dict_without_score(self):
        """dict 缺少 score 字段 → 默认 0"""
        doc = {"content": "只有内容"}

        result = _extract_doc_info(doc)
        assert result["content"] == "只有内容"
        assert result["score"] == 0
        assert result["metadata"] == {}

    def test_fallback_to_str(self):
        """既不是 Document 也不是 dict → str() 兜底"""
        doc = 12345
        result = _extract_doc_info(doc)
        assert result["content"] == "12345"
        assert result["score"] == 0
        assert result["metadata"] == {}

    def test_document_without_metadata(self):
        """Document 没有 metadata 属性"""
        doc = MagicMock()
        doc.page_content = "无元数据"
        # 删除 metadata 属性，让 hasattr 返回 False
        del doc.metadata

        result = _extract_doc_info(doc)
        assert result["content"] == "无元数据"
        assert result["score"] == 0
        assert result["metadata"] == {}


# ============================================================
#  format_rag_docs
# ============================================================

class TestFormatRagDocs:
    """将检索结果格式化为上下文字符串"""

    def test_empty_docs(self):
        """空列表 → 空字符串"""
        assert format_rag_docs([]) == ""

    def test_single_dict_doc(self):
        """单个 dict 文档"""
        docs = [{"content": "Python 是解释型语言", "score": 0.92}]
        result = format_rag_docs(docs)
        assert "参考知识库" in result
        assert "Python 是解释型语言" in result
        assert "0.920" in result

    def test_multiple_dicts(self):
        """多个 dict 文档"""
        docs = [
            {"content": "文档 A", "score": 0.9},
            {"content": "文档 B", "score": 0.7},
            {"content": "文档 C", "score": 0.5},
        ]
        result = format_rag_docs(docs)
        assert "参考知识库" in result
        assert "[1]" in result
        assert "[2]" in result
        assert "[3]" in result
        assert "文档 A" in result
        assert "文档 B" in result
        assert "文档 C" in result

    def test_langchain_documents(self):
        """LangChain Document 对象列表"""
        doc1 = MagicMock()
        doc1.page_content = "RAG 技术详解"
        doc1.metadata = {"score": 0.85, "source": "rag.md"}

        doc2 = MagicMock()
        doc2.page_content = "向量检索原理"
        doc2.metadata = {"score": 0.72, "source": "vector.md"}

        result = format_rag_docs([doc1, doc2])
        assert "RAG 技术详解" in result
        assert "向量检索原理" in result
        assert "0.850" in result
        assert "0.720" in result

    def test_empty_content_in_docs(self):
        """文档内容全为空 → 仍然格式化但内容为空"""
        docs = [{"content": "", "score": 0.5}]
        result = format_rag_docs(docs)
        # 空内容文档仍会生成条目，只是内容为空
        assert "参考知识库" in result
        assert "[1]" in result


# ============================================================
#  create_rag_retriever
# ============================================================

class TestCreateRagRetriever:
    """创建 LangChain 检索器"""

    def test_returns_runnable(self):
        """返回一个 LangChain Runnable"""
        with patch("services.vector_store.VectorStoreManager") as mock_vms:
            instance = mock_vms.return_value
            instance.available = True
            instance.search.return_value = [
                {"content": "检索结果", "score": 0.9},
            ]

            retriever = create_rag_retriever("测试岗", top_k=3)
            # RunnableLambda 有 invoke 方法
            assert hasattr(retriever, "invoke")

    def test_retrieve_returns_results(self):
        """invoke 检索器返回格式化结果"""
        with patch("services.vector_store.VectorStoreManager") as mock_vms:
            instance = mock_vms.return_value
            instance.available = True
            instance.search.return_value = [
                {"content": "关于 Python 的知识", "score": 0.95},
            ]

            retriever = create_rag_retriever("测试岗", top_k=5)
            results = retriever.invoke("Python")
            assert len(results) == 1
            assert results[0]["content"] == "关于 Python 的知识"

    def test_retrieve_when_unavailable(self):
        """向量存储不可用 → 返回空列表"""
        with patch("services.vector_store.VectorStoreManager") as mock_vms:
            instance = mock_vms.return_value
            instance.available = False

            retriever = create_rag_retriever("测试岗")
            results = retriever.invoke("任意查询")
            assert results == []

    def test_retrieve_on_search_error(self):
        """检索抛异常 → 返回空列表（非阻塞）"""
        with patch("services.vector_store.VectorStoreManager") as mock_vms:
            instance = mock_vms.return_value
            instance.available = True
            instance.search.side_effect = RuntimeError("索引损坏")

            retriever = create_rag_retriever("测试岗")
            results = retriever.invoke("查询")
            assert results == []


# ============================================================
#  build_rag_context
# ============================================================

class TestBuildRagContext:
    """一站式 RAG 上下文构建"""

    def test_empty_position_name(self):
        """空岗位名 → 返回空字符串"""
        result = build_rag_context("", "任意查询")
        assert result == ""

    def test_none_position_name(self):
        """None 岗位名 → 返回空字符串"""
        result = build_rag_context(None, "查询")
        assert result == ""

    def test_rag_disabled(self, monkeypatch):
        """RAG 开关关闭 → 返回空字符串"""
        monkeypatch.setattr("services.rag_pipeline.settings.RAG_ENABLED", False)
        result = build_rag_context("测试岗", "查询")
        assert result == ""

    def test_vector_store_unavailable(self, monkeypatch):
        """向量存储不可用 → 返回空字符串"""
        monkeypatch.setattr("services.rag_pipeline.settings.RAG_ENABLED", True)
        with patch("services.vector_store.VectorStoreManager") as mock_vms:
            instance = mock_vms.return_value
            instance.available = False

            result = build_rag_context("测试岗", "Python 是什么")
            assert result == ""

    def test_successful_retrieval(self, monkeypatch):
        """正常检索并格式化"""
        monkeypatch.setattr("services.rag_pipeline.settings.RAG_ENABLED", True)
        with patch("services.vector_store.VectorStoreManager") as mock_vms:
            instance = mock_vms.return_value
            instance.available = True
            instance.search.return_value = [
                {"content": "Python 是一种编程语言", "score": 0.93},
            ]

            result = build_rag_context("技术岗", "什么是 Python")
            assert "参考知识库" in result
            assert "Python 是一种编程语言" in result
            assert "0.930" in result

    def test_search_returns_empty(self, monkeypatch):
        """检索无结果 → 返回空字符串"""
        monkeypatch.setattr("services.rag_pipeline.settings.RAG_ENABLED", True)
        with patch("services.vector_store.VectorStoreManager") as mock_vms:
            instance = mock_vms.return_value
            instance.available = True
            instance.search.return_value = []

            result = build_rag_context("技术岗", "火星上有猫吗")
            assert result == ""

    def test_search_raises_exception(self, monkeypatch):
        """检索抛出异常 → 返回空字符串（非阻塞）"""
        monkeypatch.setattr("services.rag_pipeline.settings.RAG_ENABLED", True)
        with patch("services.vector_store.VectorStoreManager") as mock_vms:
            instance = mock_vms.return_value
            instance.available = True
            instance.search.side_effect = ConnectionError("无法连接向量数据库")

            result = build_rag_context("技术岗", "查询")
            assert result == ""

    def test_custom_top_k(self, monkeypatch):
        """自定义 top_k 参数"""
        monkeypatch.setattr("services.rag_pipeline.settings.RAG_ENABLED", True)
        with patch("services.vector_store.VectorStoreManager") as mock_vms:
            instance = mock_vms.return_value
            instance.available = True
            instance.search.return_value = [
                {"content": "结果1", "score": 0.9},
            ]

            build_rag_context("岗", "q", top_k=10)
            instance.search.assert_called_once_with("岗", "q", 10)
