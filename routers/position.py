"""岗位管理路由 — CRUD + JD 管理"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from models.schemas import (
    JDCreate,
    JDResponse,
    PositionCreate,
    PositionListResponse,
    PositionResponse,
    PositionUpdate,
)
from services.position_store import PositionStore
from services.vector_store import VectorStoreManager
from utils.auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/positions", tags=["positions"])

# 岗位名称校验正则。
# 允许空格：真实岗位名常带空格（如「AI Agent 质量效能工程师」）。
# 空格在 URL 里由前端 encodeURIComponent 编码，知识库目录名另有
# VectorStoreManager._sanitize_collection_name 兜底，因此不必限制得过窄。
_NAME_PATTERN = re.compile(r"^[\w\u4e00-\u9fff\- ]{2,50}$")


def _validate_position_name(name: str):
    """校验岗位名称（首尾空白与连续空白已由 PositionCreate 归一化）"""
    if not _NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail="岗位名称需为 2-50 个字符，允许字母/数字/中文/下划线/连字符/空格",
        )


# ============ 岗位 CRUD ============


@router.post("", response_model=PositionResponse, status_code=201)
async def create_position(
    req: PositionCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """创建新岗位（可在同一个请求里附带第一份 JD）

    岗位与 JD 在同一个数据库事务里写入（见 database.get_db）：
    要么都成功，要么都不落库，不会出现「岗位建好了但 JD 丢了」。
    """
    _validate_position_name(req.name)
    store = PositionStore(db)
    try:
        pos = await store.create(req.name, req.description, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    jd_content = (req.jd_content or "").strip()
    if jd_content:
        jd = await store.add_jd(req.name, jd_content, user_id=user.id)
        if jd is not None:
            pos.jds.append(jd)

    return pos


@router.get("", response_model=PositionListResponse)
async def list_positions(
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """列出所有岗位"""
    store = PositionStore(db)
    return PositionListResponse(positions=await store.list_all(user_id=user.id))


@router.get("/{name}", response_model=PositionResponse)
async def get_position(
    name: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """获取岗位详情（含所有 JD，仅限本人岗位）"""
    store = PositionStore(db)
    pos = await store.get(name, user_id=user.id)
    if not pos:
        raise HTTPException(status_code=404, detail=f"岗位 '{name}' 不存在")
    return pos


@router.put("/{name}", response_model=PositionResponse)
async def update_position(
    name: str,
    req: PositionUpdate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """更新岗位描述（仅限本人岗位）"""
    store = PositionStore(db)
    pos = await store.update(name, req.description, user_id=user.id)
    if not pos:
        raise HTTPException(status_code=404, detail=f"岗位 '{name}' 不存在")
    return pos


@router.delete("/{name}")
async def delete_position(
    name: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """删除岗位及其关联的向量知识库（仅限本人岗位）"""
    store = PositionStore(db)
    if not await store.get(name, user_id=user.id):
        raise HTTPException(status_code=404, detail=f"岗位 '{name}' 不存在")

    # 先尝试删除向量知识库
    try:
        vms = VectorStoreManager(settings)
        vms.delete_collection(name)
    except Exception as e:
        logger.warning(f"Failed to delete vector collection for '{name}': {e}")

    await store.delete(name, user_id=user.id)
    return {"message": f"岗位 '{name}' 已删除"}


# ============ JD 管理 ============


@router.post("/{name}/jds", response_model=JDResponse, status_code=201)
async def add_jd(
    name: str,
    req: JDCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """为岗位添加 JD（仅限本人岗位）"""
    store = PositionStore(db)
    jd = await store.add_jd(name, req.content, user_id=user.id)
    if jd is None:
        raise HTTPException(status_code=404, detail=f"岗位 '{name}' 不存在")
    return jd


@router.delete("/{name}/jds/{jd_id}")
async def remove_jd(
    name: str,
    jd_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """删除指定 JD（仅限本人岗位）"""
    store = PositionStore(db)
    if not await store.remove_jd(name, jd_id, user_id=user.id):
        raise HTTPException(status_code=404, detail=f"JD '{jd_id}' 不存在或岗位 '{name}' 不存在")
    return {"message": f"JD '{jd_id}' 已删除"}


@router.put("/{name}/jds/{jd_id}", response_model=JDResponse)
async def update_jd(
    name: str,
    jd_id: str,
    req: JDCreate,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """修改指定 JD 内容（仅限本人岗位）"""
    store = PositionStore(db)
    jd = await store.update_jd(name, jd_id, req.content, user_id=user.id)
    if jd is None:
        raise HTTPException(status_code=404, detail=f"JD '{jd_id}' 不存在或岗位 '{name}' 不存在")
    return jd
