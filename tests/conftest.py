"""pytest 公共 fixtures"""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    """FastAPI 同步测试客户端"""
    return TestClient(app)


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
        "messages": [
            {"role": "user", "content": "你好，请介绍一下自己"}
        ],
        "mode": "interviewer",
    }
