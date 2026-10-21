"""DeepSeek LLM 客户端 — 流式对话 + 报告生成"""

import logging
from typing import AsyncGenerator, Optional

import openai
from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

# 全局客户端（未传 api_key 时使用，走 .env 的 DEEPSEEK_API_KEY）
_client: Optional[AsyncOpenAI] = None

# 按 api_key 缓存的客户端。
#
# 为什么必须缓存而不是每次 new：每个 AsyncOpenAI 内部都持有一个 httpx 连接池，
# 每次调用都新建就等于每次泄漏一个连接池（既浪费连接，也让 aclose() 无法回收 ——
# 拿不到引用）。缓存后客户端的数量被「不同 key 的个数」限住，且都能在退出时关闭。
#
# 之所以需要按 key 区分：OpenAI SDK 的 key 是绑在 client 上的，没有「按请求传 key」
# 的接口，所以要用不同的 key 就只能是不同的 client。
_keyed_clients: dict[str, AsyncOpenAI] = {}


def get_client(api_key: Optional[str] = None) -> AsyncOpenAI:
    """获取 OpenAI 客户端。

    - 传了 api_key：返回该 key 对应的客户端（按 key 缓存复用，不会每次新建）
    - 没传：返回全局客户端（.env 的 DEEPSEEK_API_KEY）
    """
    global _client
    if api_key:
        cached = _keyed_clients.get(api_key)
        if cached is None:
            cached = AsyncOpenAI(
                api_key=api_key,
                base_url=settings.DEEPSEEK_BASE_URL,
            )
            _keyed_clients[api_key] = cached
        return cached
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    return _client


async def aclose() -> None:
    """关闭全部客户端（由 main.py 的 lifespan 在应用退出时调用）。

    不关的话，底层 httpx 连接池会拖到 GC 阶段才回收，那时事件循环通常
    已经关闭，`loop.call_soon()` 抛 `RuntimeError: Event loop is closed`。
    在测试里这类异常会被 anyio 记到「当时正在跑的那条用例」上，导致
    毫不相干的用例随机失败（CI 上曾表现为 test_position_store 的用例失败）。

    注意要连**按 key 缓存**的那些一起关：用户配置了自己的 API Key 时，
    get_client(api_key) 走的就是那条路径。
    """
    global _client
    clients: list[AsyncOpenAI] = []
    if _client is not None:
        clients.append(_client)
        _client = None
    # 先取出再清空，保证即使 close 抛异常也不会把引用留在字典里
    clients.extend(_keyed_clients.values())
    _keyed_clients.clear()

    for client in clients:
        try:
            await client.close()
        except Exception as exc:  # noqa: BLE001 - 清理失败不应影响退出
            logger.warning("关闭 DeepSeek 客户端失败: %s", exc)


