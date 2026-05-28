"""联网搜索工具单元测试"""

from unittest.mock import MagicMock, patch

from services.agent_tools import _get_ddgs, search_web


# ============================================================
#  _get_ddgs — DuckDuckGo 实例获取
# ============================================================

class TestGetDDGS:
    """DuckDuckGo 搜索实例懒加载"""

    def test_creates_instance_when_not_exists(self):
        """首次调用创建实例"""
        # 强制重置全局单例
        import services.agent_tools as at
        at._search_instance = None

        with patch("duckduckgo_search.DDGS") as mock_ddgs:
            mock_ddgs.return_value = MagicMock()
            result = _get_ddgs()
            assert result is not None
            mock_ddgs.assert_called_once()

    def test_reuses_existing_instance(self):
        """已有实例时直接复用"""
        import services.agent_tools as at
        fake = MagicMock()
        at._search_instance = fake

        with patch("duckduckgo_search.DDGS") as mock_ddgs:
            result = _get_ddgs()
            assert result is fake
            mock_ddgs.assert_not_called()

        at._search_instance = None  # 恢复

    def test_returns_none_on_import_error(self):
        """duckduckgo_search 未安装 → None"""
        import services.agent_tools as at
        at._search_instance = None

        with patch("duckduckgo_search.DDGS", side_effect=ImportError("not installed")):
            result = _get_ddgs()
            assert result is None


# ============================================================
#  search_web — 网页搜索
# ============================================================

class TestSearchWeb:
    """DuckDuckGo 网页搜索"""

    def test_ddgs_not_available(self):
        """DDGS 不可用 → None"""
        import services.agent_tools as at
        at._search_instance = None

        with patch("duckduckgo_search.DDGS", side_effect=ImportError):
            result = search_web("Python")
            assert result is None

    def test_no_results(self):
        """无搜索结果 → None"""
        ddgs = MagicMock()
        ddgs.text.return_value = iter([])  # 空迭代器

        import services.agent_tools as at
        at._search_instance = ddgs

        result = search_web("xyz不存在的查询")
        assert result is None

        at._search_instance = None

    def test_returns_formatted_results(self):
        """正常搜索返回格式化字符串"""
        ddgs = MagicMock()
        ddgs.text.return_value = iter([
            {"title": "Python 官网", "href": "https://python.org", "body": "Python 编程语言"},
            {"title": "FastAPI 文档", "href": "https://fastapi.tiangolo.com", "body": "现代 Web 框架"},
        ])

        import services.agent_tools as at
        at._search_instance = ddgs

        result = search_web("Python FastAPI")
        assert result is not None
        assert "[1]" in result
        assert "[2]" in result
        assert "Python 官网" in result
        assert "FastAPI 文档" in result
        assert "https://python.org" in result
        assert "https://fastapi.tiangolo.com" in result

        at._search_instance = None

    def test_result_missing_fields(self):
        """搜索结果缺少字段 → 使用默认值"""
        ddgs = MagicMock()
        ddgs.text.return_value = iter([{}])  # 空 dict

        import services.agent_tools as at
        at._search_instance = ddgs

        result = search_web("test")
        assert result is not None
        assert "无标题" in result
        assert "来源: " in result

        at._search_instance = None

    def test_search_exception_handled(self):
        """搜索抛异常 → 返回 None（不崩溃）"""
        ddgs = MagicMock()
        ddgs.text.side_effect = RuntimeError("网络错误")

        import services.agent_tools as at
        at._search_instance = ddgs

        result = search_web("Python")
        assert result is None

        at._search_instance = None

    def test_custom_max_results(self):
        """自定义 max_results 参数"""
        ddgs = MagicMock()
        ddgs.text.return_value = iter([
            {"title": "标题", "href": "", "body": "内容"},
        ])

        import services.agent_tools as at
        at._search_instance = ddgs

        search_web("test", max_results=10)
        ddgs.text.assert_called_once_with("test", max_results=10)

        at._search_instance = None
