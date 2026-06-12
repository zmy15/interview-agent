"""
STT 语音识别代理路由 — 将请求转发到 STT 微服务
仅在 VOICE_ENABLED=true 或 STT_ENABLED=true 时注册
"""

import logging

import httpx
from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stt", tags=["stt"])

# HTTP 客户端（连接池复用）
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(120.0))
    return _client


@router.get("/health")
async def health():
    """探测 STT 微服务健康状态"""
    try:
        client = _get_client()
        resp = await client.get(f"{settings.STT_SERVICE_URL}/health")
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.warning("STT health check failed: %s", e)
        return JSONResponse(
            {"status": "unavailable", "error": str(e)},
            status_code=503,
        )


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    批量转录 — 上传音频文件，返回转录文本。
    转发到 STT 微服务的 /transcribe 端点。
    """
    try:
        client = _get_client()
        # 转发文件到 STT 微服务
        files = {"file": (file.filename, await file.read(), file.content_type or "audio/webm")}
        resp = await client.post(
            f"{settings.STT_SERVICE_URL}/transcribe",
            files=files,
        )
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.error("STT transcribe failed: %s", e)
        return JSONResponse(
            {"text": "", "error": str(e)},
            status_code=503,
        )
