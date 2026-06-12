"""面试控制路由 — 开始/停止/报告/计划"""

import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

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
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview", tags=["interview"])


@router.post("/start")
async def start_interview(req: InterviewStartRequest, db: AsyncSession = Depends(get_db)):
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
        store = PositionStore(db)
        pos = await store.get(req.position_name)
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
        system_content = load_prompt(
            req.mode,
            candidate_level=req.candidate_level or "",
            interview_round=req.interview_round or "",
            **prompt_kwargs,
        )
        # 追加用户补充说明
        if req.prompt_notes:
            system_content += "\n\n---\n【用户补充说明】\n" + req.prompt_notes
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
    支持结构化 QA 记录以生成更精准的逐题评估。
    """
    # 如果有结构化 QA 记录，优先使用
    if req.qa_records:
        qa_parts = []
        for i, qa in enumerate(req.qa_records, 1):
            qa_parts.append(
                f"第{i}题 — 面试官提问：{qa.question}\n"
                f"候选人回答（{qa.answer_chars}字）：{qa.answer}"
            )
        history_text = "\n\n---\n\n".join(qa_parts)
        history_text = f"面试共 {len(req.qa_records)} 道问答：\n\n{history_text}"
    else:
        # 回退到原始对话历史
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
        report_prompt = load_prompt(
            "report",
            history=history_text,
            candidate_level=req.candidate_level or "",
            interview_round=req.interview_round or "",
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="报告模板不存在")

    report = await generate_report(
        messages=[{"role": "user", "content": report_prompt}],
        api_key=req.api_key,
    )

    return ReportResponse(report=report)


def _compute_interview_plan(
    duration_minutes: int,
    answer_length: str,
    candidate_level: str | None,
    interview_round: str | None,
    coding_enabled: bool = False,
    elapsed_minutes: float = 0.0,
    answered_questions: int = 0,
):
    """
    核心计划算法：根据参数推算题目数量和时间分配。
    支持动态重新规划（传入已用时间和已答题数）。

    HR面特殊规则：
    - 时长强制上限 30 分钟
    - 强制禁用编程题
    - 问答环节标记为「综合素质问答」
    """
    # HR面：强制约束
    is_hr_round = interview_round == "hr"
    if is_hr_round:
        duration_minutes = min(duration_minutes, 30)
        coding_enabled = False

    # 固定环节时间
    INTRO_MIN = 3      # 自我介绍
    REVERSE_MIN = 3    # 反问环节（弹性，候选人可多问）
    FIXED_MIN = INTRO_MIN + REVERSE_MIN

    # 编程题预留时间（仅在启用编程题且为技术岗时生效；HR面强制为0）
    CODING_RESERVE_MIN = 0
    if coding_enabled:
        # 根据级别和时长决定编程题预留时间
        if candidate_level == "intern":
            CODING_RESERVE_MIN = 10  # 实习生：简单题约10分钟
        elif candidate_level == "new_grad":
            CODING_RESERVE_MIN = 15  # 校招生：中等题约15分钟
        elif candidate_level == "experienced":
            CODING_RESERVE_MIN = 20  # 社招生：设计题约20分钟
        else:
            CODING_RESERVE_MIN = 15

        # 如果总时长太短，减少编程题预留
        if duration_minutes < 30:
            CODING_RESERVE_MIN = min(CODING_RESERVE_MIN, duration_minutes // 3)
        # 编程题预留不超过总时长的40%
        CODING_RESERVE_MIN = min(CODING_RESERVE_MIN, int(duration_minutes * 0.4))

    # 回答长度 → 每题耗时（秒）
    SPEED_MAP = {
        "short": 120,
        "medium": 180,
        "long": 300,
    }
    speed_per_q = SPEED_MAP.get(answer_length, 180)

    # 候选人级别的题量调整系数
    level_multiplier = 1.0
    if candidate_level == "intern":
        level_multiplier = 1.3   # 实习生问题偏基础，可以多问
    elif candidate_level == "new_grad":
        level_multiplier = 1.1   # 校招生适中
    elif candidate_level == "experienced":
        level_multiplier = 0.8   # 社招生问题偏深，少问但深问

    # 面试轮次的题量调整系数
    round_multiplier = 1.0
    if interview_round == "first":
        round_multiplier = 1.2   # 一面覆盖面广，基础题耗时短可多问
    elif interview_round == "second":
        round_multiplier = 0.7   # 二面每个问题深挖，耗时长
    elif interview_round == "hr":
        round_multiplier = 1.0   # HR面每题耗时中等

    # 技术问答可用时间（扣除固定环节和编程题预留）
    total_reserved = FIXED_MIN + CODING_RESERVE_MIN
    remaining_min = max(1, duration_minutes - total_reserved)
    remaining_sec = remaining_min * 60

    # 计算总题数
    total_question_count = max(2, min(30, int(remaining_sec // speed_per_q * level_multiplier * round_multiplier)))

    # 动态调整：如果已进行了一段时间，重新计算剩余题数
    remaining_questions = total_question_count
    current_phase = "intro"

    if elapsed_minutes > 0:
        # 扣除已用时间
        elapsed_intro = min(INTRO_MIN, elapsed_minutes)
        time_after_intro = max(0, elapsed_minutes - elapsed_intro)

        # 剩余总时间（分钟）
        total_remaining = max(0, duration_minutes - elapsed_minutes)

        if time_after_intro <= 0:
            # 还在自我介绍阶段
            current_phase = "intro"
            remaining_questions = total_question_count
        elif total_remaining <= REVERSE_MIN:
            # 剩余时间不足，应进入反问环节
            current_phase = "reverse"
            remaining_questions = 0
        elif answered_questions >= total_question_count:
            # 题目已答完，应进入反问环节
            current_phase = "reverse"
            remaining_questions = 0
        elif coding_enabled and time_after_intro >= remaining_min * 0.6:
            # 如果已用时间超过技术问答的60%，进入编程题阶段
            current_phase = "coding"
            # 编程题后剩余题数减少
            remaining_questions = max(0, total_question_count - answered_questions)
        else:
            # 仍在技术问答阶段
            current_phase = "tech_qa"

            # 根据实际消耗的时间重新计算剩余可答题数
            tech_remaining_sec = max(0, remaining_sec - time_after_intro * 60)
            can_fit_questions = max(0, int(tech_remaining_sec // speed_per_q))
            remaining_questions = max(0, min(total_question_count - answered_questions, can_fit_questions))

            # 如果一题都放不下了，也该收尾了
            if remaining_questions <= 0 and answered_questions > 0:
                current_phase = "reverse"
    else:
        # 初始计划，从自我介绍开始
        current_phase = "intro"
        remaining_questions = total_question_count

    actual_tech_min = total_question_count * speed_per_q // 60
    avg_time = round(duration_minutes / total_question_count, 1) if total_question_count > 0 else 0

    # HR面使用不同标签
    qa_label = "综合素质问答" if is_hr_round else "技术问答"
    question_label = "综合素质题" if is_hr_round else "技术题"

    breakdown = {
        "自我介绍": INTRO_MIN,
        qa_label: min(actual_tech_min, remaining_min),
        "编程题": CODING_RESERVE_MIN,
        "反问环节": REVERSE_MIN,
    }

    # 构建描述
    level_label = {"intern": "实习生", "new_grad": "校招生", "experienced": "社招生"}.get(candidate_level or "", "")
    round_label = {"first": "一面", "second": "二面", "hr": "HR面"}.get(interview_round or "", "")
    length_label = {"short": "简短", "medium": "适中", "long": "详细"}.get(answer_length, "适中")
    meta_parts = [f"回答风格「{length_label}」"]
    if level_label:
        meta_parts.append(f"「{level_label}」")
    if round_label:
        meta_parts.append(f"「{round_label}」")
    meta_str = " · ".join(meta_parts)

    desc_parts = [f"{meta_str} → 预计 {total_question_count} 道{question_label}"]
    if coding_enabled and not is_hr_round:
        desc_parts.append(f"+ 编程题（约{CODING_RESERVE_MIN}分钟）")
    desc_parts.append("含自我介绍+反问环节")

    return {
        "question_count": total_question_count,
        "remaining_questions": remaining_questions,
        "duration_minutes": duration_minutes,
        "avg_time_per_question": avg_time,
        "description": "，".join(desc_parts),
        "breakdown": breakdown,
        "coding_reserved_min": CODING_RESERVE_MIN,
        "current_phase": current_phase,
    }


@router.post("/plan", response_model=InterviewPlanResponse)
async def get_interview_plan(req: InterviewPlanRequest):
    """
    根据面试时长、回答长度、候选人级别和面试轮次推算问题数量。
    支持动态重新规划（传入 elapsed_minutes 和 answered_questions）。
    实习生/校招生问题偏基础可多问，社招生问题偏深可少问。
    一面问题覆盖面广数量多，二面问题深数量少。
    编程题时间单独预留，不计入技术问答时间。
    """
    result = _compute_interview_plan(
        duration_minutes=req.duration_minutes,
        answer_length=req.answer_length,
        candidate_level=req.candidate_level,
        interview_round=req.interview_round,
        coding_enabled=req.coding_enabled,
        elapsed_minutes=req.elapsed_minutes,
        answered_questions=req.answered_questions,
    )

    return InterviewPlanResponse(
        question_count=result["question_count"],
        duration_minutes=result["duration_minutes"],
        avg_time_per_question=result["avg_time_per_question"],
        description=result["description"],
        breakdown=result["breakdown"],
        coding_reserved_min=result["coding_reserved_min"],
        current_phase=result["current_phase"],
        remaining_questions=result["remaining_questions"],
    )
