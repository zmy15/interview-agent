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


# ── 初始化：创建所有表 + 自动导入 LeetCode 题库 ──
async def init_db():
    """应用启动时自动建表并导入内置题库"""
    # 确保所有 ORM 模型被注册到 Base.metadata
    import models.db_models  # noqa: F401 — 触发模型注册
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── 自动导入 LeetCode 内置题库（首次启动，仅导入一次） ──
    await _seed_leetcode()


# ── 内置题库导入（首次启动自动执行） ──

_SEED_FLAG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", ".leetcode_seeded")


async def _seed_leetcode():
    """自动导入 LeetCode 题库（首次启动或表为空时自动执行）"""
    leetcode_file = os.path.join(os.path.dirname(__file__), "data", "leetcode_problems.json")
    if not os.path.exists(leetcode_file):
        return

    import json
    import logging
    from datetime import datetime, timezone
    from models.db_models import QuestionBankItem
    from sqlalchemy import select, func

    logger = logging.getLogger(__name__)

    # 检查是否已导入：种子标记 + 表中实际有数据
    already_seeded = os.path.exists(_SEED_FLAG_FILE)
    if already_seeded:
        # 二次确认：表中确实有数据才跳过
        async with async_session_factory() as s:
            r = await s.execute(select(func.count()).select_from(QuestionBankItem))
            count = r.scalar() or 0
            if count > 0:
                return  # 已有数据，跳过
            # 标记存在但表为空 → 重新导入
            logger.info("Seed marker exists but table is empty, re-seeding...")
            os.remove(_SEED_FLAG_FILE)
    now = datetime.now(timezone.utc)

    try:
        with open(leetcode_file, "r", encoding="utf-8") as f:
            problems = json.load(f)
    except Exception:
        return

    async with async_session_factory() as session:
        try:
            count = 0
            for p in problems:
                title = p.get("title_cn", p.get("title", ""))
                if not title:
                    continue
                item = QuestionBankItem(
                    user_id=None,  # 系统内置，全员可见
                    title=title,
                    content=f"## {title} (LeetCode #{p.get('id', '')})\n\n"
                            f"{p.get('description', '')}\n\n"
                            f"**示例**:\n{p.get('examples', '')}\n\n"
                            f"**提示**: {p.get('hint', '无')}",
                    category="algorithm",
                    difficulty=p.get("difficulty", "medium"),
                    tags=p.get("tags", []),
                    is_public=True,
                    created_at=now,
                )
                session.add(item)
                count += 1

            await session.commit()
            # 标记已导入
            with open(_SEED_FLAG_FILE, "w") as f:
                f.write("done")
            logger.info(f"✅ LeetCode 题库自动导入完成：{count} 题")
        except Exception as e:
            await session.rollback()
            logger.warning(f"⚠ LeetCode 题库导入失败: {e}")
