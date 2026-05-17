"""模型注册表 — 管理可用模型列表"""

from config import settings
from models.schemas import ModelInfo

# 预定义模型列表
_PREDEFINED_MODELS: list[ModelInfo] = [
    ModelInfo(
        id="deepseek-v4-pro",
        name="DeepSeek V4 Pro",
        description="旗舰模型，支持深度思考模式，适合复杂面试场景",
        supports_thinking=True,
    ),
    ModelInfo(
        id="deepseek-v4-flash",
        name="DeepSeek V4 Flash",
        description="轻量模型，快速响应，支持思考模式，适合简单对话",
        supports_thinking=True,
    ),
]


def get_available_models() -> list[ModelInfo]:
    """返回当前配置启用的模型列表"""
    enabled_ids = {name.strip() for name in settings.AVAILABLE_MODELS.split(",") if name.strip()}
    return [m for m in _PREDEFINED_MODELS if m.id in enabled_ids]


def validate_model(model_id: str) -> bool:
    """校验模型是否在可用列表中"""
    enabled_ids = {name.strip() for name in settings.AVAILABLE_MODELS.split(",") if name.strip()}
    return model_id in enabled_ids
