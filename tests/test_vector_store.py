"""向量存储服务单元测试 — FAISS 索引 + 完整性校验"""

import hashlib
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from services.vector_store import (
    VectorStoreManager,
    _format_duration,
    _format_progress_bar,
    is_vector_store_available,
)


# ============================================================
#  工具函数
# ============================================================

class TestFormatProgressBar:
    """ASCII 进度条"""

    def test_zero_total(self):
        bar = _format_progress_bar(0, 0)
        assert "0/0" in bar

    def test_partial(self):
        bar = _format_progress_bar(5, 10)
        assert "5/10" in bar
        assert "50%" in bar

    def test_complete(self):
        bar = _format_progress_bar(10, 10)
        assert "100%" in bar


class TestFormatDuration:
    """耗时格式化"""

    def test_milliseconds(self):
        assert "ms" in _format_duration(0.5)

    def test_seconds(self):
        result = _format_duration(30.0)
        assert "30.0s" in result

    def test_minutes(self):
        result = _format_duration(125.0)
        assert "2m" in result
        assert "5s" in result


# ============================================================
#  依赖检测
# ============================================================

class TestIsVectorStoreAvailable:
    """向量存储依赖检测"""

    def test_caches_result(self):
        """结果被缓存"""
        import services.vector_store as vs
        vs._VECTOR_STORE_AVAILABLE = None
        result1 = is_vector_store_available()
        result2 = is_vector_store_available()
        assert result1 == result2


# ============================================================
#  VectorStoreManager 基础属性
# ============================================================

class TestVectorStoreManagerInit:
    """初始化与基础属性"""

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_sanitize_collection_name_english(self):
        """英文岗位名 sanitize"""
        vms = VectorStoreManager.__new__(VectorStoreManager)
        vms._settings = MagicMock()
        vms._settings.CHROMA_PERSIST_PATH = tempfile.gettempdir()
        vms._index_dir = tempfile.gettempdir()

        name = vms._sanitize_collection_name("Backend Engineer")
        assert name.startswith("kb_")
        assert "Backend_Engineer" in name

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_sanitize_collection_name_chinese(self):
        """中文岗位名 sanitize"""
        vms = VectorStoreManager.__new__(VectorStoreManager)
        vms._settings = MagicMock()
        vms._settings.CHROMA_PERSIST_PATH = tempfile.gettempdir()
        vms._index_dir = tempfile.gettempdir()

        name = vms._sanitize_collection_name("后端工程师")
        assert name.startswith("kb_")

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_sanitize_short_name_padded(self):
        """超短名称自动补齐"""
        vms = VectorStoreManager.__new__(VectorStoreManager)
        vms._settings = MagicMock()
        vms._settings.CHROMA_PERSIST_PATH = tempfile.gettempdir()
        vms._index_dir = tempfile.gettempdir()

        name = vms._sanitize_collection_name("ab")
        assert name.endswith("_kb")

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_sanitize_long_name_truncated(self):
        """超长名称截断（sanitize 截断到63字符再拼 kb_ 前缀，总长 ≤ 66）"""
        vms = VectorStoreManager.__new__(VectorStoreManager)
        vms._settings = MagicMock()
        vms._settings.CHROMA_PERSIST_PATH = tempfile.gettempdir()
        vms._index_dir = tempfile.gettempdir()

        long_name = "a" * 100
        name = vms._sanitize_collection_name(long_name)
        # safe[:63] + "kb_" = 最多 66 字符
        assert len(name) <= 66

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_sanitize_removes_special_chars(self):
        """特殊字符被替换"""
        vms = VectorStoreManager.__new__(VectorStoreManager)
        vms._settings = MagicMock()
        vms._settings.CHROMA_PERSIST_PATH = tempfile.gettempdir()
        vms._index_dir = tempfile.gettempdir()

        name = vms._sanitize_collection_name("C++/C# 开发")
        assert "++" not in name
        assert "#" not in name
        assert "/" not in name


# ============================================================
#  Collection 元数据
# ============================================================

class TestCollectionMeta:
    """Collection 元数据读写"""

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_save_and_load_position_name(self):
        """保存并重新加载原始岗位名"""
        with tempfile.TemporaryDirectory() as tmpdir:
            vms = VectorStoreManager.__new__(VectorStoreManager)
            vms._settings = MagicMock()
            vms._settings.CHROMA_PERSIST_PATH = tmpdir
            vms._index_dir = tmpdir
            vms._settings.FAISS_VERIFY_INTEGRITY = False

            # Mock _get_coll_dir
            vms._get_coll_dir = lambda c: os.path.join(tmpdir, c)
            vms._get_meta_path = lambda c: os.path.join(tmpdir, c, "collection_meta.json")

            os.makedirs(os.path.join(tmpdir, "kb_test_pos"), exist_ok=True)
            vms._save_collection_meta("kb_test_pos", "测试岗位名称")

            loaded = vms._load_collection_position_name("kb_test_pos")
            assert loaded == "测试岗位名称"

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_load_fallback_when_no_meta(self):
        """元数据文件不存在 → 回退到去前缀名"""
        with tempfile.TemporaryDirectory() as tmpdir:
            vms = VectorStoreManager.__new__(VectorStoreManager)
            vms._settings = MagicMock()
            vms._settings.CHROMA_PERSIST_PATH = tmpdir
            vms._index_dir = tmpdir

            vms._get_meta_path = lambda c: os.path.join(tmpdir, "nonexistent_meta.json")

            name = vms._load_collection_position_name("kb_my_position")
            assert name == "my_position"


