"""
TTS 语音合成代理路由 — 将请求转发到 TTS 微服务
仅在 VOICE_ENABLED=true 或 TTS_ENABLED=true 时注册
"""

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tts", tags=["tts"])

# HTTP 客户端（连接池复用）
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    return _client


@router.get("/health")
async def health():
    """探测 TTS 微服务健康状态"""
    try:
        client = _get_client()
        resp = await client.get(f"{settings.TTS_SERVICE_URL}/health")
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as e:
        logger.warning("TTS health check failed: %s", e)
        return JSONResponse(
            {"status": "unavailable", "error": str(e)},
            status_code=503,
        )


@router.post("/synthesize")
async def synthesize(request: Request):
    """
    批量合成 — 接收文本，返回 WAV 音频。
    转发到 TTS 微服务的 /synthesize 端点。
    """
    try:
        body = await request.json()
        text = body.get("text", "")
        if not text:
            return JSONResponse({"error": "text is required"}, status_code=400)

        client = _get_client()
        resp = await client.post(
            f"{settings.TTS_SERVICE_URL}/synthesize",
            json={"text": text},
        )
        # 透传音频流
        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "audio/wav"),
            status_code=resp.status_code,
        )
    except Exception as e:
        logger.error("TTS synthesize failed: %s", e)
        return JSONResponse(
            {"error": str(e)},
            status_code=503,
        )
