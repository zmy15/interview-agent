"""用户设置路由 —— 目前承载 API Key 的加密存储

背景
----
API Key 原先只存在浏览器 localStorage 里，桌面版 native 窗口
（pywebview，``private_mode`` 默认 True）一重启就清空，表现为
「配置过，重启就没了」。

这里把密钥改为加密存进数据库，前端启动时拉取状态、保存时提交明文
（HTTPS / 本机回环传输），读取接口只返回掩码。
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.schemas import (
    ApiKeySaveRequest,
    ApiKeySaveResponse,
    ApiKeyStatusResponse,
)
from services import api_key_store
from utils.auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/api-key", response_model=ApiKeyStatusResponse)
async def get_api_key_status(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询当前用户是否已配置 API Key（只返回掩码，不返回明文）"""
    status = await api_key_store.get_status(db, user.id)
    return ApiKeyStatusResponse(**status)


@router.put("/api-key", response_model=ApiKeySaveResponse)
async def save_api_key(
    payload: ApiKeySaveRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """保存（覆盖）当前用户的 API Key，加密后入库"""
    hint = await api_key_store.save_key(db, user.id, payload.api_key)
    return ApiKeySaveResponse(configured=True, hint=hint)


@router.delete("/api-key", response_model=ApiKeyStatusResponse)
async def clear_api_key(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清除当前用户的 API Key，之后回退到服务端 .env 配置"""
    await api_key_store.clear_key(db, user.id)
    return ApiKeyStatusResponse(configured=False, hint="")
