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
        prompt_kwargs["position_type"] = pos.position_type
        if pos.jds:
            # 按 jd_id 过滤：指定了则只取匹配的 JD，否則用全部
            if req.jd_id:
                matched_jds = [jd for jd in pos.jds if jd.id == req.jd_id]
                if matched_jds:
                    jd_text = "\n\n".join(jd.content for jd in matched_jds)
                    prompt_kwargs["jd"] = jd_text
            else:
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
    根据面试时长和回答长度推算问题数量。

    固定环节：
    - 自我介绍：3 分钟
    - 反问环节：3 分钟

    技术问答时间 = 总时长 - 6 分钟
    每题耗时根据回答长度：
    - short（简短）: 2 分钟/题
    - medium（适中）: 3 分钟/题
    - long（详细）: 5 分钟/题
    """
    # 固定环节时间
    INTRO_MIN = 3      # 自我介绍
    REVERSE_MIN = 3    # 反问环节
    FIXED_MIN = INTRO_MIN + REVERSE_MIN  # 6 分钟

    # 回答长度 → 每题耗时（秒）
    SPEED_MAP = {
        "short": 120,   # 2 分钟/题
        "medium": 180,  # 3 分钟/题
        "long": 300,    # 5 分钟/题
    }
    speed_per_q = SPEED_MAP.get(req.answer_length, 180)

    # 技术问答可用时间
    remaining_min = max(1, req.duration_minutes - FIXED_MIN)
    remaining_sec = remaining_min * 60

    # 计算题数
    question_count = max(3, min(30, remaining_sec // speed_per_q))

    # 实际技术问答用时
    actual_tech_min = question_count * speed_per_q // 60
    # 每题平均时间（总时长/题数，含固定环节分摊）
    avg_time = round(req.duration_minutes / question_count, 1) if question_count > 0 else 0

    # 各环节时长分解
    breakdown = {
        "自我介绍": INTRO_MIN,
        "技术问答": actual_tech_min,
        "反问环节": REVERSE_MIN,
    }

    length_label = {"short": "简短", "medium": "适中", "long": "详细"}.get(req.answer_length, "适中")

    return InterviewPlanResponse(
        question_count=question_count,
        duration_minutes=req.duration_minutes,
        avg_time_per_question=avg_time,
        description=f"回答风格「{length_label}」→ 预计 {question_count} 道技术题（含自我介绍+反问环节）",
        breakdown=breakdown,
    )
