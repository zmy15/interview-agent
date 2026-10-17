"""用户 API Key 的落库与取用 —— 加密存储，只暴露掩码

调用方约定
----------
* 写入：``save_key()`` 接收明文，内部加密后入库，返回掩码提示；
* 取用：``get_stored_key()`` 返回**明文**，仅供服务端调用 LLM 时使用，
  绝不可直接返回给前端；
* 展示：``get_status()`` 只返回 ``{configured, hint}``，不含明文。
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.db_models import UserApiKey
from services import crypto
from utils.auth import CurrentUser

logger = logging.getLogger(__name__)

# 目前只接 DeepSeek；字段留着是为了将来接入其他厂商时不用改表结构
PROVIDER_DEEPSEEK = "deepseek"


async def _fetch_row(
    db: AsyncSession, user_id: str, provider: str
) -> Optional[UserApiKey]:
    """取出某个用户 + 某个服务商的密钥记录（没有则 None）"""
    result = await db.execute(
        select(UserApiKey).where(
            UserApiKey.user_id == user_id,
            UserApiKey.provider == provider,
        )
    )
    return result.scalar_one_or_none()


async def get_status(
    db: AsyncSession, user_id: str, provider: str = PROVIDER_DEEPSEEK
) -> dict:
    """前端要的配置状态：是否已配置 + 掩码提示（不含明文）"""
    row = await _fetch_row(db, user_id, provider)
    if row is None:
        return {"configured": False, "hint": ""}
    return {"configured": True, "hint": row.key_hint or ""}


async def get_stored_key(
    db: AsyncSession, user_id: str, provider: str = PROVIDER_DEEPSEEK
) -> Optional[str]:
    """取出明文密钥供服务端调用 LLM；未配置或解密失败返回 None

    解密失败（例如 APP_ENCRYPTION_KEY 被换过）时返回 None，
    让调用方自然回退到 .env 的默认配置，而不是整个请求 500。
    """
    row = await _fetch_row(db, user_id, provider)
    if row is None:
        return None
    return crypto.decrypt(row.encrypted_key)


async def save_key(
    db: AsyncSession,
    user_id: str,
    plaintext: str,
    provider: str = PROVIDER_DEEPSEEK,
) -> str:
    """保存（已存在则覆盖）密钥，返回掩码提示

    注意：这里只 flush 不 commit，事务由 ``get_db`` 依赖在请求结束时提交。
    并发首次保存同一用户是极端罕见场景（界面单人操作），未额外加锁。
    """
    plaintext = (plaintext or "").strip()
    if not plaintext:
        raise ValueError("API Key 不能为空")

    encrypted = crypto.encrypt(plaintext)
    hint = crypto.mask(plaintext)

    row = await _fetch_row(db, user_id, provider)
    if row is None:
        row = UserApiKey(
            user_id=user_id,
            provider=provider,
            encrypted_key=encrypted,
            key_hint=hint,
        )
        db.add(row)
    else:
        row.encrypted_key = encrypted
        row.key_hint = hint

    await db.flush()
    logger.info("已保存用户 API Key（user=%s, hint=%s）", user_id, hint)
    return hint


async def clear_key(
    db: AsyncSession, user_id: str, provider: str = PROVIDER_DEEPSEEK
) -> bool:
    """清除密钥；返回是否确实删掉了记录"""
    row = await _fetch_row(db, user_id, provider)
    if row is None:
        return False
    await db.delete(row)
    await db.flush()
    logger.info("已清除用户 API Key（user=%s）", user_id)
    return True


# ══════════════════════════════════════════════════════════════
# 请求级解析：本次调用到底该用哪把 Key
# ══════════════════════════════════════════════════════════════


def effective_api_key_from_request(
    request: Request, explicit: Optional[str] = None
) -> Optional[str]:
    """从请求本身取出 Key：显式参数 > 专用请求头

    保留这条路径是因为「按用户自己的 Key 拉模型列表」等行为仍然依赖它；
    前端目前会自动带上 ``X-DEEPSEEK-API-KEY``。
    """
    for candidate in (
        explicit,
        request.headers.get("X-DEEPSEEK-API-KEY"),
        request.headers.get("X-DeepSeek-Key"),
    ):
        if candidate and candidate.strip():
            return candidate.strip()
    return None


async def resolve_api_key(
    request: Request,
    db: AsyncSession,
    user: Optional[CurrentUser],
    explicit: Optional[str] = None,
) -> Optional[str]:
    """决定本次 LLM 调用使用哪把 API Key。

    优先级：
        1. 请求显式传入（参数 / 请求头）
        2. 数据库里加密保存的 Key（本模块负责）
        3. 返回 None，由 llm_client 兜底到 .env 的 DEEPSEEK_API_KEY

    第 2 层是本次新增的核心：桌面版 native 窗口是 pywebview，
    ``private_mode`` 默认 True，localStorage 每次重启都会被清空，
    表现为「配过 API Key，重启就没了」。改存数据库后不再依赖浏览器存储，
    同时也摆脱了 localStorage 按「协议+域名+端口」隔离的限制。

    刻意把请求头放在数据库**之前**：既有的「用自己 Key 拉模型列表」
    行为不受影响，只有前端确实没带 Key 时才回落到用户先前存下的那一把。
    """
    from_request = effective_api_key_from_request(request, explicit=explicit)
    if from_request:
        return from_request
    if user is None:
        return None
    return await get_stored_key(db, user.id)
