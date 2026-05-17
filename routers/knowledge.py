"""知识库管理路由 — 上传/搜索/删除"""

import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from config import settings
from models.schemas import (
    KnowledgeUploadResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeChunk,
)
from services.parser import parse_file, RESUME_EXTENSIONS, CODE_EXTENSIONS
from services.chunker import chunk_document
from services.vector_store import VectorStoreManager, is_vector_store_available
from services.position_store import PositionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

MAX_KNOWLEDGE_SIZE = 10 * 1024 * 1024  # 10MB


def _check_vector_store():
    """检查向量存储是否可用，不可用则抛出 503"""
    if not is_vector_store_available():
        raise HTTPException(
            status_code=503,
            detail="向量知识库功能不可用：缺少 torch / sentence-transformers 依赖（Windows DLL 问题）",
        )


@router.post("/upload", response_model=KnowledgeUploadResponse)
async def upload_knowledge(
    file: UploadFile = File(...),
    position_name: str = Form(...),
    doc_type: str = Form(...),
):
    """
    上传知识库文档（FAQ 或代码文档）。
    doc_type: "faq" / "code"
    """
    _check_vector_store()

    # 校验 doc_type
    if doc_type not in ("faq", "code"):
        raise HTTPException(status_code=400, detail="doc_type 必须为 'faq' 或 'code'")

    # 校验 position_name 对应岗位存在
    store = PositionStore()
    pos = store.get(position_name)
    if not pos:
        raise HTTPException(status_code=404, detail=f"岗位 '{position_name}' 不存在，请先创建岗位")

    # 校验文件类型
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""

    if doc_type == "faq" and ext not in RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"FAQ 文档不支持此格式，支持: {', '.join(RESUME_EXTENSIONS)}",
        )
    elif doc_type == "code" and ext not in CODE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"代码文档不支持此格式，支持: {', '.join(sorted(CODE_EXTENSIONS))}",
        )

    # 读取和解析
    content = await file.read()
    if len(content) > MAX_KNOWLEDGE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过 10MB 限制")

    try:
        text = parse_file(content, file.filename)
    except Exception as e:
        logger.error(f"Knowledge parse error: {e}")
        raise HTTPException(status_code=422, detail=f"文件解析失败: {str(e)}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="无法从文件中提取文本内容")

    # 分块
    chunks = chunk_document(text, doc_type)
    if not chunks:
        raise HTTPException(status_code=422, detail="文档分块失败，未能提取有效内容")

    # 存入向量库
    try:
        vms = VectorStoreManager(settings)
        count = vms.add_documents(position_name, chunks, metadata={"doc_type": doc_type, "filename": file.filename})
    except Exception as e:
        logger.error(f"Vector store error: {e}")
        raise HTTPException(status_code=500, detail=f"知识库存储失败: {str(e)}")

    return KnowledgeUploadResponse(
        position_name=position_name,
        chunks_count=count,
        message=f"成功上传并存储 {count} 个文档块到岗位 '{position_name}' 的知识库",
    )


@router.get("/collections")
async def list_collections():
    """列出所有知识库"""
    _check_vector_store()
    vms = VectorStoreManager(settings)
    return {"collections": vms.list_collections()}


@router.delete("/{position_name}")
async def delete_knowledge(position_name: str):
    """删除指定岗位的知识库（不删除岗位本身）"""
    _check_vector_store()
    vms = VectorStoreManager(settings)
    success = vms.delete_collection(position_name)
    if not success:
        raise HTTPException(status_code=404, detail=f"知识库 '{position_name}' 不存在或删除失败")
    return {"message": f"知识库 '{position_name}' 已删除"}


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(req: KnowledgeSearchRequest):
    """手动搜索知识库（调试用）"""
    _check_vector_store()
    top_k = req.top_k if 1 <= req.top_k <= 20 else 3
    vms = VectorStoreManager(settings)
    results = vms.search(req.position_name, req.query, top_k)

    return KnowledgeSearchResponse(
        results=[KnowledgeChunk(**r) for r in results]
    )
