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
            logger.warning("关闭 STT HTTP 客户端失败: %s", exc)
        finally:
            _client = None


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
