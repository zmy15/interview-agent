"""
TTS 语音合成微服务 — Piper TTS + FastAPI
端点:
  - POST /synthesize      批量合成（HTTP JSON → WAV，兜底）
  - WS   /stream           WebSocket 流式合成（按句 PCM chunk）
  - GET  /health          健康检查
"""

import asyncio
import io
import json
import logging
import os
import sys
import wave
from typing import Optional

# ── HuggingFace 镜像（必须在任何 HF 导入之前设置） ──
_hf_endpoint = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = _hf_endpoint

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response

# ── 日志 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tts_service")

# ── 配置（环境变量） ──
TTS_VOICE = os.getenv("TTS_VOICE", "zh_CN-huayan-medium")
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.0"))
# 模型目录
TTS_MODEL_DIR = os.getenv("TTS_MODEL_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tts_models"))

# Piper 语音在 HF 上的路径规则: {lang}/{lang_Region}/{name}/{quality}/{voice}.onnx
# 例如: zh_CN-huayan-medium → zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx
def _hf_voice_path(voice: str) -> str:
    parts = voice.split("-")
    if len(parts) >= 3 and parts[-1] in ("low", "medium", "high"):
        quality = parts[-1]
        name = parts[-2]
        lang_region = "-".join(parts[:-2])  # e.g. "zh_CN"
        lang = lang_region.split("_")[0]
        return f"{lang}/{lang_region}/{name}/{quality}/{voice}"
    return voice  # fallback: 直接作为根文件名

# ── 应用 ──
app = FastAPI(title="TTS Service", version="1.0.0")

# 全局语音引擎（单例）
_voice = None
_model_path = ""
_model_loaded: bool = False
_model_error: Optional[str] = None


@app.on_event("startup")
async def startup_event():
    """启动时预加载语音模型"""
    global _model_loaded, _model_error
    try:
        _ensure_voice()
        logger.info("TTS voice model preloaded: %s", TTS_VOICE)
    except Exception as e:
        _model_error = str(e)
        logger.error("TTS voice model preload failed: %s", e)


def _ensure_voice():
    """确保 Piper TTS 语音模型已加载"""
    global _voice, _model_loaded, _model_error, _model_path
    if _voice is not None:
        return _voice

    try:
        import piper.voice

        # 模型路径：HF 子目录优先（下载位置），再检查根目录
        hf_path = _hf_voice_path(TTS_VOICE)
        model_path = os.path.join(TTS_MODEL_DIR, f"{hf_path}.onnx")
        if not os.path.exists(model_path):
            model_path = os.path.join(TTS_MODEL_DIR, f"{TTS_VOICE}.onnx")
        config_path = model_path  # Piper 新版配置嵌入 onnx

        if not os.path.exists(model_path):
            # 自动下载模型（HF 镜像）
            hf_path = _hf_voice_path(TTS_VOICE)
            logger.info("Downloading Piper voice: %s", TTS_VOICE)
            from huggingface_hub import hf_hub_download
            try:
                hf_hub_download(repo_id="rhasspy/piper-voices", filename=f"{hf_path}.onnx", local_dir=TTS_MODEL_DIR)
                model_path = os.path.join(TTS_MODEL_DIR, f"{hf_path}.onnx")
                try:
                    hf_hub_download(repo_id="rhasspy/piper-voices", filename=f"{hf_path}.json", local_dir=TTS_MODEL_DIR)
                    config_path = os.path.join(TTS_MODEL_DIR, f"{hf_path}.json")
                except Exception:
                    # Piper 新版模型配置嵌入在 .onnx 内，.json 不存在是正常的
                    config_path = model_path
            except Exception as dl_err:
                logger.error("Piper download failed: %s", dl_err)
                raise FileNotFoundError(f"Cannot download Piper voice '{TTS_VOICE}'.")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Piper model not found: {model_path}")

        # 确保配置文件存在（Piper 需要 .onnx.json）
        config_json_path = model_path + ".json"
        if not os.path.exists(config_json_path):
            logger.info("Generating Piper config from ONNX metadata...")
            try:
                import onnxruntime as ort
                sess = ort.InferenceSession(model_path)
                meta = sess.get_modelmeta()
                # 从 ONNX 元数据提取配置
                cfg = {}
                if meta.custom_metadata_map:
                    cfg = json.loads(meta.custom_metadata_map.get("piper_config", "{}"))
                if not cfg:
                    # 默认中文配置
                    cfg = {"dataset": "huayan", "audio": {"sample_rate": 22050}, "espeak": {"voice": "cmn"}, "num_symbols": 256, "num_speakers": 1, "phoneme_type": "espeak", "phoneme_id_map": {}, "phonemes": [], "speaker_id_map": {}}
                with open(config_json_path, "w") as f:
                    json.dump(cfg, f)
                logger.info("Config generated: %s", config_json_path)
            except Exception:
                # fallback: Chinese Mandarin config
                with open(config_json_path, "w") as f:
                    json.dump({"audio": {"sample_rate": 22050}, "espeak": {"voice": "cmn"}, "phoneme_type": "espeak", "num_symbols": 256, "num_speakers": 1}, f)

        # 加载模型
        _voice = piper.voice.PiperVoice.load(model_path, config_path=config_json_path)
        global _model_path
        _model_path = model_path
        _model_loaded = True
        logger.info("Piper voice loaded: %s", TTS_VOICE)
        return _voice

    except Exception as e:
        _model_error = str(e)
        logger.error("Failed to load Piper voice: %s", e)
        raise


