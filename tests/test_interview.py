"""面试接口测试"""

import pytest


class TestInterviewStart:
    """POST /interview/start"""

    @pytest.fixture(autouse=True)
    def setup_position(self, client):
        """创建测试岗位"""
        client.post("/positions", json={"name": "面试测试岗", "description": "测试"})
        client.post(
            "/positions/面试测试岗/jds",
            json={"content": "需要 Python 和 FastAPI 经验"},
        )
        yield
        client.delete("/positions/面试测试岗")

    def test_start_with_position(self, client):
        """带岗位名称开始面试"""
        response = client.post(
            "/interview/start",
            json={
                "mode": "interviewer",
                "position_name": "面试测试岗",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "system"
        assert "Python" in data["content"] or "FastAPI" in data["content"]

    def test_start_without_position(self, client):
        """不带岗位开始面试"""
        response = client.post(
            "/interview/start",
            json={"mode": "candidate"},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "system"

    def test_start_invalid_mode(self, client):
        """无效模式"""
        response = client.post(
            "/interview/start",
            json={"mode": "invalid_mode"},
        )
        assert response.status_code == 400

    def test_start_nonexistent_position(self, client):
        """不存在的岗位"""
        response = client.post(
            "/interview/start",
            json={"mode": "interviewer", "position_name": "不存在岗位12345"},
        )
        assert response.status_code == 404


class TestInterviewStop:
    """POST /interview/stop"""

    def test_stop(self, client):
        """停止面试"""
        response = client.post("/interview/stop")
        assert response.status_code == 200
        assert "结束" in response.json()["message"]


class TestInterviewReport:
    """POST /interview/report"""

    def test_generate_report(self, client):
        """生成面试报告"""
        response = client.post(
            "/interview/report",
            json={
                "messages": [
                    {"role": "system", "content": "你是面试官，考察 Python 知识"},
                    {"role": "user", "content": "请解释什么是装饰器？"},
                    {"role": "assistant", "content": "装饰器是..."},
                ],
                "mode": "interviewer",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "report" in data
        assert len(data["report"]) > 0
