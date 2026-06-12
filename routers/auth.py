"""
认证路由 — 注册 / 登录 / 刷新令牌 / 个人信息
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db_models import User
from utils.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    CurrentUser,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


# ============ 请求/响应模型 ============

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str = Field("用户", max_length=50)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    id: str
    email: str
    display_name: str
    avatar_url: Optional[str] = None
    role: str
    created_at: str


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = Field(None, max_length=50)
    avatar_url: Optional[str] = Field(None, max_length=500)


# ============ 端点 ============

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """用户注册"""
    # 检查邮箱是否已注册
    result = await db.execute(select(User).where(User.email == req.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该邮箱已被注册",
        )

    # 创建用户
    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        display_name=req.display_name,
    )
    db.add(user)
    await db.flush()  # 获取 user.id

    # 生成令牌
    access_token = create_access_token(user.id, user.email, user.role)
    refresh_token = create_refresh_token(user.id)

    logger.info(f"New user registered: {user.email} (id={user.id})")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录"""
    # 查找用户
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用，请联系管理员",
        )

    # 生成令牌
    access_token = create_access_token(user.id, user.email, user.role)
    refresh_token = create_refresh_token(user.id)

    logger.info(f"User logged in: {user.email}")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """使用刷新令牌获取新的访问令牌"""
    payload = decode_token(req.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="刷新令牌无效或已过期",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    # 签发新令牌
    access_token = create_access_token(user.id, user.email, user.role)
    new_refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        user={
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
    )


@router.get("/me", response_model=UserProfile)
async def get_me(user: CurrentUser = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取当前登录用户信息"""
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one_or_none()

    if db_user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    return UserProfile(
        id=db_user.id,
        email=db_user.email,
        display_name=db_user.display_name,
        avatar_url=db_user.avatar_url,
        role=db_user.role,
        created_at=db_user.created_at.isoformat() if db_user.created_at else "",
    )


@router.put("/me", response_model=UserProfile)
async def update_profile(
    req: UpdateProfileRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新个人信息"""
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one_or_none()

    if db_user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    if req.display_name is not None:
        db_user.display_name = req.display_name
    if req.avatar_url is not None:
        db_user.avatar_url = req.avatar_url

    await db.flush()

    return UserProfile(
        id=db_user.id,
        email=db_user.email,
        display_name=db_user.display_name,
        avatar_url=db_user.avatar_url,
        role=db_user.role,
        created_at=db_user.created_at.isoformat() if db_user.created_at else "",
    )
