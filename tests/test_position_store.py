"""岗位存储服务单元测试 — 异步数据库持久化与多用户隔离。"""

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from database import Base
from models.db_models import User
from services.position_store import PositionStore

pytestmark = pytest.mark.anyio


@pytest.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )

    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
        )

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest.fixture
def store(
    db_session: AsyncSession,
) -> PositionStore:
    return PositionStore(db_session)


@pytest.fixture
async def user_id(
    db_session: AsyncSession,
) -> str:
    user = User(
        email="position-store@example.com",
        hashed_password="not-used-in-this-test",
        display_name="Position Store Test",
    )

    db_session.add(user)
    await db_session.flush()

    return user.id


# ============================================================
#  CRUD 操作
# ============================================================


class TestPositionCRUD:
    """岗位 CRUD"""

    async def test_create_position(
        self,
        store: PositionStore,
        user_id: str,
    ) -> None:
        position = await store.create(
            "后端工程师",
            "负责后端开发",
            user_id=user_id,
        )

        assert position.name == "后端工程师"
        assert position.description == "负责后端开发"
        assert position.position_type in {
            "技术岗",
            "未知",
        }

    async def test_create_duplicate_raises(
        self,
        store: PositionStore,
        user_id: str,
    ) -> None:
        await store.create(
            "测试岗位",
            user_id=user_id,
        )

        with pytest.raises(
            ValueError,
            match="已存在",
        ):
            await store.create(
                "测试岗位",
                user_id=user_id,
            )

    async def test_get_existing(
        self,
        store: PositionStore,
        user_id: str,
    ) -> None:
        await store.create(
            "前端工程师",
            user_id=user_id,
        )

        position = await store.get("前端工程师")

        assert position is not None
        assert position.name == "前端工程师"

    async def test_get_nonexistent(
        self,
        store: PositionStore,
    ) -> None:
        position = await store.get("不存在")

        assert position is None

    async def test_list_all(
        self,
        store: PositionStore,
        user_id: str,
    ) -> None:
        await store.create(
            "岗位A",
            user_id=user_id,
        )
        await store.create(
            "岗位B",
            user_id=user_id,
        )

        positions = await store.list_all(
            user_id=user_id,
        )
        names = [position.name for position in positions]

        assert len(positions) == 2
        assert "岗位A" in names
        assert "岗位B" in names

    async def test_update_description(
        self,
        store: PositionStore,
        user_id: str,
    ) -> None:
        await store.create(
            "测试岗",
            "原始描述",
            user_id=user_id,
        )

        updated = await store.update(
            "测试岗",
            "新描述",
        )

        assert updated is not None
        assert updated.description == "新描述"

        position = await store.get("测试岗")

        assert position is not None
        assert position.description == "新描述"

    async def test_update_nonexistent(
        self,
        store: PositionStore,
    ) -> None:
        result = await store.update(
            "不存在岗位",
            "描述",
        )

        assert result is None

    async def test_delete_existing(
        self,
        store: PositionStore,
        user_id: str,
    ) -> None:
        await store.create(
            "要删除的岗",
            user_id=user_id,
        )

        deleted = await store.delete("要删除的岗")
        position = await store.get("要删除的岗")

        assert deleted is True
        assert position is None

    async def test_delete_nonexistent(
        self,
        store: PositionStore,
    ) -> None:
        deleted = await store.delete("不存在")

        assert deleted is False


class TestJDManagement:
    """JD 数据库操作测试。"""

    @pytest.fixture(autouse=True)
    async def setup_position(
        self,
        store: PositionStore,
        user_id: str,
    ) -> None:
        await store.create(
            "JD测试岗",
            "测试",
            user_id=user_id,
        )

    async def test_add_jd(
        self,
        store: PositionStore,
    ) -> None:
        jd = await store.add_jd(
            "JD测试岗",
            "需要 3 年 Python 经验",
        )

        assert jd is not None
        assert jd.content == "需要 3 年 Python 经验"
        assert jd.id

    async def test_add_jd_to_nonexistent_position(
        self,
        store: PositionStore,
    ) -> None:
        jd = await store.add_jd(
            "不存在岗位",
            "测试内容",
        )

        assert jd is None

    async def test_remove_jd(
        self,
        store: PositionStore,
    ) -> None:
        jd = await store.add_jd(
            "JD测试岗",
            "待删除内容",
        )
        assert jd is not None

        removed = await store.remove_jd(
            "JD测试岗",
            jd.id,
        )
        position = await store.get("JD测试岗")

        assert removed is True
        assert position is not None
        assert position.jds == []

    async def test_remove_nonexistent_jd(
        self,
        store: PositionStore,
    ) -> None:
        removed = await store.remove_jd(
            "JD测试岗",
            "missing-jd",
        )

        assert removed is False

    async def test_update_jd(
        self,
        store: PositionStore,
    ) -> None:
        jd = await store.add_jd(
            "JD测试岗",
            "原始内容",
        )
        assert jd is not None

        updated = await store.update_jd(
            "JD测试岗",
            jd.id,
            "修改后的内容",
        )

        assert updated is not None
        assert updated.content == "修改后的内容"

    async def test_update_nonexistent_jd(
        self,
        store: PositionStore,
    ) -> None:
        updated = await store.update_jd(
            "JD测试岗",
            "missing-jd",
            "修改内容",
        )

        assert updated is None


class TestPersistence:
    """数据库持久化测试。"""

    async def test_data_persists_between_sessions(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        store = PositionStore(db_session)

        await store.create(
            "持久化测试岗",
            "测试数据是否保存",
            user_id=user_id,
        )
        await db_session.commit()

        session_factory = async_sessionmaker(
            db_session.bind,
            expire_on_commit=False,
        )

        async with session_factory() as new_session:
            new_store = PositionStore(new_session)
            position = await new_store.get(
                "持久化测试岗",
            )

        assert position is not None
        assert position.description == "测试数据是否保存"


class TestUserIsolation:
    """多用户数据隔离测试。"""

    async def test_different_users_can_create_same_position_name(
        self,
        db_session: AsyncSession,
        user_id: str,
    ) -> None:
        second_user = User(
            email="second-user@example.com",
            hashed_password="not-used",
            display_name="Second User",
        )
        db_session.add(second_user)
        await db_session.flush()

        store = PositionStore(db_session)

        first_position = await store.create(
            "算法工程师",
            "用户 A 的岗位",
            user_id=user_id,
        )
        second_position = await store.create(
            "算法工程师",
            "用户 B 的岗位",
            user_id=second_user.id,
        )

        assert first_position.description == "用户 A 的岗位"
        assert second_position.description == "用户 B 的岗位"