def _synthesize_audio(text: str) -> bytes:
    """合成文本为 WAV — Piper Python API (audio_int16_bytes)"""
    voice = _ensure_voice()
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(voice.config.sample_rate)
        for chunk in voice.synthesize(text):
            wav_file.writeframes(chunk.audio_int16_bytes)
    wav_buffer.seek(0)
    return wav_buffer.read()


def _synthesize_pcm(text: str) -> bytes:
    """合成文本为原始 PCM 16bit mono"""
    voice = _ensure_voice()
    chunks = []
    for chunk in voice.synthesize(text):
        chunks.append(chunk.audio_int16_bytes)
    return b"".join(chunks)


# ═══════════════════════════════════════════════════════════════
# HTTP 端点
# ═══════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    """健康检查 — 模型未加载时返回 503，前端据此隐藏/显示 TTS 按钮"""
    if not _model_loaded:
        # 尝试加载（首次调用时懒加载）
        try:
            _ensure_voice()
        except Exception:
            pass
    status_code = 200 if _model_loaded else 503
    return JSONResponse({
        "status": "ok" if _model_loaded else "error",
        "voice": TTS_VOICE,
        "speed": TTS_SPEED,
        "error": _model_error,
    }, status_code=status_code)


@app.post("/synthesize")
async def synthesize(request_data: dict):
    """
    批量合成 — 接收 JSON {"text": "..."}，返回完整 WAV。
    兜底方案，当 WebSocket 不可用时使用。
    """
    text = request_data.get("text", "")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)

    try:
        wav_data = _synthesize_audio(text)
        return Response(
            content=wav_data,
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=speech.wav"},
        )
    except Exception as e:
        logger.error("Synthesis error: %s", e)
        return JSONResponse({"error": str(e), "model_loaded": _model_loaded}, status_code=500)


# ═══════════════════════════════════════════════════════════════
# WebSocket 流式端点
# ═══════════════════════════════════════════════════════════════


@app.websocket("/stream")
async def websocket_stream(ws: WebSocket):
    """
    WebSocket 流式合成端点。

    协议：
    Client → Server: {"text": "你好，欢迎。"}
    Server → Client: <binary PCM chunk (16kHz, 16bit, mono)>
    Client → Server: {"text": "请自我介绍。"}
    Server → Client: <binary PCM chunk>
    Client → Server: {"type": "eos"}     # End of Stream
    Server → Client: {"type": "done"}    # 所有合成完毕
    """
    await ws.accept()
    logger.info("TTS WebSocket client connected")

    try:
        # 确保模型已加载
        _ensure_voice()
        await ws.send_json({"type": "ready", "voice": TTS_VOICE})

        while True:
            try:
                data = await ws.receive()
            except WebSocketDisconnect:
                logger.info("TTS WebSocket client disconnected")
                break

            if "text" not in data:
                continue

            try:
                msg = json.loads(data["text"])
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "eos":
                # 文本发送完毕
                await ws.send_json({"type": "done"})
                break

            # 合成文本
            text = msg.get("text", "")
            if text:
                # 在后台线程合成（Piper 是同步的）
                pcm_data = await asyncio.to_thread(_synthesize_pcm, text)
                if pcm_data:
                    await ws.send_bytes(pcm_data)

    except Exception as e:
        logger.error("TTS WebSocket error: %s", e)
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
        logger.info("TTS WebSocket connection closed")


# ═══════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
