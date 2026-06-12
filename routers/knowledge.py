"""知识库管理路由 — 上传/搜索/删除"""

import logging
import time

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.schemas import (
    KnowledgeUploadResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeChunk,
)
from services.parser import (
    parse_file,
    analyze_project,
    RESUME_EXTENSIONS,
    CODE_EXTENSIONS,
    ARCHIVE_EXTENSIONS,
)
from services.chunker import chunk_document
from services.vector_store import VectorStoreManager, is_vector_store_available
from services.position_store import PositionStore
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

MAX_KNOWLEDGE_SIZE = 10 * 1024 * 1024   # 10MB（FAQ/代码文件）
MAX_PROJECT_SIZE = 50 * 1024 * 1024      # 50MB（项目压缩包）


def _check_vector_store():
    """检查向量存储是否可用，不可用则抛出 503"""
    if not is_vector_store_available():
        raise HTTPException(
            status_code=503,
            detail="向量知识库功能不可用：缺少 torch / sentence-transformers 依赖（Windows DLL 问题）",
        )


def _get_ext(filename: str) -> str:
    """获取文件扩展名（兼容 .tar.gz 等）"""
    namelower = filename.lower()
    for ext in [".tar.gz", ".tar.bz2", ".tar.xz", ".tgz"]:
        if namelower.endswith(ext):
            return ext
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


@router.post("/upload", response_model=KnowledgeUploadResponse)
async def upload_knowledge(
    file: UploadFile = File(...),
    position_name: str = Form(...),
    doc_type: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    上传知识库文档。
    doc_type:
      - "faq"       : FAQ / 技术文档（PDF/DOCX/TXT/MD）
      - "code"      : 代码文档（.py/.js/.java 等）
      - "project"   : 项目压缩包（ZIP/TAR.GZ/7Z 等）
    """
    _check_vector_store()

    # 校验 doc_type
    if doc_type not in ("faq", "code", "project"):
        raise HTTPException(status_code=400, detail="doc_type 必须为 'faq' / 'code' / 'project'")

    # 校验 position_name 对应岗位存在
    store = PositionStore(db)
    pos = await store.get(position_name)
    if not pos:
        raise HTTPException(status_code=404, detail=f"岗位 '{position_name}' 不存在，请先创建岗位")

    # 校验文件类型
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = _get_ext(file.filename)

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
    elif doc_type == "project" and ext not in ARCHIVE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"项目压缩包不支持此格式，支持: {', '.join(sorted(ARCHIVE_EXTENSIONS))}",
        )

    # 读取文件
    content = await file.read()
    max_size = MAX_PROJECT_SIZE if doc_type == "project" else MAX_KNOWLEDGE_SIZE
    if len(content) > max_size:
        size_mb = max_size // (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"文件大小超过 {size_mb}MB 限制")

    # 解析文本
    text: str
    metadata_extra: dict = {}

    if doc_type == "project":
        try:
            project = analyze_project(content, file.filename)
            text = project["total_text"]
            metadata_extra = {
                "file_count": project["file_count"],
                "tech_stack": project.get("tech_stack", []),
            }
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            logger.error(f"Project parse error: {e}")
            raise HTTPException(status_code=422, detail=f"项目解析失败: {str(e)}")
    else:
        try:
            text = parse_file(content, file.filename)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            logger.error(f"Knowledge parse error: {e}")
            raise HTTPException(status_code=422, detail=f"文件解析失败: {str(e)}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="无法从文件中提取文本内容")

    # 分块（project 和 code 都按代码分块策略）
    t_chunk_start = time.time()
    chunk_type = "code" if doc_type in ("code", "project") else "faq"
    chunks = chunk_document(text, chunk_type)
    t_chunk = time.time() - t_chunk_start
    if not chunks:
        raise HTTPException(status_code=422, detail="文档分块失败，未能提取有效内容")
    logger.info(
        "[知识库上传] 分块完成 | file=%s | type=%s | chunks=%d | 耗时=%.2fs | 平均块长=%d",
        file.filename, doc_type, len(chunks), t_chunk,
        len(text) // len(chunks) if chunks else 0,
    )

    # 存入向量库
    try:
        metadata = {"doc_type": doc_type, "filename": file.filename, **metadata_extra}
        logger.info(
            "[知识库上传] 开始向量索引 | position=%s | file=%s | chunks=%d",
            position_name, file.filename, len(chunks),
        )
        t_index_start = time.time()
        vms = VectorStoreManager(settings)
        count = vms.add_documents(position_name, chunks, metadata=metadata)
        t_index = time.time() - t_index_start
        logger.info(
            "[知识库上传] 向量索引完成 | position=%s | chunks=%d | 耗时=%.2fs | 速度=%.1f chunks/s",
            position_name, count, t_index,
            count / t_index if t_index > 0 else 0,
        )
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


@router.delete("/collections/{position_name}")
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


# ============ RAG 开关 ============

@router.get("/rag-status")
async def get_rag_status():
    """查询 RAG 检索增强的开关状态"""
    return {
        "rag_enabled": settings.RAG_ENABLED,
        "message": "RAG 检索增强已开启" if settings.RAG_ENABLED else "RAG 检索增强已关闭",
    }


@router.post("/rag-toggle")
async def toggle_rag(enabled: bool = None):
    """
    动态切换 RAG 检索增强开关。

    - 不传参数：翻转当前状态
    - enabled=true：强制开启
    - enabled=false：强制关闭

    注意：此切换仅在当前进程生命周期内生效，重启后恢复 .env 配置。
    """
    if enabled is None:
        # 翻转
        settings.RAG_ENABLED = not settings.RAG_ENABLED
    else:
        settings.RAG_ENABLED = enabled

    new_status = "开启" if settings.RAG_ENABLED else "关闭"
    logger.info("RAG status toggled → %s (by API)", new_status)
    return {
        "rag_enabled": settings.RAG_ENABLED,
        "message": f"RAG 检索增强已{new_status}",
    }
