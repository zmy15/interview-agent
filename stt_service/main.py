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

# ── 加载项目根目录的 .env ──
#
# 为什么必须显式加载：
#   本服务是**独立进程**，主进程的 load_dotenv() 管不到它。
#   此前它只读环境变量，导致 .env 里的 STT_MODEL 等设置
#   完全无效 —— 实际总在用代码里的默认值 base，
#   而 start.bat 只传递 STT_DEVICE，用户改 .env 看不出任何效果。
#
#   环境变量优先于 .env（load_dotenv 默认不覆盖已有变量），
#   这样 start.bat / Docker 传入的值仍然说了算。
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
try:
    from dotenv import load_dotenv

    # 同时尝试项目根与当前工作目录，覆盖两种启动方式
    for _candidate in (
        os.path.join(_PROJECT_ROOT, ".env"),
        os.path.join(os.getcwd(), ".env"),
    ):
        if os.path.isfile(_candidate):
            load_dotenv(_candidate, override=False)
            break
except ImportError:  # pragma: no cover
    pass

# ── HuggingFace 镜像与下载通道（必须在任何 HF 导入之前设置） ──
#
# HF_ENDPOINT：国内直连 huggingface.co 会超时，用镜像站。
#
# HF_HUB_DISABLE_XET：**必须**禁用，否则模型下载会卡死。
#   huggingface_hub 新版默认走 Xet 存储后端，权重文件从
#   cas-bridge.xethub.hf.co 下载 —— 该域名**不受 HF_ENDPOINT 影响**，
#   在国内表现为「元数据请求全部 200，但 model.bin 停在 0 字节」。
#   实测：启用 Xet 时 30 秒下载 0 MB；禁用后同一条 1.5GB 的模型
#   146 秒下载完成（约 10 MB/s，走 hf-mirror）。
_hf_endpoint = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = _hf_endpoint
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

import numpy as np
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from streaming_transcriber import StreamingTranscriber, preload_shared_models
from zh_convert import to_simplified
from stt_config import load_config

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("stt_service")

# ── 配置（环境变量 + .env，解析逻辑见 stt_config.py） ──
_cfg = load_config()
STT_MODEL = _cfg.model
STT_DEVICE = _cfg.device
STT_COMPUTE_TYPE = _cfg.compute_type
VAD_SILENCE_TIMEOUT = _cfg.vad_silence_timeout

# ── 应用 ──
app = FastAPI(title="STT Service", version="1.0.0")

# 全局转录器（单例，所有连接共享模型）
_transcriber: Optional[StreamingTranscriber] = None
_model_loaded: bool = False
_model_error: Optional[str] = None
# 预热是否完成（用于让 /health 反映真实可用性）
_preload_done: bool = False


@app.on_event("startup")
async def _preload_models():
    """启动时在后台线程预热模型。

    为什么不在模块导入阶段做：加载要十几秒，会拖住 uvicorn 起来；
    放到 startup 的后台线程里，服务可以立即响应 /health，
    等用户真正开始监听时模型通常已经就绪。
    """
    global _preload_done, _model_loaded, _model_error

    def _work():
        global _preload_done, _model_loaded, _model_error
        try:
            # preload 返回是否真的成功 —— 它内部会吞掉异常并逐个记录，
            # 不能只看「有没有抛异常」就认定就绪。
            ready = preload_shared_models(STT_MODEL, STT_DEVICE, STT_COMPUTE_TYPE)
            _model_loaded = bool(ready)
            if ready:
                logger.info("模型预热完成，连接将立即可用")
            else:
                _model_error = "模型预热未完成（详见上方日志）"
                logger.warning("模型预热未全部完成，首个连接时会重试")
        except Exception as exc:
            _model_loaded = False
            _model_error = str(exc)
            logger.error("预热过程异常（首个连接时会重试）: %s", exc)
        finally:
            _preload_done = True

    asyncio.get_running_loop().run_in_executor(None, _work)


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
    """健康检查 — 返回模型和设备状态

    status 语义：
      ok      模型已就绪，连接可立即使用
      loading 正在预热（服务可用，只是首次连接会稍慢）
      error   预热失败（会在首次连接时重试）
    """
    if _model_loaded:
        status = "ok"
    elif not _preload_done:
        status = "loading"
    else:
        status = "error"

    return JSONResponse({
        "status": status,
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
            # 与 WebSocket 流式路径保持一致：不给这句提示的话，
            # 短音频会退化成没有标点的连续文字。
            initial_prompt=StreamingTranscriber.INITIAL_PROMPT,
        )
        text = "".join(seg.text for seg in segments)

        return JSONResponse({
            # 与 WebSocket 流式路径保持一致：繁转简后再返回，
            # 否则两条路径输出繁简不同，用户会以为识别结果不一致。
            "text": to_simplified(text).strip(),
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
        # 复用进程级共享模型：Whisper 加载约 11 秒，每连接各加载一份
        # 会让每次点开监听都要等十几秒，日志里也会出现成串的
        # 「Whisper model loaded」。StreamingTranscriber 只有会话状态
        # （VAD 状态机、音频缓冲、回调）是按连接隔离的。
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

            # 客户端主动关闭时，receive() 返回的是 disconnect 消息而非抛异常。
            # 若不在这里 break，下一次 receive() 会报
            # 「Cannot call "receive" once a disconnect message has been received」，
            # 被下方 except Exception 记成 ERROR —— 实际只是正常挂断。
            if data.get("type") == "websocket.disconnect":
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
