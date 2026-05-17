"""
面试 Agent 后端 — FastAPI + DeepSeek
无状态设计，SSE 流式输出，支持 RAG 向量知识库 + 联网搜索
"""

import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import chat, upload, interview, position, knowledge

# ============ 日志配置 ============

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ============ FastAPI 应用 ============

app = FastAPI(
    title="Interview Agent API",
    description="面试 Agent 后端服务 — DeepSeek 驱动 + RAG 增强",
    version="1.0.0",
)

# CORS 中间件（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(interview.router)
app.include_router(position.router)
app.include_router(knowledge.router)


# ============ 全局异常处理 ============

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"服务器内部错误: {str(exc)}"},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


# ============ 根路径 ============

@app.get("/")
async def root():
    return {
        "message": "Interview Agent Backend is running",
        "version": "1.0.0",
        "docs": "/docs",
    }


# ============ 生产模式：托管前端静态文件 ============

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    # 前端通过 /api/* 访问后端，生产模式下需要注册 /api 前缀路由
    app.include_router(chat.router, prefix="/api")
    app.include_router(upload.router, prefix="/api")
    app.include_router(interview.router, prefix="/api")
    app.include_router(position.router, prefix="/api")
    app.include_router(knowledge.router, prefix="/api")

    # 挂载静态资源（JS/CSS/图片等）
    if os.path.isdir(os.path.join(FRONTEND_DIST, "assets")):
        app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        """SPA 回退：所有非 API/非静态资源路由返回 index.html"""
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

    logger.info(f"Frontend static files served from: {FRONTEND_DIST}")
    logger.info("API routes also available under /api prefix for production SPA mode")

