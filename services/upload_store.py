"""上传记录存储服务 — 数据库持久化（平台模式）

完全替代 JSON 文件存储，所有数据存入 PostgreSQL/SQLite。
保持与旧版 UploadStore 相同的方法签名（改为异步）。
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.schemas import UploadRecord
from models.db_models import Upload

logger = logging.getLogger(__name__)


class UploadStore:
    """上传记录存储 — 数据库持久化"""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def create(
        self,
        filename: str,
        upload_type: str,
        text: str,
        user_id: Optional[str] = None,
        file_count: int = 1,
        tech_stack: Optional[list[str]] = None,
    ) -> UploadRecord:
        """创建上传记录"""
        preview = text[:200].replace("\n", " ").strip()
        if len(text) > 200:
            preview += "..."

        upload = Upload(
            user_id=user_id,
            filename=filename,
            type=upload_type,
            text=text,
            preview=preview,
            file_count=file_count,
            tech_stack=tech_stack or [],
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(upload)
        await self._db.flush()
        logger.info(f"Upload created: {filename} (type={upload_type}, user={user_id})")
        return self._to_record(upload)

    async def get(self, upload_id: str) -> Optional[UploadRecord]:
        """查询单条记录"""
        result = await self._db.execute(
            select(Upload).where(Upload.id == upload_id)
        )
        upload = result.scalar_one_or_none()
        return self._to_record(upload) if upload else None

    async def list_all(
        self,
        upload_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> list[UploadRecord]:
        """列出所有记录，可按类型和用户过滤"""
        conditions = []
        if upload_type:
            conditions.append(Upload.type == upload_type)
        if user_id:
            conditions.append(Upload.user_id == user_id)

        query = select(Upload).order_by(Upload.created_at.desc())
        if conditions:
            query = query.where(*conditions)

        result = await self._db.execute(query)
        uploads = result.scalars().all()
        return [self._to_record(u) for u in uploads]

    async def delete(self, upload_id: str) -> bool:
        """删除记录"""
        result = await self._db.execute(
            select(Upload).where(Upload.id == upload_id)
        )
        upload = result.scalar_one_or_none()
        if not upload:
            return False
        await self._db.delete(upload)
        await self._db.flush()
        return True

    async def delete_all(
        self,
        upload_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> int:
        """删除所有记录，返回删除数量"""
        conditions = []
        if upload_type:
            conditions.append(Upload.type == upload_type)
        if user_id:
            conditions.append(Upload.user_id == user_id)

        count_query = select(func.count()).select_from(Upload)
        if conditions:
            count_query = count_query.where(*conditions)
        result = await self._db.execute(count_query)
        count = result.scalar() or 0

        del_query = delete(Upload)
        if conditions:
            del_query = del_query.where(*conditions)
        await self._db.execute(del_query)
        await self._db.flush()

        return count

    @staticmethod
    def _to_record(u: Upload) -> UploadRecord:
        """ORM → Pydantic"""
        return UploadRecord(
            id=u.id,
            filename=u.filename,
            type=u.type,
            text=u.text,
            preview=u.preview or "",
            file_count=u.file_count or 1,
            tech_stack=u.tech_stack or [],
            created_at=u.created_at.isoformat() if u.created_at else "",
        )
