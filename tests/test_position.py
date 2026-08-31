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


class TestUserIsolation:
    """多用户数据隔离测试 — 同名岗位按用户隔离"""

    NAME = "隔离测试岗"

    def test_same_name_across_users(self, client, user_b_headers):
        """两个用户各自创建同名岗位，互不可见、互不可改、互不可删"""
        # 用户 A 创建
        resp = client.post("/positions", json={"name": self.NAME, "description": "A的岗位"})
        assert resp.status_code == 201, resp.text

        # 用户 B 可以创建同名岗位
        resp = client.post(
            "/positions",
            json={"name": self.NAME, "description": "B的岗位"},
            headers=user_b_headers,
        )
        assert resp.status_code == 201, resp.text

        # 各自只能看到自己的
        resp = client.get(f"/positions/{self.NAME}")
        assert resp.status_code == 200
        assert resp.json()["description"] == "A的岗位"

        resp = client.get(f"/positions/{self.NAME}", headers=user_b_headers)
        assert resp.status_code == 200
        assert resp.json()["description"] == "B的岗位"

        # 用户 A 改自己的，不影响 B
        resp = client.put(
            f"/positions/{self.NAME}",
            json={"description": "A改后的岗位"},
        )
        assert resp.status_code == 200
        resp = client.get(f"/positions/{self.NAME}", headers=user_b_headers)
        assert resp.json()["description"] == "B的岗位"

        # JD 也按用户隔离：A 添加的 JD，B 看不到
        resp = client.post(
            f"/positions/{self.NAME}/jds",
            json={"content": "A的 JD 内容"},
        )
        assert resp.status_code == 201
        resp = client.get(f"/positions/{self.NAME}", headers=user_b_headers)
        assert resp.json()["jds"] == []

        # 用户 A 删除自己的，B 的不受影响
        resp = client.delete(f"/positions/{self.NAME}")
        assert resp.status_code == 200
        resp = client.get(f"/positions/{self.NAME}", headers=user_b_headers)
        assert resp.status_code == 200
        assert resp.json()["description"] == "B的岗位"

        # A 删除后，B 仍存在，再删 B 的
        resp = client.delete(f"/positions/{self.NAME}", headers=user_b_headers)
        assert resp.status_code == 200

    def test_cannot_touch_others_position(self, client, user_b_headers):
        """用户无法获取/修改/删除其他用户的岗位"""
        # 用户 B 创建岗位
        resp = client.post(
            "/positions",
            json={"name": self.NAME, "description": "B的岗位"},
            headers=user_b_headers,
        )
        assert resp.status_code == 201

        # 用户 A（默认 client）访问同名岗位 → 404（视角里不存在）
        assert client.get(f"/positions/{self.NAME}").status_code == 404

        resp = client.put(
            f"/positions/{self.NAME}",
            json={"description": "A想改B的"},
        )
        assert resp.status_code == 404

        resp = client.delete(f"/positions/{self.NAME}")
        assert resp.status_code == 404

        # 用户 A 给"不存在"（实际是 B 的）岗位加 JD → 404
        resp = client.post(
            f"/positions/{self.NAME}/jds",
            json={"content": "A想给B的岗位加JD"},
        )
        assert resp.status_code == 404

        # 清理：B 删除自己的岗位
        resp = client.delete(f"/positions/{self.NAME}", headers=user_b_headers)
        assert resp.status_code == 200
