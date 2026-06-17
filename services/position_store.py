"""岗位存储服务 — 数据库持久化（平台模式）

完全替代 JSON 文件存储，所有数据存入 PostgreSQL/SQLite。
保持与旧版 PositionStore 相同的方法签名（改为异步）。
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.schemas import PositionResponse, JDResponse
from models.db_models import Position, JD
from utils.position_classifier import classify_position

logger = logging.getLogger(__name__)


class PositionStore:
    """岗位存储 — 数据库持久化，线程安全由数据库保证"""

    def __init__(self, db: AsyncSession):
        self._db = db

    # ========== 岗位 CRUD ==========

    async def create(self, name: str, description: str = "", user_id: Optional[str] = None) -> PositionResponse:
        """创建岗位"""
        existing = await self._db.execute(
            select(Position).where(Position.name == name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"岗位 '{name}' 已存在")

        now = datetime.now(timezone.utc)
        pos = Position(
            name=name,
            description=description,
            position_type=classify_position(name),
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        self._db.add(pos)
        await self._db.flush()
        # 新建岗位无 JD，直接构造响应避免触发懒加载
        logger.info(f"Position created: {name} (user={user_id})")
        return PositionResponse(
            name=pos.name,
            description=pos.description or "",
            position_type=pos.position_type or "未知",
            jds=[],
            created_at=pos.created_at.isoformat() if pos.created_at else "",
            updated_at=pos.updated_at.isoformat() if pos.updated_at else "",
        )

    async def get(self, name: str) -> Optional[PositionResponse]:
        """查询单个岗位（按名称）"""
        result = await self._db.execute(
            select(Position).options(selectinload(Position.jds)).where(Position.name == name)
        )
        pos = result.scalar_one_or_none()
        return await self._to_response(pos) if pos else None

    async def get_by_id(self, position_id: str) -> Optional[PositionResponse]:
        """按 ID 查询岗位"""
        result = await self._db.execute(
            select(Position).options(selectinload(Position.jds)).where(Position.id == position_id)
        )
        pos = result.scalar_one_or_none()
        return await self._to_response(pos) if pos else None

    async def list_all(
        self,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> list[PositionResponse]:
        """列出所有岗位（支持按用户/团队过滤）"""
        conditions = []
        if user_id:
            conditions.append(Position.user_id == user_id)
        if team_id:
            conditions.append(Position.team_id == team_id)

        query = select(Position).options(selectinload(Position.jds)).order_by(Position.updated_at.desc())
        if conditions:
            query = query.where(*conditions)

        result = await self._db.execute(query)
        positions = result.scalars().all()
        return [await self._to_response(p) for p in positions]

    async def update(self, name: str, description: str) -> Optional[PositionResponse]:
        """更新岗位描述"""
        result = await self._db.execute(
            select(Position).options(selectinload(Position.jds)).where(Position.name == name)
        )
        pos = result.scalar_one_or_none()
        if not pos:
            return None
        pos.description = description
        pos.updated_at = datetime.now(timezone.utc)
        await self._db.flush()
        return await self._to_response(pos)

    async def delete(self, name: str) -> bool:
        """删除岗位（级联删除 JD）"""
        result = await self._db.execute(
            select(Position).where(Position.name == name)
        )
        pos = result.scalar_one_or_none()
        if not pos:
            return False
        await self._db.delete(pos)
        await self._db.flush()
        logger.info(f"Position deleted: {name}")
        return True

    # ========== JD CRUD ==========

    async def add_jd(self, position_name: str, content: str) -> Optional[JDResponse]:
        """为岗位添加 JD"""
        result = await self._db.execute(
            select(Position).options(selectinload(Position.jds)).where(Position.name == position_name)
        )
        pos = result.scalar_one_or_none()
        if not pos:
            return None

        jd = JD(
            position_id=pos.id,
            content=content,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(jd)
        pos.updated_at = datetime.now(timezone.utc)
        await self._db.flush()
        return JDResponse(id=jd.id, content=jd.content, created_at=jd.created_at.isoformat())

    async def remove_jd(self, position_name: str, jd_id: str) -> bool:
        """删除指定 JD"""
        result = await self._db.execute(
            select(Position).options(selectinload(Position.jds)).where(Position.name == position_name)
        )
        pos = result.scalar_one_or_none()
        if not pos:
            return False

        jd_result = await self._db.execute(
            select(JD).where(JD.id == jd_id, JD.position_id == pos.id)
        )
        jd = jd_result.scalar_one_or_none()
        if not jd:
            return False

        await self._db.delete(jd)
        pos.updated_at = datetime.now(timezone.utc)
        await self._db.flush()
        return True

    async def update_jd(self, position_name: str, jd_id: str, content: str) -> Optional[JDResponse]:
        """修改指定 JD 内容"""
        result = await self._db.execute(
            select(Position).options(selectinload(Position.jds)).where(Position.name == position_name)
        )
        pos = result.scalar_one_or_none()
        if not pos:
            return None

        jd_result = await self._db.execute(
            select(JD).where(JD.id == jd_id, JD.position_id == pos.id)
        )
        jd = jd_result.scalar_one_or_none()
        if not jd:
            return None

        jd.content = content
        jd.created_at = datetime.now(timezone.utc)
        pos.updated_at = datetime.now(timezone.utc)
        await self._db.flush()
        return JDResponse(id=jd.id, content=jd.content, created_at=jd.created_at.isoformat())

    @staticmethod
    async def _to_response(pos: Position) -> PositionResponse:
        """将 ORM 模型转换为 Pydantic 响应（加载 JD 列表）"""
        return PositionResponse(
            name=pos.name,
            description=pos.description or "",
            position_type=pos.position_type or "未知",
            jds=[
                JDResponse(
                    id=jd.id,
                    content=jd.content,
                    created_at=jd.created_at.isoformat() if jd.created_at else "",
                )
                for jd in (pos.jds or [])
            ],
            created_at=pos.created_at.isoformat() if pos.created_at else "",
            updated_at=pos.updated_at.isoformat() if pos.updated_at else "",
        )
