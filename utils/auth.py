"""
认证工具 — JWT 令牌 + 密码哈希 + 认证依赖注入
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db

# ── 密码哈希上下文 ──
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── JWT 配置 ──
JWT_SECRET = settings.JWT_SECRET
JWT_ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS

# ── Bearer Token 提取器 ──
bearer_scheme = HTTPBearer(auto_error=False)


# ============ 密码工具 ============

def hash_password(password: str) -> str:
    """对密码进行 bcrypt 哈希（bcrypt 限制 72 字节，自动截断）"""
    # bcrypt 最多处理 72 字节，超出部分直接截断
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    return pwd_context.hash(password_bytes.decode("utf-8", errors="ignore"))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希值是否匹配（同样截断至 72 字节）"""
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    return pwd_context.verify(password_bytes.decode("utf-8", errors="ignore"), hashed_password)


# ============ JWT 令牌工具 ============

def create_access_token(user_id: str, email: str, role: str) -> str:
    """创建访问令牌（短期有效）"""
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """创建刷新令牌（长期有效）"""
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT 令牌，返回 payload 或 None"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# ============ 认证依赖注入（FastAPI Depends） ============

# ── 单用户模式（桌面版免登录） ──
#
# 背景：桌面版是「一个人的本机应用」，每次启动都要登录毫无意义。
# 但仅仅设置 AUTH_REQUIRED=false 是不够的 —— 那只影响日志文案，
# 大量路由（岗位 / 题库 / 会话 / 上传 / 分析）用的是 get_current_user，
# 依然会返回 401。
#
# 做法：单用户模式下，get_current_user 不再要求 token，而是返回一个
# **真实存在于 users 表里的固定本地账号**。
#
# 为什么必须是真实账号，不能只造一个假 id：
#   positions / interview_sessions / uploads 等表的 user_id 都带
#   `ForeignKey("users.id")`。用一个不存在的 id 写入会直接触发外键约束
#   失败（SQLite 开了外键时整条 insert 报错）。
#
# 为什么用固定 UUID 而不是「第一个用户」：
#   固定 id 与用户注册顺序无关，可重复、可预测；也不会把网页版真实
#   账号的数据混进来。__init_db 建表时会把该账号插进去。
LOCAL_USER_ID = "00000000-0000-4000-8000-000000000001"
LOCAL_USER_EMAIL = "desktop@local"
LOCAL_USER_NAME = "本机用户"


def auth_disabled() -> bool:
    """当前是否为单用户模式（桌面版免登录）"""
    return not settings.AUTH_REQUIRED


async def _ensure_local_user(db: AsyncSession):
    """取出（必要时创建）单用户模式的固定本地账号"""
    from models.db_models import User

    result = await db.execute(select(User).where(User.id == LOCAL_USER_ID))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        id=LOCAL_USER_ID,
        email=LOCAL_USER_EMAIL,
        display_name=LOCAL_USER_NAME,
        role="admin",
        is_active=True,
        # 本机账号不用于密码登录，但该列非空，填一个不可逆的占位值
        hashed_password="!disabled-local-account-no-login",
        preferences={},
    )
    db.add(user)
    try:
        await db.commit()
    except Exception:
        # 并发请求可能同时插入：回滚后重新查询即可
        await db.rollback()
        result = await db.execute(select(User).where(User.id == LOCAL_USER_ID))
        existing = result.scalar_one_or_none()
        if existing is None:
            raise
        return existing
    await db.refresh(user)
    return user


class CurrentUser:
    """通过 Depends 注入当前认证用户信息"""

    def __init__(self, user_id: str, email: str, role: str):
        self.id = user_id
        self.email = email
        self.role = role


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """
    从请求中提取 Bearer Token 并验证，返回当前用户信息。

    用法：
        @router.get("/protected")
        async def protected_route(user: CurrentUser = Depends(get_current_user)):
            return {"user_id": user.id}

    单用户模式（AUTH_REQUIRED=false，桌面版默认）：
        不要求 token，一律返回固定的本机账号。这样所有用本依赖的路由
        （岗位 / 题库 / 会话 / 上传 / 分析）都无需登录即可使用，
        数据统一归属该账号，不会因重启丢失。
    """
    if auth_disabled():
        local = await _ensure_local_user(db)
        return CurrentUser(user_id=local.id, email=local.email, role=local.role)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证令牌",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请使用访问令牌",
        )

    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role", "user")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌内容无效",
        )

    # 验证用户是否仍存在且激活
    from models.db_models import User
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )

    return CurrentUser(user_id=user_id, email=email, role=role)


# ── 可选的认证（允许未登录访问，但提供用户信息） ──

async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[CurrentUser]:
    """
    与 get_current_user 类似，但不强制要求认证。
    未登录时返回 None。

    单用户模式下返回固定的本机账号（而不是 None），
    这样聊天 / 知识库 / 系统音频等路由也能正确关联到该账号的数据。
    """
    if auth_disabled():
        local = await _ensure_local_user(db)
        return CurrentUser(user_id=local.id, email=local.email, role=local.role)

    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


# ── 管理员权限校验 ──

async def get_admin_user(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """要求管理员权限"""
    if user.role not in ("admin", "enterprise"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return user
