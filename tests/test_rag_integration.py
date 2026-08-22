"""RAG 端到端集成测试"""

import io

import pytest

from services.vector_store import (
    is_vector_store_available,
)


pytestmark = pytest.mark.skipif(
    not is_vector_store_available(),
    reason="需要安装 requirements-rag.txt 中的可选 RAG 依赖",
)


def test_rag_full_pipeline(client):
    """完整 RAG 流水线测试：创建岗位 → 上传知识 → 向量检索 → 验证 chat 集成"""
    
    position_name = "RAG集成测试岗"
    
    # ========== 1. 创建岗位（如果已存在则先删除） ==========
    print("\n[1/5] 创建测试岗位...")
    # 清理旧数据
    try:
        client.delete(f"/knowledge/{position_name}")
    except Exception:
        pass
    try:
        client.delete(f"/positions/{position_name}")
    except Exception:
        pass
    
    resp = client.post("/positions", json={
        "name": position_name,
        "description": "用于 RAG 集成测试的岗位"
    })
    assert resp.status_code in (200, 201), f"创建岗位失败: {resp.text}"
    print(f"  岗位 '{position_name}' 创建成功")
    
    # ========== 2. 添加 JD ==========
    print("\n[2/5] 添加岗位 JD...")
    resp = client.post(f"/positions/{position_name}/jds", json={
        "content": "## 岗位要求\n\n1. 精通 Python 编程\n2. 熟悉 FastAPI 框架\n3. 了解向量数据库原理\n4. 有 RAG 系统开发经验"
    })
    assert resp.status_code in (200, 201), f"添加 JD 失败: {resp.text}"
    print(f"  JD 添加成功")
    
    # ========== 3. 上传知识库文档 ==========
    print("\n[3/5] 上传知识库文档...")
    faq_content = (
        "Q: 什么是 RAG？\n"
        "A: RAG（Retrieval-Augmented Generation）是一种结合检索和生成的 AI 技术架构，"
        "通过从外部知识库检索相关信息来增强大语言模型的回答质量。\n\n"
        "Q: FastAPI 有哪些优势？\n"
        "A: FastAPI 是一个现代 Python Web 框架，具有自动 API 文档生成、"
        "类型提示验证、异步支持、高性能等特点。\n\n"
        "Q: 向量数据库的作用是什么？\n"
        "A: 向量数据库专门用于存储和检索高维向量数据，"
        "通过近似最近邻搜索实现语义相似度匹配，是 RAG 系统的核心组件。"
    )
    files = {"file": ("faq.txt", io.BytesIO(faq_content.encode("utf-8")), "text/plain")}
    data = {"position_name": position_name, "doc_type": "faq"}
    
    resp = client.post("/knowledge/upload", files=files, data=data)
    assert resp.status_code == 200, f"上传知识失败: {resp.text}"
    result = resp.json()
    assert result["chunks_count"] > 0, "知识分块数量为0"
    print(f"  上传成功，共 {result['chunks_count']} 个文档块")
    
    # ========== 4. 向量检索测试 ==========
    print("\n[4/5] 测试向量检索...")
    search_queries = [
        ("什么是 RAG 技术", "RAG"),
        ("FastAPI 的特点", "FastAPI"),
        ("向量数据库有什么用", "向量数据库"),
    ]
    
    for query, expected_keyword in search_queries:
        resp = client.post("/knowledge/search", json={
            "query": query,
            "position_name": position_name,
            "top_k": 3,
        })
        assert resp.status_code == 200, f"搜索失败 ({query}): {resp.text}"
        data = resp.json()
        assert "results" in data
        assert len(data["results"]) > 0, f"搜索 '{query}' 无结果"
        
        all_contents = " ".join(r["content"] for r in data["results"])
        top_score = data["results"][0]["score"]
        print(f"  查询: '{query}' → Top1 score={top_score:.4f}, 含关键词 '{expected_keyword}': {expected_keyword in all_contents}")
        assert expected_keyword in all_contents, f"搜索结果不包含关键词 '{expected_keyword}'"
    
    # ========== 5. 列出知识库和清理 ==========
    print("\n[5/5] 验证知识库列表并清理...")
    
    # 列出所有知识库
    resp = client.get("/knowledge/collections")
    assert resp.status_code == 200, f"列出知识库失败: {resp.text}"
    collections = resp.json().get("collections", [])
    our_collection = [c for c in collections if c["position_name"] == position_name]
    assert len(our_collection) > 0, f"知识库列表中未找到 '{position_name}'"
    assert our_collection[0]["document_count"] > 0, "文档数为0"
    print(f"  知识库 '{position_name}' 文档数: {our_collection[0]['document_count']}")
    
    # 删除知识库
    resp = client.delete(f"/knowledge/{position_name}")
    assert resp.status_code == 200, f"删除知识库失败: {resp.text}"
    print(f"  知识库 '{position_name}' 已删除")
    
    # 删除岗位
    resp = client.delete(f"/positions/{position_name}")
    assert resp.status_code == 200, f"删除岗位失败: {resp.text}"
    print(f"  岗位 '{position_name}' 已删除")
    
    print("\n✅ RAG 端到端集成测试全部通过！")


if __name__ == "__main__":
    test_rag_full_pipeline()