# ============================================================
#  完整性校验
# ============================================================

class TestIntegrityCheck:
    """SHA-256 完整性签名与校验"""

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_sign_and_verify_passes(self):
        """签名后校验通过"""
        with tempfile.TemporaryDirectory() as tmpdir:
            vms = VectorStoreManager.__new__(VectorStoreManager)
            vms._settings = MagicMock()
            vms._settings.FAISS_VERIFY_INTEGRITY = True
            vms._settings.CHROMA_PERSIST_PATH = tmpdir
            vms._index_dir = tmpdir

            coll_name = "kb_test_int"
            coll_dir = os.path.join(tmpdir, coll_name)
            os.makedirs(coll_dir, exist_ok=True)

            vms._get_coll_dir = lambda c: os.path.join(tmpdir, c)
            vms._get_pkl_path = lambda c: os.path.join(tmpdir, c, "index.pkl")
            vms._get_sig_path = lambda c: os.path.join(tmpdir, c, "index.pkl.sha256")

            # 创建伪造的 index.pkl
            pkl_path = os.path.join(coll_dir, "index.pkl")
            with open(pkl_path, "wb") as f:
                f.write(b"test pickle content")

            # 签名
            vms._sign_index(coll_name)
            assert os.path.exists(os.path.join(coll_dir, "index.pkl.sha256"))

            # 校验应通过
            vms._verify_index_integrity(coll_name)  # 不抛异常

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_verify_tampered_file_raises(self):
        """文件被篡改 → 抛出 RuntimeError"""
        with tempfile.TemporaryDirectory() as tmpdir:
            vms = VectorStoreManager.__new__(VectorStoreManager)
            vms._settings = MagicMock()
            vms._settings.FAISS_VERIFY_INTEGRITY = True
            vms._settings.CHROMA_PERSIST_PATH = tmpdir
            vms._index_dir = tmpdir

            coll_name = "kb_tamper"
            coll_dir = os.path.join(tmpdir, coll_name)
            os.makedirs(coll_dir, exist_ok=True)

            vms._get_coll_dir = lambda c: os.path.join(tmpdir, c)
            vms._get_pkl_path = lambda c: os.path.join(tmpdir, c, "index.pkl")
            vms._get_sig_path = lambda c: os.path.join(tmpdir, c, "index.pkl.sha256")

            # 创建并签名
            pkl_path = os.path.join(coll_dir, "index.pkl")
            with open(pkl_path, "wb") as f:
                f.write(b"original content")
            vms._sign_index(coll_name)

            # 篡改文件
            with open(pkl_path, "wb") as f:
                f.write(b"tampered content!")

            with pytest.raises(RuntimeError, match="integrity"):
                vms._verify_index_integrity(coll_name)

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_verify_disabled_skips_check(self):
        """校验关闭 → 跳过"""
        with tempfile.TemporaryDirectory() as tmpdir:
            vms = VectorStoreManager.__new__(VectorStoreManager)
            vms._settings = MagicMock()
            vms._settings.FAISS_VERIFY_INTEGRITY = False
            vms._settings.CHROMA_PERSIST_PATH = tmpdir
            vms._index_dir = tmpdir

            coll_name = "kb_skip"
            coll_dir = os.path.join(tmpdir, coll_name)
            os.makedirs(coll_dir, exist_ok=True)

            vms._get_coll_dir = lambda c: os.path.join(tmpdir, c)
            vms._get_pkl_path = lambda c: os.path.join(tmpdir, c, "index.pkl")

            # 不创建 pkl 文件也能通过（跳过校验）
            vms._verify_index_integrity(coll_name)  # 不抛异常


# ============================================================
#  Collection 存在性检查
# ============================================================

class TestCollectionExists:
    """检查 FAISS collection 是否存在"""

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_exists_when_index_present(self):
        """index.faiss 存在 → True"""
        with tempfile.TemporaryDirectory() as tmpdir:
            vms = VectorStoreManager.__new__(VectorStoreManager)
            vms._settings = MagicMock()
            vms._settings.CHROMA_PERSIST_PATH = tmpdir
            vms._index_dir = tmpdir

            coll_dir = os.path.join(tmpdir, "kb_exists_test")
            os.makedirs(coll_dir, exist_ok=True)
            with open(os.path.join(coll_dir, "index.faiss"), "w") as f:
                f.write("fake index")

            vms._get_coll_dir = lambda c: os.path.join(tmpdir, c)
            assert vms._collection_exists("kb_exists_test") is True

    @patch.object(VectorStoreManager, "__init__", lambda self, s: None)
    def test_not_exists_when_no_index(self):
        """index.faiss 不存在 → False"""
        with tempfile.TemporaryDirectory() as tmpdir:
            vms = VectorStoreManager.__new__(VectorStoreManager)
            vms._settings = MagicMock()
            vms._settings.CHROMA_PERSIST_PATH = tmpdir
            vms._index_dir = tmpdir

            vms._get_coll_dir = lambda c: os.path.join(tmpdir, c)
            assert vms._collection_exists("kb_nonexistent") is False
