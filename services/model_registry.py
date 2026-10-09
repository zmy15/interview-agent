"""模型注册表 — 动态从 DeepSeek /models 接口获取可用模型

不再把模型名硬编码在代码里（旧实现维护一份 _PREDEFINED_MODELS 常量，
官方每新增/改名一个模型就要改一次代码）。

数据来源：GET {DEEPSEEK_BASE_URL}/models
    https://api-docs.deepseek.com/zh-cn/api/list-models

官方返回的模型元数据：
    id                模型标识符
    name              展示名称（供模型选择器使用）
    context_window    上下文窗口 token 总容量
    max_output_tokens 单次响应输出 token 上限
    input_modalities  输入模态，取值 text / image
    output_modalities 输出模态
    effort.supported_levels / effort.default_level  思考模式的推理强度档位

其中 input_modalities 含 "image" 即代表该模型支持图片输入 ——
截图识别据此判断，而不是靠猜模型名。

缓存：结果在进程内缓存 TTL 秒（默认 300），避免每次请求都打一次远端；
      远端不可用（未配置 Key 等）时回退到 .env 的 AVAILABLE_MODELS 配置，
      保证纯本地开发也能正常列出模型。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from config import settings
from models.schemas import ModelInfo

logger = logging.getLogger(__name__)

# 远端模型列表缓存有效期（秒）
_CACHE_TTL = 300

# 进程内缓存： (过期时间戳, [ModelInfo])
_cache: tuple[float, list[ModelInfo]] | None = None
_cache_lock = threading.Lock()

# 未配置 API Key 时优先使用的兜底模型名（保持与历史默认行为一致）
_FALLBACK_DEFAULT = "deepseek-v4-pro"


# ══════════════════════════════════════════════════════════════
# 远端元数据 → ModelInfo
# ══════════════════════════════════════════════════════════════


def _modalities(raw: object) -> list[str]:
    """把 input_modalities / output_modalities 统一成小写字符串列表"""
    if isinstance(raw, str):
        return [raw.lower()]
    if isinstance(raw, (list, tuple)):
        return [str(m).lower() for m in raw]
    return []


def _effort_levels(model: object) -> list[str]:
    """读取 effort.supported_levels（官方元数据里是嵌套对象）"""
    effort = getattr(model, "effort", None)
    if effort is None and isinstance(model, dict):
        effort = model.get("effort")
    if effort is None:
        return []
    levels = getattr(effort, "supported_levels", None)
    if levels is None and isinstance(effort, dict):
        levels = effort.get("supported_levels")
    if isinstance(levels, str):
        return [levels]
    if isinstance(levels, (list, tuple)):
        return [str(l) for l in levels]
    return []


def _supports_thinking(model: object) -> bool:
    """模型是否支持思考模式。

    优先依据官方元数据的 effort.supported_levels；字段缺失时保守认为支持
    （思考开关由请求体的 thinking 参数控制，传了也不会报错）。
    """
    levels = _effort_levels(model)
    if levels:
        return True
    return getattr(model, "effort", None) is None


def model_info_from_api(model: object) -> ModelInfo:
    """把官方 /models 返回的一个模型对象转换成 ModelInfo"""
    get = (lambda k, d=None: model.get(k, d)) if isinstance(model, dict) else (
        lambda k, d=None: getattr(model, k, d)
    )

    model_id = str(get("id") or "").strip()
    display = (get("name") or "").strip() or model_id

    inputs = _modalities(get("input_modalities"))
    supports_vision = "image" in inputs

    # 描述用官方元数据拼出来，让界面能直接看出这个模型能干什么
    bits: list[str] = []
    if inputs:
        bits.append("输入：" + "/".join(inputs))
    ctx = get("context_window")
    if isinstance(ctx, int) and ctx > 0:
        bits.append(f"上下文 {ctx // 1000}K tokens" if ctx >= 1000 else f"上下文 {ctx} tokens")
    max_out = get("max_output_tokens")
    if isinstance(max_out, int) and max_out > 0:
        bits.append(f"输出上限 {max_out}")
    if supports_vision:
        bits.append("支持图片")
    if _supports_thinking(model):
        levels = _effort_levels(model)
        bits.append("支持思考" + (f"（{'/'.join(levels)}）" if levels else ""))
    description = " · ".join(bits)

    return ModelInfo(
        id=model_id,
        name=display,
        description=description,
        supports_thinking=_supports_thinking(model),
        supports_vision=supports_vision,
    )


# ══════════════════════════════════════════════════════════════
# 远端拉取
# ══════════════════════════════════════════════════════════════


async def fetch_remote_models(api_key: Optional[str] = None) -> list[ModelInfo]:
    """调用官方 GET /models，返回模型列表。

    失败（网络不可达 / Key 无效等）时抛异常，由调用方决定兜底策略。
    """
    from services.llm_client import get_client

    client = get_client(api_key=api_key)
    resp = await client.models.list()
    raw_models = getattr(resp, "data", None) or []

    models: list[ModelInfo] = []
    seen: set[str] = set()
    for item in raw_models:
        info = model_info_from_api(item)
        if not info.id or info.id in seen:
            continue
        seen.add(info.id)
        models.append(info)
    return models


def _fallback_models() -> list[ModelInfo]:
    """远端不可用时的兜底：使用 .env 中配置的 AVAILABLE_MODELS。

    注意这里**没有**内嵌模型元数据，视觉能力标记为未知（False），
    真实判断仍以远端元数据为准；界面会提示模型列表来自本地配置。
    """
    ids = [name.strip() for name in settings.AVAILABLE_MODELS.split(",") if name.strip()]
    return [
        ModelInfo(
            id=mid,
            name=mid,
            description="本地配置模型（远端模型列表暂不可用）",
            supports_thinking=True,
            supports_vision=False,
        )
        for mid in ids
    ]


async def get_available_models(api_key: Optional[str] = None, *, force: bool = False) -> list[ModelInfo]:
    """返回可用模型列表（优先远端，失败回退 .env 配置）。

    结果按 api_key 维度做进程内缓存，TTL 内不重复请求远端。
    """
    global _cache

    now = time.monotonic()
    if not api_key and not force:
        with _cache_lock:
            if _cache and _cache[0] > now:
                return _cache[1]

    try:
        models = await fetch_remote_models(api_key=api_key)
    except Exception as exc:
        logger.warning("获取远端模型列表失败，回退到 AVAILABLE_MODELS 配置: %s", exc)
        # 兜底结果同样缓存一段时间，避免远端持续不可用时每次请求都超时
        fallback = _fallback_models()
        with _cache_lock:
            _cache = (now + _CACHE_TTL, fallback)
        return fallback

    if not models:
        return _fallback_models()

    with _cache_lock:
        _cache = (now + _CACHE_TTL, models)
    return models


def invalidate_cache() -> None:
    """清空模型列表缓存（API Key 变更 / 手动刷新时调用）"""
    global _cache
    with _cache_lock:
        _cache = None


async def get_vision_models(api_key: Optional[str] = None) -> list[ModelInfo]:
    """支持图片输入的模型（input_modalities 含 image）"""
    return [m for m in await get_available_models(api_key=api_key) if m.supports_vision]


async def supports_vision(model_id: str, api_key: Optional[str] = None) -> bool:
    """判断指定模型是否支持图片输入。

    远端列表拿不到时返回 False（未知），由调用方给出「无法确认」的提示。
    """
    if not model_id:
        return False
    for m in await get_available_models(api_key=api_key):
        if m.id == model_id:
            return m.supports_vision
    return False


async def resolve_vision_model(api_key: Optional[str] = None) -> Optional[str]:
    """挑一个账号下可用的视觉模型，没有则返回 None。

    仅作为「界面未选择模型」时的默认值；用户显式选择的模型不会被替换。
    """
    preferred = (settings.SCREENSHOT_VISION_MODEL or "").strip()
    models = await get_available_models(api_key=api_key)
    vision = [m for m in models if m.supports_vision]

    if preferred:
        for m in vision:
            if m.id == preferred:
                return m.id
    return vision[0].id if vision else None


async def validate_model(model_id: str, api_key: Optional[str] = None) -> bool:
    """校验模型是否在可用列表中。

    远端列表不可用时（回退到本地配置）只要配置里出现过就放行，
    避免网络抖动把用户挡在门外。
    """
    if not model_id:
        return False
    return any(m.id == model_id for m in await get_available_models(api_key=api_key))