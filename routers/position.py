"""岗位管理路由 — CRUD + JD 管理"""

import logging
import re

from fastapi import APIRouter, HTTPException

from models.schemas import (
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    PositionListResponse,
    JDCreate,
    JDResponse,
)
from services.position_store import PositionStore
from config import settings
from services.vector_store import VectorStoreManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/positions", tags=["positions"])

# 岗位名称校验正则
_NAME_PATTERN = re.compile(r"^[\w\u4e00-\u9fff-]{2,50}$")


def _validate_position_name(name: str):
    if not _NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail="岗位名称需为 2-50 个字符，允许字母/数字/中文/下划线/连字符",
        )


# ============ 岗位 CRUD ============


@router.post("", response_model=PositionResponse, status_code=201)
async def create_position(req: PositionCreate):
    """创建新岗位"""
    _validate_position_name(req.name)
    store = PositionStore()
    try:
        return store.create(req.name, req.description)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("", response_model=PositionListResponse)
async def list_positions():
    """列出所有岗位"""
    store = PositionStore()
    return PositionListResponse(positions=store.list_all())


@router.get("/{name}", response_model=PositionResponse)
async def get_position(name: str):
    """获取岗位详情（含所有 JD）"""
    store = PositionStore()
    pos = store.get(name)
    if not pos:
        raise HTTPException(status_code=404, detail=f"岗位 '{name}' 不存在")
    return pos


@router.put("/{name}", response_model=PositionResponse)
async def update_position(name: str, req: PositionUpdate):
    """更新岗位描述"""
    store = PositionStore()
    pos = store.update(name, req.description)
    if not pos:
        raise HTTPException(status_code=404, detail=f"岗位 '{name}' 不存在")
    return pos


@router.delete("/{name}")
async def delete_position(name: str):
    """删除岗位及其关联的向量知识库"""
    store = PositionStore()
    if not store.get(name):
        raise HTTPException(status_code=404, detail=f"岗位 '{name}' 不存在")

    # 先尝试删除向量知识库
    try:
        vms = VectorStoreManager(settings)
        vms.delete_collection(name)
    except Exception as e:
        logger.warning(f"Failed to delete vector collection for '{name}': {e}")

    store.delete(name)
    return {"message": f"岗位 '{name}' 已删除"}


# ============ JD 管理 ============


@router.post("/{name}/jds", response_model=JDResponse, status_code=201)
async def add_jd(name: str, req: JDCreate):
    """为岗位添加 JD"""
    store = PositionStore()
    jd = store.add_jd(name, req.content)
    if jd is None:
        raise HTTPException(status_code=404, detail=f"岗位 '{name}' 不存在")
    return jd


@router.delete("/{name}/jds/{jd_id}")
async def remove_jd(name: str, jd_id: str):
    """删除指定 JD"""
    store = PositionStore()
    if not store.remove_jd(name, jd_id):
        raise HTTPException(status_code=404, detail=f"JD '{jd_id}' 不存在或岗位 '{name}' 不存在")
    return {"message": f"JD '{jd_id}' 已删除"}


@router.put("/{name}/jds/{jd_id}", response_model=JDResponse)
async def update_jd(name: str, jd_id: str, req: JDCreate):
    """修改指定 JD 内容"""
    store = PositionStore()
    jd = store.update_jd(name, jd_id, req.content)
    if jd is None:
        raise HTTPException(status_code=404, detail=f"JD '{jd_id}' 不存在或岗位 '{name}' 不存在")
    return jd
