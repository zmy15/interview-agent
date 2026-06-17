"""文件上传路由 — 简历 + 代码 + 项目压缩包"""

import logging
import time

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.schemas import UploadResponse, ProjectUploadResponse, UploadListResponse, UploadRecord
from services.parser import (
    parse_file,
    analyze_project,
    RESUME_EXTENSIONS,
    CODE_EXTENSIONS,
    ARCHIVE_EXTENSIONS,
)
from services.upload_store import UploadStore
from services.chunker import chunk_document
from services.vector_store import VectorStoreManager, is_vector_store_available
from database import get_db
from utils.auth import get_current_user, CurrentUser

logger = logging.getLogger(__name__)

# 上传文件统一 FAISS collection 名称
UPLOADS_COLLECTION = "__uploads__"

router = APIRouter(prefix="/upload", tags=["upload"])

MAX_RESUME_SIZE = 5 * 1024 * 1024   # 5MB
MAX_CODE_SIZE = 2 * 1024 * 1024     # 2MB
MAX_PROJECT_SIZE = 50 * 1024 * 1024  # 50MB
MAX_STORED_TEXT = 100 * 1024         # 存储文本上限 100KB（预览之外截断）


def _get_ext(filename: str) -> str:
    """获取文件扩展名（兼容 .tar.gz 等复合扩展名）"""
    namelower = filename.lower()
    for ext in [".tar.gz", ".tar.bz2", ".tar.xz", ".tgz"]:
        if namelower.endswith(ext):
            return ext
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


