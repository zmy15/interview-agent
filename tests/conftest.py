"""pytest 公共 fixtures"""

import os
import tempfile

# 测试专用数据库：必须在导入 main（间接导入 database.py）之前设置，
# 否则 API 测试会直接读写开发库 data/interview_platform.db。
# load_dotenv() 默认不覆盖已存在的环境变量，因此此处设置优先生效。
_TEST_DB_DIR = tempfile.mkdtemp(prefix="interview-agent-tests-")
os.environ["DATABASE_URL"] = (
    "sqlite+aiosqlite:///" + os.path.join(_TEST_DB_DIR, "test_platform.db").replace("\\", "/")
)

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
def user_b_headers(client):
    """第二个测试用户的认证头（与 client 默认用户不同，用于多用户隔离测试）"""
    credentials = {
        "email": "pytest-b@example.com",
        "password": "pytest-password-b",
        "display_name": "Pytest User B",
    }

    auth_response = client.post(
        "/auth/register",
        json=credentials,
    )
    if auth_response.status_code == 409:
        auth_response = client.post(
            "/auth/login",
            json={
                "email": credentials["email"],
                "password": credentials["password"],
            },
        )

    assert auth_response.status_code in {200, 201}, auth_response.text
    return {"Authorization": f"Bearer {auth_response.json()['access_token']}"}


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
