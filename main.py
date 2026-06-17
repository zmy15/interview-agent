"""
面试 Agent 后端 — FastAPI + DeepSeek
平台化架构：用户系统 + 会话持久化 + 分析仪表盘
SSE 流式输出，支持 RAG 向量知识库 + 联网搜索
"""

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from routers import chat, upload, interview, position, knowledge, auth, sessions, analytics, question_bank

# ============ 日志配置 ============

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ============ 应用生命周期 ============

async def _seed_question_bank():
    """从种子数据库导入题库数据（仅在 question_bank 表为空时执行）"""
    import json
    from sqlalchemy import select, func
    from models.db_models import QuestionBankItem
    from database import async_session_factory

    seed_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "question_bank.db")
    if not os.path.exists(seed_db_path):
        logger.info("📭 题库种子文件不存在，跳过导入")
        return

    async with async_session_factory() as session:
        # 检查是否已导入过
        result = await session.execute(select(func.count()).select_from(QuestionBankItem))
        if result.scalar() and result.scalar() > 0:
            return

        # 从种子 DB 读取（同步 sqlite3，只读）
        import sqlite3
        seed_conn = sqlite3.connect(f"file:{seed_db_path}?mode=ro", uri=True)
        seed_rows = seed_conn.execute(
            "SELECT id, user_id, team_id, title, content, category, difficulty, "
            "tags, expected_answer, is_public, usage_count, created_at, updated_at "
            "FROM question_bank"
        ).fetchall()
        seed_conn.close()

        if not seed_rows:
            return

        for row in seed_rows:
            tags_raw = row[7]
            tags = json.loads(tags_raw) if isinstance(tags_raw, str) else (tags_raw or [])
            item = QuestionBankItem(
                id=row[0],
                user_id=row[1],
                team_id=row[2],
                title=row[3],
                content=row[4],
                category=row[5],
                difficulty=row[6],
                tags=tags,
                expected_answer=row[8],
                is_public=bool(row[9]) if row[9] is not None else False,
                usage_count=row[10] or 0,
                created_at=row[11],
                updated_at=row[12],
            )
            session.add(item)

        await session.commit()
        logger.info(f"🌱 题库种子数据已导入: {len(seed_rows)} 题")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动/关闭时的初始化与清理"""
    # 启动：初始化数据库表
    try:
        from database import init_db
        await init_db()
        logger.info("✅ 数据库初始化完成")
    except Exception as e:
        logger.warning(f"⚠ 数据库初始化失败（将使用 JSON 回退）: {e}")

    # 启动：自动导入题库种子数据（仅首次）
    try:
        await _seed_question_bank()
    except Exception as e:
        logger.warning(f"⚠ 题库种子数据导入跳过: {e}")

    # 启动：检查依赖
    from config import settings as _s
    if _s.AUTH_REQUIRED:
        logger.info("🔒 认证模式已开启 — 所有 API 需要登录")
    else:
        logger.info("🔓 单用户模式 — 无需登录即可使用")

    yield  # 应用运行中...

    # 关闭：清理资源
    try:
        from database import engine
        await engine.dispose()
        logger.info("✅ 数据库连接已关闭")
    except Exception:
        pass


# ============ FastAPI 应用 ============

app = FastAPI(
    title="Interview Agent Platform API",
    description="AI 模拟面试平台 — DeepSeek 驱动 + RAG 增强 + 用户系统",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS 中间件（允许前端跨域访问）
# 注意：allow_credentials=True 时不能使用 "*"，必须指定具体域名
cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由（无前缀版本，开发模式）
app.include_router(chat.router)
app.include_router(upload.router)
app.include_router(interview.router)
app.include_router(position.router)
app.include_router(knowledge.router)
app.include_router(auth.router)          # 认证路由
app.include_router(sessions.router)      # 会话历史
app.include_router(analytics.router)     # 分析仪表盘
app.include_router(question_bank.router) # 题库管理

# ── 条件注册语音路由（默认关闭，需 .env 中启用） ──
if settings.VOICE_ENABLED or settings.STT_ENABLED:
    try:
        from routers import stt
        app.include_router(stt.router)
        logger.info("🎤 STT 语音识别路由已注册")
    except ImportError:
        logger.warning("⚠ STT 路由模块未找到，跳过注册")

if settings.VOICE_ENABLED or settings.TTS_ENABLED:
    try:
        from routers import tts
        app.include_router(tts.router)
        logger.info("🔊 TTS 语音合成路由已注册")
    except ImportError:
        logger.warning("⚠ TTS 路由模块未找到，跳过注册")


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
    app.include_router(auth.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(analytics.router, prefix="/api")
    app.include_router(question_bank.router, prefix="/api")

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

