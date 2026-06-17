"""
题库管理路由 — CRUD + 批量导入 + 面试中选题
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db_models import QuestionBankItem
from utils.auth import get_current_user, CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/question-bank", tags=["question-bank"])

# 种子数据库路径
_SEED_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "question_bank.db")


# ============ 请求/响应模型 ============

class QuestionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    category: str = Field(default="general")
    difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    tags: list[str] = Field(default_factory=list)
    expected_answer: str = Field(default="")


class QuestionResponse(BaseModel):
    id: str
    title: str
    content: str
    category: str
    difficulty: str
    tags: list[str]
    expected_answer: str
    is_public: bool
    usage_count: int
    created_at: str


class QuestionListResponse(BaseModel):
    questions: list[QuestionResponse]
    total: int
    page: int
    page_size: int


class QuestionImportResponse(BaseModel):
    imported: int
    skipped: int
    message: str


# ============ 辅助 ============

def _to_response(q: QuestionBankItem) -> QuestionResponse:
    return QuestionResponse(
        id=q.id,
        title=q.title,
        content=q.content,
        category=q.category or "general",
        difficulty=q.difficulty or "medium",
        tags=q.tags or [],
        expected_answer=q.expected_answer or "",
        is_public=q.is_public or False,
        usage_count=q.usage_count or 0,
        created_at=q.created_at.isoformat() if q.created_at else "",
    )


# ============ API 端点 ============

@router.get("/", response_model=QuestionListResponse)
async def list_questions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    search: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出题库（系统内置题目 + 用户自建题目，不筛选则显示全部）"""
    conditions = [
        or_(
            QuestionBankItem.user_id.is_(None),  # 系统内置，全员可见
            QuestionBankItem.user_id == user.id,  # 用户自建
        )
    ]
    if category:
        conditions.append(QuestionBankItem.category == category)
    if difficulty:
        conditions.append(QuestionBankItem.difficulty == difficulty)
    if search:
        conditions.append(
            or_(
                QuestionBankItem.title.contains(search),
                QuestionBankItem.content.contains(search),
            )
        )

    count_q = select(func.count()).select_from(QuestionBankItem).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(QuestionBankItem)
        .where(*conditions)
        .order_by(QuestionBankItem.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(q)
    items = result.scalars().all()

    return QuestionListResponse(
        questions=[_to_response(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=QuestionResponse, status_code=201)
async def create_question(
    req: QuestionCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动添加题目"""
    item = QuestionBankItem(
        user_id=user.id,
        title=req.title,
        content=req.content,
        category=req.category,
        difficulty=req.difficulty,
        tags=req.tags,
        expected_answer=req.expected_answer,
        created_at=datetime.now(timezone.utc),
    )
    db.add(item)
    await db.flush()
    return _to_response(item)


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(
    question_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单题详情"""
    result = await db.execute(
        select(QuestionBankItem).where(
            QuestionBankItem.id == question_id,
            QuestionBankItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="题目不存在")
    return _to_response(item)


@router.put("/{question_id}", response_model=QuestionResponse)
async def update_question(
    question_id: str,
    req: QuestionCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新题目"""
    result = await db.execute(
        select(QuestionBankItem).where(
            QuestionBankItem.id == question_id,
            QuestionBankItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="题目不存在")

    item.title = req.title
    item.content = req.content
    item.category = req.category
    item.difficulty = req.difficulty
    item.tags = req.tags
    item.expected_answer = req.expected_answer
    item.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return _to_response(item)


@router.delete("/{question_id}", status_code=204)
async def delete_question(
    question_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除题目"""
    result = await db.execute(
        select(QuestionBankItem).where(
            QuestionBankItem.id == question_id,
            QuestionBankItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="题目不存在")
    await db.delete(item)


@router.post("/import/leetcode", response_model=QuestionImportResponse)
async def import_leetcode(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """一键导入内置题库（184 题，从种子数据库）"""
    if not os.path.exists(_SEED_DB):
        raise HTTPException(status_code=404, detail="题库种子文件不存在")

    import sqlite3
    try:
        seed_conn = sqlite3.connect(f"file:{_SEED_DB}?mode=ro", uri=True)
        seed_rows = seed_conn.execute(
            "SELECT id, user_id, team_id, title, content, category, difficulty, "
            "tags, expected_answer, is_public, usage_count, created_at, updated_at "
            "FROM question_bank"
        ).fetchall()
        seed_conn.close()
    except Exception:
        raise HTTPException(status_code=500, detail="题库种子文件读取失败")

    imported = 0
    skipped = 0
    now = datetime.now(timezone.utc)

    for row in seed_rows:
        title = row[3]
        # 跳过已存在的（按标题去重，匹配当前用户）
        existing = await db.execute(
            select(QuestionBankItem).where(
                QuestionBankItem.user_id == user.id,
                QuestionBankItem.title == title,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        tags_raw = row[7]
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else (tags_raw or [])

        item = QuestionBankItem(
            user_id=user.id,
            title=title,
            content=row[4],
            category=row[5] or "general",
            difficulty=row[6] or "medium",
            tags=tags,
            expected_answer=row[8] or "",
            is_public=False,
            usage_count=0,
            created_at=now,
        )
        db.add(item)
        imported += 1

    await db.flush()
    logger.info(f"LeetCode import: {imported} new, {skipped} skipped for user {user.id}")

    return QuestionImportResponse(
        imported=imported,
        skipped=skipped,
        message=f"成功导入 {imported} 题，跳过 {skipped} 题（已存在）",
    )


@router.get("/categories/list")
async def list_categories(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取用户题库中的所有分类"""
    result = await db.execute(
        select(QuestionBankItem.category, func.count())
        .where(QuestionBankItem.user_id == user.id)
        .group_by(QuestionBankItem.category)
    )
    rows = result.all()
    return {"categories": [{"name": r[0], "count": r[1]} for r in rows]}
