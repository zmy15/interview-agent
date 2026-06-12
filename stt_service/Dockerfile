# STT 微服务 — CPU 版本
# 构建: docker build -t interview-stt:cpu .
# 运行: docker run -p 8001:8000 -v stt_models:/app/models interview-stt:cpu

FROM python:3.11-slim

# 安装 ffmpeg（音频转码）
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY . .

# 模型存储目录
RUN mkdir -p /app/models

# 健康检查端口
EXPOSE 8000

# 启动（模型在首次请求时懒加载）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