@router.post("/resume", response_model=UploadResponse)
async def upload_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """上传简历文件（PDF/DOCX/DOC/TXT）"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = _get_ext(file.filename)
    if ext not in RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的简历格式，支持: {', '.join(RESUME_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_RESUME_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过 5MB 限制")

    try:
        text = parse_file(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Resume parse error: {e}")
        raise HTTPException(status_code=422, detail=f"文件解析失败: {str(e)}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="无法从文件中提取文本内容")

    # 持久化存储（DB）
    store = UploadStore(db)
    stored_text = text[:MAX_STORED_TEXT]
    await store.create(filename=file.filename, upload_type="resume", text=stored_text, user_id=user.id)

    return UploadResponse(filename=file.filename, text=text, type="resume")


@router.post("/code", response_model=UploadResponse)
async def upload_code(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """上传代码文件"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = _get_ext(file.filename)
    if ext not in CODE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的代码格式，支持: {', '.join(sorted(CODE_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_CODE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过 2MB 限制")

    try:
        text = parse_file(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Code parse error: {e}")
        raise HTTPException(status_code=422, detail=f"文件解析失败: {str(e)}")

    # 持久化存储（DB）
    store = UploadStore(db)
    stored_text = text[:MAX_STORED_TEXT]
    record = await store.create(filename=file.filename, upload_type="code", text=stored_text, user_id=user.id)

    # 索引到 FAISS 向量库（用于 RAG 检索）
    _index_to_faiss(
        filename=file.filename,
        text=text,
        doc_type="code",
        upload_id=record.id,
    )

    return UploadResponse(filename=file.filename, text=text, type="code")


@router.post("/project", response_model=ProjectUploadResponse)
async def upload_project(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    上传项目压缩包（ZIP / TAR.GZ / TAR.BZ2 / 7Z）。

    后端会自动：
    1. 解压压缩包
    2. 识别文件分类（源码 / 配置 / 文档 / 构建 / 测试 / 其他）
    3. 提取所有文本文件内容
    4. 推断技术栈（Python/React/Java/Go 等）
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = _get_ext(file.filename)
    if ext not in ARCHIVE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的项目压缩格式，支持: {', '.join(sorted(ARCHIVE_EXTENSIONS))}",
        )

    content = await file.read()
    if len(content) > MAX_PROJECT_SIZE:
        raise HTTPException(status_code=413, detail="文件大小超过 50MB 限制")

    try:
        project = analyze_project(content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Project parse error: {e}")
        raise HTTPException(status_code=422, detail=f"项目解析失败: {str(e)}")

    if not project["total_text"].strip():
        raise HTTPException(status_code=422, detail="无法从项目中提取文本内容")

    # 持久化存储（DB）
    store = UploadStore(db)
    stored_text = project["total_text"][:MAX_STORED_TEXT]
    record = await store.create(
        filename=project["filename"],
        upload_type="project",
        text=stored_text,
        user_id=user.id,
        file_count=project["file_count"],
        tech_stack=project["tech_stack"],
    )

    # 索引到 FAISS 向量库（用于 RAG 检索）
    _index_to_faiss(
        filename=project["filename"],
        text=project["total_text"],
        doc_type="project",
        upload_id=record.id,
    )

    return ProjectUploadResponse(
        filename=project["filename"],
        file_count=project["file_count"],
        structure=project["structure"],
        total_text=project["total_text"],
        tech_stack=project["tech_stack"],
        type="project",
    )


def _index_to_faiss(filename: str, text: str, doc_type: str, upload_id: str):
    """将上传文件内容分块并索引到 FAISS 向量库（失败不影响上传主流程）"""
    if not is_vector_store_available():
        logger.info("Vector store not available, skipping FAISS index for %s", filename)
        return

    t_total_start = time.time()
    text_len = len(text)
    logger.info(
        ">>> 上传文件 FAISS 索引开始 | file=%s | type=%s | 文本长度=%d",
        filename, doc_type, text_len,
    )

    try:
        # ── 分块阶段 ──
        t_chunk_start = time.time()
        chunks = chunk_document(text, doc_type)
        t_chunk = time.time() - t_chunk_start
        if not chunks:
            logger.warning("Chunking produced no chunks for %s", filename)
            return
        logger.info(
            "  [分块] %d chunks | 耗时: %.2fs | 平均块长: %d",
            len(chunks), t_chunk, text_len // len(chunks) if chunks else 0,
        )

        # ── 索引阶段 ──
        t_index_start = time.time()
        vms = VectorStoreManager(settings)
        count = vms.add_documents(
            position_name=UPLOADS_COLLECTION,
            chunks=chunks,
            metadata={
                "doc_type": doc_type,
                "filename": filename,
                "upload_id": upload_id,
                "source": "upload",
            },
        )
        t_index = time.time() - t_index_start

        t_total = time.time() - t_total_start
        logger.info(
            "<<< 上传文件 FAISS 索引完成 | file=%s | type=%s | chunks=%d/%d | "
            "分块耗时=%.2fs | 索引耗时=%.2fs | 总耗时=%.2fs | collection=%s",
            filename, doc_type, count, len(chunks),
            t_chunk, t_index, t_total, UPLOADS_COLLECTION,
        )
    except Exception as e:
        t_total = time.time() - t_total_start
        logger.warning(
            "FAISS index failed for %s (non-blocking, elapsed=%.2fs): %s",
            filename, t_total, e,
        )


# ============ 上传文件管理 ============

@router.get("/files", response_model=UploadListResponse)
async def list_uploads(
    type: str = Query(None, description="按类型过滤: resume / code / project"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """列出当前用户的所有上传文件记录。可选 ?type=resume 过滤类型。"""
    if type and type not in ("resume", "code", "project"):
        raise HTTPException(status_code=400, detail="type 必须为 resume / code / project")
    store = UploadStore(db)
    records = await store.list_all(upload_type=type or None, user_id=user.id)
    return UploadListResponse(uploads=records)


@router.get("/files/{upload_id}", response_model=UploadRecord)
async def get_upload(upload_id: str, db: AsyncSession = Depends(get_db)):
    """获取单条上传记录的完整文本"""
    store = UploadStore(db)
    record = await store.get(upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="上传记录不存在")
    return record


@router.delete("/files/{upload_id}")
async def delete_upload(upload_id: str, db: AsyncSession = Depends(get_db)):
    """删除上传记录"""
    store = UploadStore(db)
    success = await store.delete(upload_id)
    if not success:
        raise HTTPException(status_code=404, detail="上传记录不存在")
    return {"message": f"已删除: {upload_id}"}


@router.delete("/files")
async def delete_all_uploads(
    type: str = Query(None, description="按类型删除: resume / code / project"),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """删除当前用户的所有上传记录（或按类型）"""
    if type and type not in ("resume", "code", "project"):
        raise HTTPException(status_code=400, detail="type 必须为 resume / code / project")
    store = UploadStore(db)
    count = await store.delete_all(upload_type=type or None, user_id=user.id)
    return {"message": f"已删除 {count} 条记录"}
