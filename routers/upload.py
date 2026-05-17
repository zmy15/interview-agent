"""文件上传路由 — 简历 + 代码"""

import logging

from fastapi import APIRouter, UploadFile, File, HTTPException

from models.schemas import UploadResponse
from services.parser import parse_file, RESUME_EXTENSIONS, CODE_EXTENSIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["upload"])

MAX_RESUME_SIZE = 5 * 1024 * 1024  # 5MB
MAX_CODE_SIZE = 2 * 1024 * 1024    # 2MB


@router.post("/resume", response_model=UploadResponse)
async def upload_resume(file: UploadFile = File(...)):
    """上传简历文件（PDF/DOCX/TXT）"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
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
    except Exception as e:
        logger.error(f"Resume parse error: {e}")
        raise HTTPException(status_code=422, detail=f"文件解析失败: {str(e)}")

    if not text.strip():
        raise HTTPException(status_code=422, detail="无法从文件中提取文本内容")

    return UploadResponse(filename=file.filename, text=text, type="resume")


@router.post("/code", response_model=UploadResponse)
async def upload_code(file: UploadFile = File(...)):
    """上传代码文件"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
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
    except Exception as e:
        logger.error(f"Code parse error: {e}")
        raise HTTPException(status_code=422, detail=f"文件解析失败: {str(e)}")

    return UploadResponse(filename=file.filename, text=text, type="code")