async def stream_chat(
    messages: list[dict],
    model: Optional[str] = None,
    thinking_enabled: Optional[bool] = None,
    reasoning_effort: Optional[str] = None,
    api_key: Optional[str] = None,
    cache_label: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """
    流式调用 DeepSeek，yield 统一格式 dict：
    - {"type": "reasoning", "content": "..."}  思考链
    - {"type": "content", "content": "..."}    最终回答
    - {"type": "done", "content": ""}          结束

    reasoning_effort 支持 low / high / max 三档，非规范值会被归一化。

    cache_label 只用于日志：把「稳定前缀命中情况」和具体是哪一场面试
    （指纹前缀）关联起来，方便排查前缀为什么没命中。
    """
    from services.screen_capture import normalize_effort
    _model = model or settings.DEEPSEEK_MODEL
    _thinking = thinking_enabled if thinking_enabled is not None else settings.DEEPSEEK_THINKING_ENABLED
    # 归一化成 low / high / max（官方规范档位）
    _effort = normalize_effort(reasoning_effort or settings.DEEPSEEK_REASONING_EFFORT)

    # 将 Pydantic models 转为 dict
    msgs = []
    for m in messages:
        if hasattr(m, "model_dump"):
            msgs.append(m.model_dump())
        elif isinstance(m, dict):
            msgs.append(m)
        else:
            msgs.append({"role": getattr(m, "role", "user"), "content": getattr(m, "content", str(m))})

    extra_body = {}
    if _thinking:
        extra_body["thinking"] = {"type": "enabled"}
        extra_body["reasoning_effort"] = _effort
    else:
        # DeepSeek 思考模式默认开启，必须显式传 disabled 才能关闭
        extra_body["thinking"] = {"type": "disabled"}

    try:
        client = get_client(api_key=api_key)
        stream = await client.chat.completions.create(
            model=_model,
            messages=msgs,
            stream=True,
            extra_body=extra_body if extra_body else None,
            # 流式响应默认不带 usage，必须显式要求；这是观测前缀缓存的唯一途径。
            stream_options={"include_usage": True},
        )

        usage = None
        async for chunk in stream:
            # 带 include_usage 时，最后一个 chunk 的 choices 为空、usage 有值
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = chunk_usage

            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta

                # 思考模式的 reasoning_content
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield {"type": "reasoning", "content": reasoning}

                # 正常 content
                content = getattr(delta, "content", None)
                if content:
                    yield {"type": "content", "content": content}

            # 检查是否结束
            if chunk.choices and chunk.choices[0].finish_reason:
                _log_cache_usage(usage, _model, cache_label)
                yield {"type": "done", "content": ""}
                return

        _log_cache_usage(usage, _model, cache_label)
        yield {"type": "done", "content": ""}

    except openai.APIError as e:
        logger.error(f"DeepSeek API error: {e}")
        yield {"type": "error", "content": f"API 调用失败: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error in stream_chat: {e}")
        yield {"type": "error", "content": f"发生错误: {str(e)}"}


def _log_cache_usage(usage, model: str, cache_label: Optional[str]) -> None:
    """记录本次调用的 token 用量，重点是前缀缓存命中量。

    DeepSeek 在 usage 里用 ``prompt_cache_hit_tokens`` / ``prompt_cache_miss_tokens``
    暴露服务端前缀缓存的结果：命中量高说明「prompt + 简历 + JD」这段前缀
    确实被复用了；如果命中量长期为 0，多半是前缀里混进了每轮变化的内容。

    官方文档还提供了等价字段 ``prompt_tokens_details.cached_tokens``，
    这里作为兜底读取（不同版本的响应里字段位置可能不同）。
    """
    if usage is None:
        logger.info("LLM usage unavailable | model=%s | label=%s", model, cache_label or "-")
        return

    def pick(name):
        value = getattr(usage, name, None)
        if value is None:
            details = getattr(usage, "prompt_tokens_details", None)
            if details is not None:
                value = getattr(details, name, None)
        return value if isinstance(value, int) else None

    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    hit = pick("prompt_cache_hit_tokens")
    if hit is None:
        hit = pick("cached_tokens")
    miss = pick("prompt_cache_miss_tokens")

    cache_rate = ""
    if isinstance(hit, int) and isinstance(miss, int) and (hit + miss) > 0:
        cache_rate = f" | cache_hit_rate={(hit / (hit + miss)) * 100:.1f}%"

    logger.info(
        "LLM usage | model=%s | label=%s | prompt=%s (cache_hit=%s, cache_miss=%s)%s | completion=%s",
        model, cache_label or "-", prompt_tokens, hit, miss, cache_rate, completion,
    )


async def generate_report(
    messages: list[dict],
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> str:
    """非流式调用，用于报告生成"""
    _model = model or settings.DEEPSEEK_MODEL

    msgs = []
    for m in messages:
        if hasattr(m, "model_dump"):
            msgs.append(m.model_dump())
        elif isinstance(m, dict):
            msgs.append(m)
        else:
            msgs.append({"role": getattr(m, "role", "user"), "content": getattr(m, "content", str(m))})

    try:
        client = get_client(api_key=api_key)
        response = await client.chat.completions.create(
            model=_model,
            messages=msgs,
            stream=False,
        )
        _log_cache_usage(getattr(response, "usage", None), _model, "report")
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"Report generation error: {e}")
        return f"报告生成失败: {str(e)}"
