"""岗位管理接口测试"""

import pytest


class TestPositionCRUD:
    """岗位 CRUD 测试"""

    def test_create_position(self, client, sample_position):
        """创建岗位"""
        response = client.post("/positions", json=sample_position)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_position["name"]
        assert data["description"] == sample_position["description"]

        # 清理
        client.delete(f"/positions/{sample_position['name']}")

    def test_create_duplicate(self, client, sample_position):
        """创建重名岗位"""
        client.post("/positions", json=sample_position)
        response = client.post("/positions", json=sample_position)
        assert response.status_code == 409

        # 清理
        client.delete(f"/positions/{sample_position['name']}")

    def test_list_positions(self, client, sample_position):
        """列出岗位"""
        client.post("/positions", json=sample_position)
        response = client.get("/positions")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        names = [p["name"] for p in data["positions"]]
        assert sample_position["name"] in names

        # 清理
        client.delete(f"/positions/{sample_position['name']}")

    def test_get_position(self, client, sample_position):
        """获取单个岗位"""
        client.post("/positions", json=sample_position)
        response = client.get(f"/positions/{sample_position['name']}")
        assert response.status_code == 200
        assert response.json()["name"] == sample_position["name"]

        # 清理
        client.delete(f"/positions/{sample_position['name']}")

    def test_get_nonexistent(self, client):
        """获取不存在的岗位"""
        response = client.get("/positions/nonexistent_test_12345")
        assert response.status_code == 404

    def test_update_position(self, client, sample_position):
        """更新岗位"""
        client.post("/positions", json=sample_position)
        response = client.put(
            f"/positions/{sample_position['name']}",
            json={"description": "更新后的描述"},
        )
        assert response.status_code == 200
        assert response.json()["description"] == "更新后的描述"

        # 清理
        client.delete(f"/positions/{sample_position['name']}")

    def test_delete_position(self, client, sample_position):
        """删除岗位"""
        client.post("/positions", json=sample_position)
        response = client.delete(f"/positions/{sample_position['name']}")
        assert response.status_code == 200
        # 确认已删除
        response = client.get(f"/positions/{sample_position['name']}")
        assert response.status_code == 404


class TestJDManagement:
    """JD 管理测试"""

    @pytest.fixture(autouse=True)
    def setup_position(self, client, sample_position):
        """每个测试前创建岗位"""
        client.post("/positions", json=sample_position)
        yield
        client.delete(f"/positions/{sample_position['name']}")

    def test_add_jd(self, client, sample_position, sample_jd):
        """添加 JD"""
        response = client.post(
            f"/positions/{sample_position['name']}/jds",
            json=sample_jd,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["content"] == sample_jd["content"]
        assert "id" in data

    def test_remove_jd(self, client, sample_position, sample_jd):
        """删除 JD"""
        # 先添加
        add_resp = client.post(
            f"/positions/{sample_position['name']}/jds",
            json=sample_jd,
        )
        jd_id = add_resp.json()["id"]

        # 删除
        response = client.delete(f"/positions/{sample_position['name']}/jds/{jd_id}")
        assert response.status_code == 200

        # 确认已删除
        pos = client.get(f"/positions/{sample_position['name']}")
        jd_ids = [j["id"] for j in pos.json()["jds"]]
        assert jd_id not in jd_ids

    def test_update_jd(self, client, sample_position, sample_jd):
        """修改 JD"""
        add_resp = client.post(
            f"/positions/{sample_position['name']}/jds",
            json=sample_jd,
        )
        jd_id = add_resp.json()["id"]

        response = client.put(
            f"/positions/{sample_position['name']}/jds/{jd_id}",
            json={"content": "修改后的 JD"},
        )
        assert response.status_code == 200
        assert response.json()["content"] == "修改后的 JD"
