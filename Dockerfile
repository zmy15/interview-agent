# ============================================
# 阶段 1: 构建前端
# ============================================
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --silent

COPY frontend/ .
RUN npm run build

# ============================================
# 阶段 2: 安装 Python 依赖
# ============================================
FROM python:3.11-slim AS python-deps

ARG SKIP_RAG=false

WORKDIR /app

COPY requirements.txt requirements-rag.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$SKIP_RAG" != "true" ]; then \
        echo ">>> Installing RAG dependencies..." && \
        pip install --no-cache-dir -r requirements-rag.txt; \
    else \
        echo ">>> SKIP_RAG=true — 跳过 RAG 依赖安装（向量知识库不可用）"; \
    fi

# ============================================
# 阶段 3: 最终运行镜像
# ============================================
FROM python:3.11-slim

WORKDIR /app

# 从构建阶段复制 Python 依赖（系统级安装，无需 --user）
COPY --from=python-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

# 复制后端代码
COPY *.py .
COPY routers/ ./routers/
COPY services/ ./services/
COPY models/ ./models/
COPY prompts/ ./prompts/
COPY utils/ ./utils/
COPY positions.json ./
COPY data/ ./data/
COPY hf_cache/ ./hf_cache/

# 复制前端构建产物（将由 FastAPI 托管）
COPY --from=frontend-builder /frontend/dist ./frontend/dist

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
