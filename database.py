"""
数据库配置 — SQLAlchemy 2.0 Async + PostgreSQL/SQLite 双模式
开发环境自动使用 SQLite，生产环境使用 PostgreSQL
"""

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings


# ── 数据库 URL 构建 ──
# 优先使用 DATABASE_URL，否则根据 DB_TYPE 自动构建
_DATABASE_URL = settings.DATABASE_URL
if not _DATABASE_URL:
    if settings.DB_TYPE == "postgresql":
        _DATABASE_URL = (
            f"postgresql+asyncpg://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
        )
    else:
        # SQLite（开发环境）— 使用绝对路径确保不受工作目录影响
        _DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(_DB_DIR, exist_ok=True)
        _DATABASE_URL = f"sqlite+aiosqlite:///{_DB_DIR}/interview_platform.db"


# ── 异步引擎 ──
_connect_args = {}
if settings.DB_TYPE == "sqlite":
    _connect_args = {"check_same_thread": False}

engine = create_async_engine(
    _DATABASE_URL,
    echo=settings.DB_ECHO,
    connect_args=_connect_args,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)

# ── 异步 Session 工厂 ──
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── 声明式基类 ──
class Base(DeclarativeBase):
    pass


# ── FastAPI 依赖注入：获取数据库会话 ──
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """每个请求获取一个独立的数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── 初始化：创建所有表 ──
async def init_db():
    """应用启动时自动建表"""
    # 确保所有 ORM 模型被注册到 Base.metadata
    import models.db_models  # noqa: F401 — 触发模型注册
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

