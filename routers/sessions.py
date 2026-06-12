"""
面试会话管理路由 — 历史记录 / 回放 / 列表
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from models.db_models import InterviewSession, ChatMessage, QARecord, InterviewReport
from utils.auth import get_current_user, get_optional_user, CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ============ 响应模型 ============

class SessionSummary(BaseModel):
    id: str
    mode: str
    candidate_level: Optional[str]
    interview_round: Optional[str]
    model_used: Optional[str]
    coding_enabled: bool
    duration_minutes: int
    questions_planned: int
    questions_answered: int
    status: str
    plan_snapshot: dict
    started_at: str
    ended_at: Optional[str]
    message_count: int = 0
    has_report: bool = False

    class Config:
        from_attributes = True


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    reasoning: Optional[str]
    token_count: int
    created_at: str


class QARecordResponse(BaseModel):
    id: int
    question_number: int
    question: str
    answer: str
    answer_chars: int
    answer_duration_sec: float


class SessionDetail(BaseModel):
    id: str
    mode: str
    candidate_level: Optional[str]
    interview_round: Optional[str]
    model_used: Optional[str]
    coding_enabled: bool
    duration_minutes: int
    questions_planned: int
    questions_answered: int
    status: str
    plan_snapshot: dict
    started_at: str
    ended_at: Optional[str]
    messages: list[MessageResponse] = []
    qa_records: list[QARecordResponse] = []
    report: Optional[dict] = None


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]
    total: int
    page: int
    page_size: int


# ============ API 端点 ============

@router.get("/", response_model=SessionListResponse)
async def list_sessions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    mode_filter: Optional[str] = Query(None, alias="mode"),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的面试历史列表"""
    # 构建查询
    conditions = [InterviewSession.user_id == user.id]
    if status_filter:
        conditions.append(InterviewSession.status == status_filter)
    if mode_filter:
        conditions.append(InterviewSession.mode == mode_filter)

    # 总数
    count_query = select(func.count()).select_from(InterviewSession).where(*conditions)
    total = (await db.execute(count_query)).scalar() or 0

    # 分页查询
    query = (
        select(InterviewSession)
        .where(*conditions)
        .order_by(desc(InterviewSession.started_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    sessions = result.scalars().all()

    # 补充 message_count 和 has_report
    summaries = []
    for s in sessions:
        # 计数消息
        msg_count_result = await db.execute(
            select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == s.id)
        )
        msg_count = msg_count_result.scalar() or 0

        # 检查报告
        report_result = await db.execute(
            select(InterviewReport).where(InterviewReport.session_id == s.id)
        )
        has_report = report_result.scalar_one_or_none() is not None

        summaries.append(SessionSummary(
            id=s.id,
            mode=s.mode,
            candidate_level=s.candidate_level,
            interview_round=s.interview_round,
            model_used=s.model_used,
            coding_enabled=s.coding_enabled,
            duration_minutes=s.duration_minutes,
            questions_planned=s.questions_planned,
            questions_answered=s.questions_answered,
            status=s.status,
            plan_snapshot=s.plan_snapshot or {},
            started_at=s.started_at.isoformat() if s.started_at else "",
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            message_count=msg_count,
            has_report=has_report,
        ))

    return SessionListResponse(
        sessions=summaries,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取单次面试的完整详情（含消息、QA记录、报告）"""
    result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.id == session_id, InterviewSession.user_id == user.id)
        .options(
            selectinload(InterviewSession.messages),
            selectinload(InterviewSession.qa_records),
            selectinload(InterviewSession.report),
        )
    )
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    return SessionDetail(
        id=session.id,
        mode=session.mode,
        candidate_level=session.candidate_level,
        interview_round=session.interview_round,
        model_used=session.model_used,
        coding_enabled=session.coding_enabled,
        duration_minutes=session.duration_minutes,
        questions_planned=session.questions_planned,
        questions_answered=session.questions_answered,
        status=session.status,
        plan_snapshot=session.plan_snapshot or {},
        started_at=session.started_at.isoformat() if session.started_at else "",
        ended_at=session.ended_at.isoformat() if session.ended_at else None,
        messages=[
            MessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                reasoning=m.reasoning,
                token_count=m.token_count,
                created_at=m.created_at.isoformat() if m.created_at else "",
            )
            for m in (session.messages or [])
        ],
        qa_records=[
            QARecordResponse(
                id=r.id,
                question_number=r.question_number,
                question=r.question,
                answer=r.answer,
                answer_chars=r.answer_chars,
                answer_duration_sec=r.answer_duration_sec,
            )
            for r in (session.qa_records or [])
        ],
        report={
            "content": session.report.content,
            "scores": session.report.scores,
            "dimensions": session.report.dimensions,
        } if session.report else None,
    )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除一次面试记录"""
    result = await db.execute(
        select(InterviewSession).where(
            InterviewSession.id == session_id,
            InterviewSession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    await db.delete(session)
    logger.info(f"Session deleted: {session_id} by user {user.id}")
