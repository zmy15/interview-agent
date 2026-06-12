# TTS 微服务 — Piper TTS（仅 CPU）
# 构建: docker build -t interview-tts .
# 运行: docker run -p 8002:8000 -v tts_models:/app/models interview-tts

FROM python:3.11-slim

# 安装 Piper TTS 所需的系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . .

# 模型存储目录
RUN mkdir -p /app/models

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
