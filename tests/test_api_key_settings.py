"""用户 API Key 加密存储的接口测试"""

import pytest
from sqlalchemy import select

from database import async_session_factory
from models.db_models import UserApiKey
from services import crypto


class TestApiKeyEndpoints:
    """PUT / GET / DELETE /settings/api-key"""

    def test_initially_not_configured(self, client):
        """新用户默认未配置"""
        resp = client.get("/settings/api-key")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["configured"] is False
        assert body["hint"] == ""

    def test_save_then_status_shows_hint(self, client):
        """保存后状态变为已配置，且只返回掩码"""
        key = "sk-6680b1234567890abcdefghijklmnopd69d"
        resp = client.put("/settings/api-key", json={"api_key": key})
        assert resp.status_code == 200, resp.text
        assert resp.json()["configured"] is True
        assert resp.json()["hint"] == "sk-668…d69d"

        status = client.get("/settings/api-key").json()
        assert status["configured"] is True
        assert status["hint"] == "sk-668…d69d"

    def test_response_never_leaks_plaintext(self, client):
        """任何响应体都不能出现明文密钥"""
        key = "sk-6680b1234567890abcdefghijklmnopd69d"
        save_resp = client.put("/settings/api-key", json={"api_key": key})
        status_resp = client.get("/settings/api-key")

        for resp in (save_resp, status_resp):
            assert key not in resp.text
            assert "b1234567890abcdefghijklmnop" not in resp.text

    def test_save_overwrites_existing(self, client):
        """重复保存是覆盖而不是新增"""
        client.put("/settings/api-key", json={"api_key": "sk-first-aaaaaaaaaaaa-1111"})
        client.put("/settings/api-key", json={"api_key": "sk-second-bbbbbbbbbbbb-2222"})

        status = client.get("/settings/api-key").json()
        assert status["hint"] == "sk-sec…2222"

    def test_delete_clears_key(self, client):
        """DELETE 之后回到未配置状态"""
        client.put("/settings/api-key", json={"api_key": "sk-to-be-removed-9999"})
        assert client.get("/settings/api-key").json()["configured"] is True

        resp = client.delete("/settings/api-key")
        assert resp.status_code == 200, resp.text
        assert resp.json()["configured"] is False
        assert client.get("/settings/api-key").json()["configured"] is False

    def test_delete_when_absent_is_idempotent(self, client):
        """未配置时删除不应报错"""
        resp = client.delete("/settings/api-key")
        assert resp.status_code == 200, resp.text
        assert resp.json()["configured"] is False

    def test_empty_key_rejected(self, client):
        """空字符串被拒绝（校验层拦截）"""
        resp = client.put("/settings/api-key", json={"api_key": ""})
        assert resp.status_code == 422

    def test_whitespace_only_key_rejected(self, client):
        """纯空白也被拒绝（服务层 strip 后为空）"""
        resp = client.put("/settings/api-key", json={"api_key": "    "})
        assert resp.status_code == 400

    def test_requires_auth(self, client):
        """未带令牌时不可访问（client fixture 默认带了认证头）"""
        resp = client.get("/settings/api-key", headers={"Authorization": ""})
        assert resp.status_code in {401, 403}


class TestApiKeyIsolation:
    """不同用户之间的密钥互相隔离"""

    def test_user_b_cannot_see_user_a_key(self, client, user_b_headers):
        client.put("/settings/api-key", json={"api_key": "sk-user-a-key-aaaa-1111"})

        resp = client.get("/settings/api-key", headers=user_b_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["configured"] is False

    def test_user_b_save_does_not_clobber_user_a(self, client, user_b_headers):
        client.put("/settings/api-key", json={"api_key": "sk-user-a-key-aaaa-1111"})
        client.put(
            "/settings/api-key",
            json={"api_key": "sk-user-b-key-bbbb-2222"},
            headers=user_b_headers,
        )

        assert client.get("/settings/api-key").json()["hint"] == "sk-use…1111"
        assert (
            client.get("/settings/api-key", headers=user_b_headers).json()["hint"]
            == "sk-use…2222"
        )


class TestStoredKeyIsEncrypted:
    """落库内容必须是密文，且能被服务端解回明文"""

    @pytest.mark.anyio
    async def test_db_row_holds_ciphertext(self, client):
        key = "sk-6680b1234567890abcdefghijklmnopd69d"
        client.put("/settings/api-key", json={"api_key": key})
        user_id = client.get("/auth/me").json()["id"]

        async with async_session_factory() as db:
            result = await db.execute(
                select(UserApiKey).where(UserApiKey.user_id == user_id)
            )
            row = result.scalar_one()

        # 库里不能是明文
        assert row.encrypted_key != key
        assert key not in row.encrypted_key
        # 但必须能解回来（否则服务端没法真正调用 LLM）
        assert crypto.decrypt(row.encrypted_key) == key
        # 掩码字段不含完整密钥
        assert row.key_hint == "sk-668…d69d"
