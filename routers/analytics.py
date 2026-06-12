"""
分析仪表盘路由 — 统计数据 / 趋势 / 薄弱项 / 对比
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, extract, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.db_models import (
    InterviewSession,
    ChatMessage,
    QARecord,
    InterviewReport,
)
from utils.auth import get_current_user, CurrentUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ============ 响应模型 ============

class DashboardOverview(BaseModel):
    """仪表盘概览"""
    total_sessions: int = 0
    total_questions_answered: int = 0
    avg_session_duration_min: float = 0.0
    sessions_this_week: int = 0
    sessions_this_month: int = 0
    completion_rate: float = 0.0  # 完成率
    most_used_mode: str = ""
    avg_report_score: Optional[float] = None  # 平均评分
    streak_days: int = 0  # 连续练习天数


class TrendPoint(BaseModel):
    """趋势数据点"""
    date: str
    sessions: int = 0
    avg_score: Optional[float] = None
    questions_answered: int = 0


class TrendData(BaseModel):
    """趋势数据"""
    points: list[TrendPoint]
    period: str  # "7d" / "30d" / "90d"


class DimensionScore(BaseModel):
    """维度评分"""
    name: str
    score: float
    comment: str = ""


class WeaknessItem(BaseModel):
    """薄弱项"""
    dimension: str
    current_score: float
    target_score: float = 60.0
    gap: float
    suggestion: str = ""
    trend: str = "stable"  # "improving" / "declining" / "stable"


class WeaknessAnalysis(BaseModel):
    """薄弱项分析"""
    dimensions: list[DimensionScore]
    weaknesses: list[WeaknessItem]
    strongest_dimension: str = ""
    updated_at: str = ""


class ComparisonData(BaseModel):
    """面试对比"""
    sessions: list[dict]  # 每次面试的核心指标
    score_trend: list[dict]  # 评分趋势
    improvement_rate: float = 0.0


class StatsSummary(BaseModel):
    """统计汇总"""
    total_practice_time_min: float = 0.0
    total_chars_written: int = 0
    avg_answer_length: int = 0
    avg_thinking_time_sec: float = 0.0
    top_tags: list[str] = []
    sessions_by_mode: dict = {}
    sessions_by_level: dict = {}
    sessions_by_round: dict = {}


# ============ API 端点 ============

@router.get("/dashboard", response_model=DashboardOverview)
async def get_dashboard(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取仪表盘概览数据"""
    user_id = user.id
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    # 总会话数
    total = await _scalar(
        db,
        select(func.count()).select_from(InterviewSession)
        .where(InterviewSession.user_id == user_id)
    )

    # 总答题数
    total_qa = await _scalar(
        db,
        select(func.count()).select_from(QARecord)
        .join(InterviewSession, QARecord.session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user_id)
    )

    # 平均时长
    avg_dur_result = await db.execute(
        select(func.avg(InterviewSession.duration_minutes))
        .where(InterviewSession.user_id == user_id, InterviewSession.status == "completed")
    )
    avg_dur = avg_dur_result.scalar()
    avg_duration_min = round(float(avg_dur), 1) if avg_dur else 0.0

    # 本周会话数
    sessions_week = await _scalar(
        db,
        select(func.count()).select_from(InterviewSession)
        .where(
            InterviewSession.user_id == user_id,
            InterviewSession.started_at >= week_start,
        )
    )

    # 本月会话数
    sessions_month = await _scalar(
        db,
        select(func.count()).select_from(InterviewSession)
        .where(
            InterviewSession.user_id == user_id,
            InterviewSession.started_at >= month_start,
        )
    )

    # 完成率
    completed = await _scalar(
        db,
        select(func.count()).select_from(InterviewSession)
        .where(InterviewSession.user_id == user_id, InterviewSession.status == "completed")
    )
    completion_rate = round(completed / total * 100, 1) if total > 0 else 0.0

    # 最常用模式
    mode_result = await db.execute(
        select(InterviewSession.mode, func.count())
        .where(InterviewSession.user_id == user_id)
        .group_by(InterviewSession.mode)
        .order_by(func.count().desc())
        .limit(1)
    )
    mode_row = mode_result.first()
    most_used_mode = mode_row[0] if mode_row else ""
    # 模式名称映射
    mode_labels = {"interviewer": "面试官模式", "candidate": "求职者模式"}
    most_used_mode = mode_labels.get(most_used_mode, most_used_mode)

    # 平均评分（从报告中提取）
    avg_score = await _get_avg_score(db, user_id)

    # 连续练习天数
    streak = await _calc_streak(db, user_id, now)

    return DashboardOverview(
        total_sessions=total,
        total_questions_answered=total_qa,
        avg_session_duration_min=avg_duration_min,
        sessions_this_week=sessions_week,
        sessions_this_month=sessions_month,
        completion_rate=completion_rate,
        most_used_mode=most_used_mode,
        avg_report_score=avg_score,
        streak_days=streak,
    )


