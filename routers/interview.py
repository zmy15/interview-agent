"""面试控制路由 — 开始/停止/报告/计划"""

import logging

from fastapi import APIRouter, HTTPException

from models.schemas import (
    InterviewStartRequest,
    InterviewPlanRequest,
    InterviewPlanResponse,
    Message,
    ReportRequest,
    ReportResponse,
    InterviewStopResponse,
)
from services.position_store import PositionStore
from services.llm_client import generate_report
from utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview", tags=["interview"])


@router.post("/start")
async def start_interview(req: InterviewStartRequest):
    """
    开始面试，返回组装好的 system 消息。
    内部调用 PositionStore 获取岗位 JD。
    """
    prompt_kwargs = {
        "jd": "暂无岗位描述",
        "resume": req.resume_text or "",
        "code": req.code_context or "",
    }

    if req.position_name:
        store = PositionStore()
        pos = store.get(req.position_name)
        if not pos:
            raise HTTPException(status_code=404, detail=f"岗位 '{req.position_name}' 不存在")
        if pos.jds:
            jd_text = "\n\n".join(jd.content for jd in pos.jds)
            prompt_kwargs["jd"] = jd_text

    try:
        system_content = load_prompt(req.mode, **prompt_kwargs)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"不支持的面试模式: {req.mode}")

    return Message(role="system", content=system_content)


@router.post("/stop", response_model=InterviewStopResponse)
async def stop_interview():
    """停止面试（预留接口）"""
    return InterviewStopResponse(message="面试已结束")


@router.post("/report", response_model=ReportResponse)
async def generate_interview_report(req: ReportRequest):
    """
    基于完整对话历史生成面试评价报告。
    """
    # 格式化对话历史
    history_parts = []
    for msg in req.messages:
        role_label = {
            "system": "系统",
            "user": "用户",
            "assistant": "AI",
        }.get(msg.role, msg.role)
        history_parts.append(f"【{role_label}】: {msg.content}")

    history_text = "\n\n".join(history_parts)

    try:
        report_prompt = load_prompt("report", history=history_text)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="报告模板不存在")

    report = await generate_report(
        messages=[{"role": "user", "content": report_prompt}],
        api_key=req.api_key,
    )

    return ReportResponse(report=report)


@router.post("/plan", response_model=InterviewPlanResponse)
async def get_interview_plan(req: InterviewPlanRequest):
    """
    根据面试时长推算问题数量。

    推算规则：
    - 每个问题平均 3-5 分钟（含回答时间）
    - 预留 2 分钟开场和 3 分钟总结
    - 最少 3 题，最多 30 题
    """
    effective_minutes = max(1, req.duration_minutes - 5)  # 减去开场+总结时间
    # 每题约 4 分钟（回答 + 追问），至少 1 题
    question_count = max(3, min(30, effective_minutes * 60 // 240))

    avg_time = round(req.duration_minutes / question_count, 1) if question_count > 0 else 0

    return InterviewPlanResponse(
        question_count=question_count,
        duration_minutes=req.duration_minutes,
        avg_time_per_question=avg_time,
        description=f"预计 {question_count} 道题目，每题约 {avg_time} 分钟",
    )
