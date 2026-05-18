"""文件上传路由 — 简历 + 代码 + 项目压缩包"""

import logging

from fastapi import APIRouter, UploadFile, File, HTTPException, Query

from models.schemas import UploadResponse, ProjectUploadResponse, UploadListResponse, UploadRecord
from services.parser import (
    parse_file,
    analyze_project,
    RESUME_EXTENSIONS,
    CODE_EXTENSIONS,
    ARCHIVE_EXTENSIONS,
)
from services.upload_store import UploadStore

logger = logging.getLogger(__name__)

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
async def upload_resume(file: UploadFile = File(...)):
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

    # 持久化存储
    store = UploadStore()
    stored_text = text[:MAX_STORED_TEXT]
    record = store.create(filename=file.filename, upload_type="resume", text=stored_text)

    return UploadResponse(filename=file.filename, text=text, type="resume")


@router.post("/code", response_model=UploadResponse)
async def upload_code(file: UploadFile = File(...)):
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

    # 持久化存储
    store = UploadStore()
    stored_text = text[:MAX_STORED_TEXT]
    record = store.create(filename=file.filename, upload_type="code", text=stored_text)

    return UploadResponse(filename=file.filename, text=text, type="code")


@router.post("/project", response_model=ProjectUploadResponse)
async def upload_project(file: UploadFile = File(...)):
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

    # 持久化存储
    store = UploadStore()
    stored_text = project["total_text"][:MAX_STORED_TEXT]
    record = store.create(
        filename=project["filename"],
        upload_type="project",
        text=stored_text,
        file_count=project["file_count"],
        tech_stack=project["tech_stack"],
    )

    return ProjectUploadResponse(
        filename=project["filename"],
        file_count=project["file_count"],
        structure=project["structure"],
        total_text=project["total_text"],
        tech_stack=project["tech_stack"],
        type="project",
    )


# ============ 上传文件管理 ============

@router.get("/files", response_model=UploadListResponse)
async def list_uploads(type: str = Query(None, description="按类型过滤: resume / code / project")):
    """
    列出所有上传文件记录。
    可选 ?type=resume 过滤类型。
    """
    if type and type not in ("resume", "code", "project"):
        raise HTTPException(status_code=400, detail="type 必须为 resume / code / project")
    store = UploadStore()
    records = store.list_all(upload_type=type or None)
    return UploadListResponse(uploads=records)


@router.get("/files/{upload_id}", response_model=UploadRecord)
async def get_upload(upload_id: str):
    """获取单条上传记录的完整文本"""
    store = UploadStore()
    record = store.get(upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="上传记录不存在")
    return record


@router.delete("/files/{upload_id}")
async def delete_upload(upload_id: str):
    """删除上传记录"""
    store = UploadStore()
    success = store.delete(upload_id)
    if not success:
        raise HTTPException(status_code=404, detail="上传记录不存在")
    return {"message": f"已删除: {upload_id}"}


@router.delete("/files")
async def delete_all_uploads(type: str = Query(None, description="按类型删除: resume / code / project")):
    """删除所有上传记录（或按类型）"""
    if type and type not in ("resume", "code", "project"):
        raise HTTPException(status_code=400, detail="type 必须为 resume / code / project")
    store = UploadStore()
    count = store.delete_all(upload_type=type or None)
    return {"message": f"已删除 {count} 条记录"}
