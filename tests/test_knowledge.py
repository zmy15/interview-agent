"""知识库接口测试"""

import io

import pytest


class TestKnowledgeUpload:
    """POST /knowledge/upload"""

    @pytest.fixture(autouse=True)
    def setup_position(self, client):
        """创建测试岗位"""
        client.post("/positions", json={"name": "知识库测试岗", "description": "测试"})
        yield
        # 清理知识库
        try:
            client.delete("/knowledge/知识库测试岗")
        except Exception:
            pass
        # 清理岗位
        try:
            client.delete("/positions/知识库测试岗")
        except Exception:
            pass

    def test_upload_faq(self, client):
        """上传 FAQ 文档"""
        content = (
            "Q: Python 中什么是 GIL？\n"
            "A: GIL 是全局解释器锁，确保同一时刻只有一个线程执行 Python 字节码。\n\n"
            "Q: 什么是装饰器？\n"
            "A: 装饰器是一种设计模式，用于在不修改原函数的情况下给函数添加新功能。"
        )
        files = {"file": ("faq.txt", io.BytesIO(content.encode("utf-8")), "text/plain")}
        data = {"position_name": "知识库测试岗", "doc_type": "faq"}

        response = client.post("/knowledge/upload", files=files, data=data)
        assert response.status_code == 200
        result = response.json()
        assert result["position_name"] == "知识库测试岗"
        assert result["chunks_count"] > 0

    def test_upload_nonexistent_position(self, client):
        """上传到不存在的岗位"""
        content = b"test content"
        files = {"file": ("test.txt", io.BytesIO(content), "text/plain")}
        data = {"position_name": "不存在的岗位", "doc_type": "faq"}

        response = client.post("/knowledge/upload", files=files, data=data)
        assert response.status_code == 404


class TestKnowledgeSearch:
    """POST /knowledge/search"""

    @pytest.fixture(autouse=True)
    def setup_knowledge(self, client):
        """创建岗位并上传知识"""
        client.post("/positions", json={"name": "搜索测试岗", "description": "测试"})
        content = "Python 是一种解释型编程语言"
        files = {"file": ("test.txt", io.BytesIO(content.encode("utf-8")), "text/plain")}
        client.post("/knowledge/upload", files=files, data={"position_name": "搜索测试岗", "doc_type": "faq"})
        yield
        try:
            client.delete("/knowledge/搜索测试岗")
        except Exception:
            pass
        try:
            client.delete("/positions/搜索测试岗")
        except Exception:
            pass

    def test_search(self, client):
        """搜索知识库"""
        response = client.post(
            "/knowledge/search",
            json={
                "query": "Python 是什么语言",
                "position_name": "搜索测试岗",
                "top_k": 3,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data


class TestKnowledgeDelete:
    """DELETE /knowledge/{position_name}"""

    def test_delete(self, client):
        """删除知识库"""
        client.post("/positions", json={"name": "删除测试岗", "description": "测试"})
        content = b"test"
        files = {"file": ("test.txt", io.BytesIO(content), "text/plain")}
        client.post("/knowledge/upload", files=files, data={"position_name": "删除测试岗", "doc_type": "faq"})

        response = client.delete("/knowledge/删除测试岗")
        assert response.status_code == 200

        # 清理岗位
        client.delete("/positions/删除测试岗")
