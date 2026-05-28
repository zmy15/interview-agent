"""岗位存储服务单元测试 — JSON 文件持久化 + 线程安全"""

import json
import os
import tempfile
import threading

import pytest

from services.position_store import PositionStore


@pytest.fixture
def store():
    """创建临时文件的 PositionStore 实例"""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    # 重置单例
    PositionStore._instance = None
    s = PositionStore(file_path=path)
    yield s
    PositionStore._instance = None
    try:
        os.remove(path)
    except OSError:
        pass


# ============================================================
#  CRUD 操作
# ============================================================

class TestPositionCRUD:
    """岗位 CRUD"""

    def test_create_position(self, store):
        """创建岗位"""
        pos = store.create("后端工程师", "负责后端开发")
        assert pos.name == "后端工程师"
        assert pos.description == "负责后端开发"
        assert pos.position_type in ("技术岗", "未知")

    def test_create_duplicate_raises(self, store):
        """重复创建抛异常"""
        store.create("测试岗位")
        with pytest.raises(ValueError, match="已存在"):
            store.create("测试岗位")

    def test_get_existing(self, store):
        """获取存在的岗位"""
        store.create("前端工程师")
        pos = store.get("前端工程师")
        assert pos is not None
        assert pos.name == "前端工程师"

    def test_get_nonexistent(self, store):
        """获取不存在的岗位"""
        pos = store.get("不存在")
        assert pos is None

    def test_list_all(self, store):
        """列出所有岗位"""
        store.create("岗位A")
        store.create("岗位B")
        all_pos = store.list_all()
        assert len(all_pos) >= 2
        names = [p.name for p in all_pos]
        assert "岗位A" in names
        assert "岗位B" in names

    def test_update_description(self, store):
        """更新岗位描述"""
        store.create("测试岗", "原始描述")
        updated = store.update("测试岗", "新描述")
        assert updated is not None
        assert updated.description == "新描述"

        # 确认持久化了
        pos = store.get("测试岗")
        assert pos.description == "新描述"

    def test_update_nonexistent(self, store):
        """更新不存在的岗位"""
        result = store.update("不存在岗位", "描述")
        assert result is None

    def test_delete_existing(self, store):
        """删除存在的岗位"""
        store.create("要删除的岗")
        assert store.delete("要删除的岗") is True
        assert store.get("要删除的岗") is None

    def test_delete_nonexistent(self, store):
        """删除不存在的岗位"""
        assert store.delete("不存在") is False


# ============================================================
#  JD 管理
# ============================================================

class TestJDManagement:
    """JD（岗位要求）管理"""

    @pytest.fixture(autouse=True)
    def setup(self, store):
        store.create("JD测试岗", "测试")
        yield
        store.delete("JD测试岗")

    def test_add_jd(self, store):
        """添加 JD"""
        jd = store.add_jd("JD测试岗", "需要 3 年 Python 经验")
        assert jd is not None
        assert jd.content == "需要 3 年 Python 经验"
        assert jd.id is not None

    def test_add_jd_nonexistent_position(self, store):
        """向不存在的岗位添加 JD"""
        jd = store.add_jd("不存在岗位", "内容")
        assert jd is None

    def test_remove_jd(self, store):
        """删除 JD"""
        jd = store.add_jd("JD测试岗", "JD内容")
        assert store.remove_jd("JD测试岗", jd.id) is True

        # 确认已删除
        pos = store.get("JD测试岗")
        jd_ids = [j.id for j in pos.jds]
        assert jd.id not in jd_ids

    def test_remove_nonexistent_jd(self, store):
        """删除不存在的 JD"""
        assert store.remove_jd("JD测试岗", "fake-id-12345") is False

    def test_update_jd(self, store):
        """修改 JD 内容"""
        jd = store.add_jd("JD测试岗", "旧内容")
        updated = store.update_jd("JD测试岗", jd.id, "新内容")
        assert updated is not None
        assert updated.content == "新内容"

    def test_update_nonexistent_jd(self, store):
        """修改不存在的 JD"""
        result = store.update_jd("JD测试岗", "fake-id", "新内容")
        assert result is None


# ============================================================
#  持久化
# ============================================================

class TestPersistence:
    """数据持久化测试"""

    def test_data_persists_to_file(self, store):
        """创建岗位后数据写入文件"""
        store.create("持久化测试", "描述")
        with open(store._file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "持久化测试" in data["positions"]

    def test_reload_from_file(self, store):
        """从文件重新加载数据"""
        store.create("重载测试")
        # 创建新实例读取同一文件
        new_store = PositionStore(file_path=store._file_path)
        pos = new_store.get("重载测试")
        assert pos is not None


# ============================================================
#  线程安全
# ============================================================

class TestThreadSafety:
    """多线程并发安全"""

    def test_concurrent_creates(self, store):
        """并发创建不同岗位不丢数据"""
        results = []
        errors = []

        def create_pos(name):
            try:
                r = store.create(name)
                results.append(r)
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=create_pos, args=(f"并发岗{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 10
        all_pos = store.list_all()
        assert len(all_pos) >= 10
