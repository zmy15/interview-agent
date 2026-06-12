"""
STT 语音识别微服务 — FastAPI 应用
端点:
  - POST /transcribe      批量转录（HTTP multipart，兜底）
  - WS   /stream           WebSocket 流式转录 + VAD
  - GET  /health          健康检查
"""

import asyncio
import logging
import os
import sys
import tempfile
from typing import Optional

# ── HuggingFace 镜像（必须在任何 HF 导入之前设置） ──
_hf_endpoint = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = _hf_endpoint

import numpy as np
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from streaming_transcriber import StreamingTranscriber

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stt_service")

# ── 配置（环境变量） ──
STT_MODEL = os.getenv("STT_MODEL", "base")
STT_DEVICE = os.getenv("STT_DEVICE", "cpu")
STT_COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", "auto")
VAD_SILENCE_TIMEOUT = float(os.getenv("VAD_SILENCE_TIMEOUT", "1.0"))

# ── 应用 ──
app = FastAPI(title="STT Service", version="1.0.0")

# 全局转录器（单例，所有连接共享模型）
_transcriber: Optional[StreamingTranscriber] = None
_model_loaded: bool = False
_model_error: Optional[str] = None


def get_transcriber() -> StreamingTranscriber:
    """获取或初始化全局转录器"""
    global _transcriber, _model_loaded, _model_error
    if _transcriber is None:
        try:
            _transcriber = StreamingTranscriber(
                model_size=STT_MODEL,
                device=STT_DEVICE,
                compute_type=STT_COMPUTE_TYPE,
                silence_timeout=VAD_SILENCE_TIMEOUT,
            )
            _transcriber._ensure_model()
            _model_loaded = True
            logger.info("STT model loaded successfully")
        except Exception as e:
            _model_error = str(e)
            logger.error("Failed to load STT model: %s", e)
            raise
    return _transcriber


# ═══════════════════════════════════════════════════════════════
# HTTP 端点
# ═══════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    """健康检查 — 返回模型和设备状态"""
    return JSONResponse({
        "status": "ok" if _model_loaded else "error",
        "model": STT_MODEL,
        "device": STT_DEVICE,
        "vad": "loaded" if _model_loaded else "not_loaded",
        "error": _model_error,
    })


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    批量转录 — 接收完整音频文件，返回转录文本。
    兜底方案，当 WebSocket 不可用时使用。
    支持格式：wav, webm, mp3, ogg 等（通过 ffmpeg 转码）。
    """
    # 保存临时文件
    suffix = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        # 用 ffmpeg 转 PCM 16kHz mono
        import ffmpeg
        import subprocess

        out_path = tmp_path + ".wav"
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", tmp_path,
                "-ar", "16000", "-ac", "1",
                "-sample_fmt", "s16", out_path,
            ],
            capture_output=True,
            check=True,
        )

        # 读取 PCM 数据
        import soundfile as sf  # 备选
        try:
            import wave
            with wave.open(out_path, "rb") as wf:
                n_frames = wf.getnframes()
                audio_bytes = wf.readframes(n_frames)
                audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32767.0
        except Exception:
            # fallback: 使用 scipy 或直接读取
            audio_np = np.zeros(0, dtype=np.float32)

        if len(audio_np) == 0:
            return JSONResponse({"text": "", "segments": [], "language": "zh", "warning": "empty audio"})

        # 转录 — HTTP 批量模式跳过 VAD，直接全量转录
        transcriber = get_transcriber()
        transcriber._ensure_model()

        # faster-whisper 需要 float32 输入
        segments, info = transcriber._model.transcribe(
            audio_np.astype(np.float32),
            language="zh",
            beam_size=5,
            vad_filter=True,   # HTTP 批量模式用 whisper 内置 VAD
        )
        text = "".join(seg.text for seg in segments)

        return JSONResponse({
            "text": text.strip(),
            "segments": [],
            "language": info.language,
        })

    except Exception as e:
        logger.error("Transcription error: %s", e)
        return JSONResponse(
            {"text": "", "segments": [], "language": "zh", "error": str(e)},
            status_code=500,
        )
    finally:
        # 清理临时文件
        for p in [tmp_path, tmp_path + ".wav"]:
            try:
                os.unlink(p)
            except OSError:
                pass


# ═══════════════════════════════════════════════════════════════
# WebSocket 流式端点
# ═══════════════════════════════════════════════════════════════


@app.websocket("/stream")
async def websocket_stream(ws: WebSocket):
    """
    WebSocket 流式转录端点。

    协议：
    Client → Server: binary audio frames (16kHz, 16bit, mono PCM, 每帧 3200 bytes = 100ms)
    Server → Client: JSON 消息
        {"type": "vad", "ts": 1.2, "status": "speech_start"}
        {"type": "partial", "ts": 1.5, "text": "我认为"}
        {"type": "final", "ts": 5.2, "text": "我认为这个问题可以从三个角度来回答"}
    """
    await ws.accept()
    logger.info("WebSocket client connected")

    try:
        transcriber = StreamingTranscriber(
            model_size=STT_MODEL,
            device=STT_DEVICE,
            compute_type=STT_COMPUTE_TYPE,
            silence_timeout=VAD_SILENCE_TIMEOUT,
            on_partial=lambda text: asyncio.create_task(
                ws.send_json({"type": "partial", "text": text})
            ),
            on_final=lambda text: asyncio.create_task(
                ws.send_json({"type": "final", "text": text})
            ),
            on_vad=lambda status: asyncio.create_task(
                ws.send_json({"type": "vad", "status": status})
            ),
        )
        transcriber._ensure_model()

        # 发送就绪信号
        await ws.send_json({"type": "ready", "model": STT_MODEL, "device": STT_DEVICE})

        # 处理音频帧
        while True:
            try:
                data = await ws.receive()
            except WebSocketDisconnect:
                logger.info("WebSocket client disconnected")
                break

            if "bytes" in data:
                # binary PCM 帧
                raw = data["bytes"]
                # 转换为 float32 numpy array
                audio_np = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
                await transcriber.process_frame(audio_np)

            elif "text" in data:
                # JSON 控制消息
                import json
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "flush":
                        # 强制转录并返回最终文本
                        final_text = await transcriber.flush()
                        await ws.send_json({"type": "final", "text": final_text})
                    elif msg.get("type") == "reset":
                        transcriber.reset()
                except json.JSONDecodeError:
                    pass

    except Exception as e:
        logger.error("WebSocket error: %s", e)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
        logger.info("WebSocket connection closed")


# ═══════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
