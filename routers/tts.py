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


async def aclose() -> None:
    """关闭模块级客户端（由 main.py 的 lifespan 在应用退出时调用）。

    必须在事件循环**还活着**的时候关闭：不然 httpx 的连接池会拖到 GC
    阶段才去关底层 socket，那时 loop 已关闭，`loop.call_soon()` 会抛
    `RuntimeError: Event loop is closed`。这类异常会被 anyio 归到当时
    恰好正在运行的那条测试用例上，表现为「毫不相干的用例莫名失败」。
    """
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception as exc:  # noqa: BLE001 - 清理失败不应影响退出
            logger.warning("关闭 TTS HTTP 客户端失败: %s", exc)
        finally:
            _client = None


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