@router.get("/progress", response_model=TrendData)
async def get_progress(
    days: int = Query(30, ge=7, le=365),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取进步趋势（按天聚合）"""
    user_id = user.id
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    # 按日期聚合会话数和平均评分
    query = (
        select(
            func.date(InterviewSession.started_at).label("date"),
            func.count(InterviewSession.id).label("session_count"),
            func.sum(InterviewSession.questions_answered).label("qa_total"),
        )
        .where(
            InterviewSession.user_id == user_id,
            InterviewSession.started_at >= start_date,
        )
        .group_by(func.date(InterviewSession.started_at))
        .order_by("date")
    )
    result = await db.execute(query)
    rows = result.all()

    points = []
    for row in rows:
        # 获取当天平均评分
        day_score = await _get_day_avg_score(db, user_id, row.date)
        points.append(TrendPoint(
            date=str(row.date),
            sessions=row.session_count,
            avg_score=day_score,
            questions_answered=row.qa_total or 0,
        ))

    return TrendData(points=points, period=f"{days}d")


@router.get("/weakness", response_model=WeaknessAnalysis)
async def get_weakness(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取薄弱项分析"""
    user_id = user.id

    # 获取最近5份报告的维度评分
    result = await db.execute(
        select(InterviewReport)
        .join(InterviewSession, InterviewReport.session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user_id)
        .order_by(InterviewReport.created_at.desc())
        .limit(5)
    )
    reports = result.scalars().all()

    if not reports:
        return WeaknessAnalysis(dimensions=[], weaknesses=[], strongest_dimension="")

    # 聚合维度评分
    dim_scores: dict[str, list[float]] = {}
    for report in reports:
        dims = report.dimensions or []
        for dim in dims:
            name = dim.get("name", "未知")
            score = dim.get("score", 0)
            if name not in dim_scores:
                dim_scores[name] = []
            dim_scores[name].append(float(score))

    # 计算平均分
    dimensions = []
    weaknesses = []
    max_avg = -1
    strongest = ""

    for name, scores in dim_scores.items():
        avg = round(sum(scores) / len(scores), 1)
        dimensions.append(DimensionScore(name=name, score=avg))

        if avg > max_avg:
            max_avg = avg
            strongest = name

        # 判断趋势（最近一次 vs 平均）
        latest = scores[0] if scores else avg
        trend = "stable"
        if latest > avg + 3:
            trend = "improving"
        elif latest < avg - 3:
            trend = "declining"

        gap = round(max(0, 70 - avg), 1)
        if gap > 5:  # 差距超过5分才算薄弱
            weaknesses.append(WeaknessItem(
                dimension=name,
                current_score=avg,
                gap=gap,
                suggestion=f"建议加强{name}方面的练习",
                trend=trend,
            ))

    # 按差距排序
    weaknesses.sort(key=lambda w: w.gap, reverse=True)

    return WeaknessAnalysis(
        dimensions=dimensions,
        weaknesses=weaknesses[:5],  # Top 5 薄弱项
        strongest_dimension=strongest,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/comparison", response_model=ComparisonData)
async def get_comparison(
    limit: int = Query(10, ge=2, le=50),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取多次面试对比"""
    user_id = user.id

    result = await db.execute(
        select(InterviewSession)
        .where(InterviewSession.user_id == user_id, InterviewSession.status == "completed")
        .order_by(InterviewSession.started_at.asc())
        .limit(limit)
    )
    sessions = result.scalars().all()

    session_data = []
    score_trend = []

    for i, s in enumerate(sessions):
        # 获取报告评分
        report_result = await db.execute(
            select(InterviewReport).where(InterviewReport.session_id == s.id)
        )
        report = report_result.scalar_one_or_none()

        scores = report.scores if report else {}
        avg = round(sum(scores.values()) / len(scores), 1) if scores else None

        session_data.append({
            "index": i + 1,
            "date": s.started_at.isoformat() if s.started_at else "",
            "mode": s.mode,
            "questions_answered": s.questions_answered,
            "duration_minutes": s.duration_minutes,
            "scores": scores,
            "avg_score": avg,
        })
        if avg is not None:
            score_trend.append({"index": i + 1, "avg_score": avg})

    # 改进率：第一次 vs 最后一次
    improvement = 0.0
    if len(score_trend) >= 2:
        first = score_trend[0]["avg_score"]
        last = score_trend[-1]["avg_score"]
        improvement = round(last - first, 1)

    return ComparisonData(
        sessions=session_data,
        score_trend=score_trend,
        improvement_rate=improvement,
    )


@router.get("/stats", response_model=StatsSummary)
async def get_stats(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取统计汇总"""
    user_id = user.id

    # 总练习时间
    total_time_result = await db.execute(
        select(func.sum(InterviewSession.duration_minutes))
        .where(InterviewSession.user_id == user_id)
    )
    total_time = total_time_result.scalar() or 0

    # 总字数
    total_chars_result = await db.execute(
        select(func.sum(QARecord.answer_chars))
        .join(InterviewSession, QARecord.session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user_id)
    )
    total_chars = total_chars_result.scalar() or 0

    # 平均回答字数
    avg_chars_result = await db.execute(
        select(func.avg(QARecord.answer_chars))
        .join(InterviewSession, QARecord.session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user_id)
    )
    avg_chars = round(float(avg_chars_result.scalar()), 0) if avg_chars_result.scalar() else 0

    # 按模式统计
    mode_result = await db.execute(
        select(InterviewSession.mode, func.count())
        .where(InterviewSession.user_id == user_id)
        .group_by(InterviewSession.mode)
    )
    sessions_by_mode = {row[0]: row[1] for row in mode_result.all()}

    # 按级别统计
    level_result = await db.execute(
        select(InterviewSession.candidate_level, func.count())
        .where(InterviewSession.user_id == user_id)
        .group_by(InterviewSession.candidate_level)
    )
    sessions_by_level = {row[0] or "未设置": row[1] for row in level_result.all()}

    # 按轮次统计
    round_result = await db.execute(
        select(InterviewSession.interview_round, func.count())
        .where(InterviewSession.user_id == user_id)
        .group_by(InterviewSession.interview_round)
    )
    sessions_by_round = {row[0] or "未设置": row[1] for row in round_result.all()}

    return StatsSummary(
        total_practice_time_min=round(float(total_time), 0),
        total_chars_written=total_chars,
        avg_answer_length=int(avg_chars),
        avg_thinking_time_sec=0.0,
        top_tags=[],
        sessions_by_mode=sessions_by_mode,
        sessions_by_level=sessions_by_level,
        sessions_by_round=sessions_by_round,
    )


# ============ 辅助函数 ============

async def _scalar(db: AsyncSession, query) -> int:
    """执行 count 查询并返回整数"""
    result = await db.execute(query)
    val = result.scalar()
    return val if val is not None else 0


async def _get_avg_score(db: AsyncSession, user_id: str) -> Optional[float]:
    """获取用户所有报告的平均综合评分"""
    result = await db.execute(
        select(InterviewReport.scores)
        .join(InterviewSession, InterviewReport.session_id == InterviewSession.id)
        .where(InterviewSession.user_id == user_id)
        .limit(20)
    )
    all_scores = []
    for (scores,) in result.all():
        if scores and isinstance(scores, dict):
            all_scores.extend(scores.values())

    if not all_scores:
        return None
    return round(sum(all_scores) / len(all_scores), 1)


async def _get_day_avg_score(db: AsyncSession, user_id: str, date_str: str) -> Optional[float]:
    """获取某一天的平均评分"""
    result = await db.execute(
        select(InterviewReport.scores)
        .join(InterviewSession, InterviewReport.session_id == InterviewSession.id)
        .where(
            InterviewSession.user_id == user_id,
            func.date(InterviewSession.started_at) == date_str,
        )
        .limit(10)
    )
    all_scores = []
    for (scores,) in result.all():
        if scores and isinstance(scores, dict):
            all_scores.extend(scores.values())

    if not all_scores:
        return None
    return round(sum(all_scores) / len(all_scores), 1)


async def _calc_streak(db: AsyncSession, user_id: str, now: datetime) -> int:
    """计算连续练习天数"""
    streak = 0
    check_date = now.date()
    for _ in range(365):  # 最多往前查365天
        result = await db.execute(
            select(func.count())
            .select_from(InterviewSession)
            .where(
                InterviewSession.user_id == user_id,
                func.date(InterviewSession.started_at) == check_date,
            )
        )
        count = result.scalar() or 0
        if count > 0:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            if streak == 0:
                check_date -= timedelta(days=1)
                continue
            break
    return streak
