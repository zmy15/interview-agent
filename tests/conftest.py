"""pytest 公共 fixtures"""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    """启动应用，并返回带测试用户认证的客户端。"""
    with TestClient(app) as test_client:
        credentials = {
            "email": "pytest@example.com",
            "password": "pytest-password",
            "display_name": "Pytest User",
        }

        auth_response = test_client.post(
            "/auth/register",
            json=credentials,
        )

        if auth_response.status_code == 409:
            auth_response = test_client.post(
                "/auth/login",
                json={
                    "email": credentials["email"],
                    "password": credentials["password"],
                },
            )

        assert auth_response.status_code in {
            200,
            201,
        }, auth_response.text

        access_token = auth_response.json()["access_token"]

        test_client.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
            }
        )

        yield test_client


@pytest.fixture
def sample_position():
    """测试用岗位数据"""
    return {
        "name": "测试工程师",
        "description": "一个测试岗位",
    }


@pytest.fixture
def sample_jd():
    """测试用 JD 数据"""
    return {
        "content": "## 岗位要求\n\n1. 熟悉 Python\n2. 了解 FastAPI\n3. 有测试经验",
    }


@pytest.fixture
def sample_chat_request():
    """测试用聊天请求"""
    return {
        "messages": [{"role": "user", "content": "你好，请介绍一下自己"}],
        "mode": "interviewer",
    }
