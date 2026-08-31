"""对话流式路由 — SSE 流式输出 + 模型列表 + LCEL RAG 管线 + 上下文窗口管理"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from models.schemas import ChatRequest, ModelsResponse
from services.llm_client import stream_chat
from services.model_registry import get_available_models, validate_model
from services.agent_tools import search_web
from services.coding_problem import select_problems, format_problems_for_prompt
from services.rag_pipeline import build_rag_context
from utils.prompt_loader import load_prompt
from utils.context_manager import estimate_tokens, trim_messages
from utils.auth import get_optional_user, CurrentUser
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/models", response_model=ModelsResponse)
async def list_models():
    """返回可用模型列表"""
    return ModelsResponse(models=get_available_models())


# ============ 辅助函数 ============

def _build_dynamic_context(req: ChatRequest, prompt_kwargs: dict) -> str:
    """构建每轮动态上下文（RAG + 搜索 + 编程题 + 题库），这些内容每轮都可能变化"""
    parts = []

    # 题库注入（从 prompt_kwargs 中获取已加载的题库内容）
    if prompt_kwargs.get("_question_bank_text"):
        parts.append(prompt_kwargs["_question_bank_text"])
        logger.info("Question bank injected | %d questions", len(req.question_bank_ids or []))

    # RAG 检索
    if req.position_name and req.messages:
        last_user_msg = req.messages[-1].content
        rag_context = build_rag_context(
            position_name=req.position_name,
            query=last_user_msg,
            top_k=settings.VECTOR_SEARCH_TOP_K,
        )
        if rag_context:
            parts.append(rag_context.strip())
            context_len = len(rag_context)
            logger.info("RAG context injected | position=%s | length=%d chars", req.position_name, context_len)
        else:
            logger.info("RAG context empty | position=%s — no knowledge base data", req.position_name)

    # 联网搜索
    if req.use_search and req.messages:
        try:
            last_user_msg = req.messages[-1].content
            search_result = search_web(last_user_msg)
            if search_result:
                parts.append("网络搜索结果：\n" + search_result)
        except Exception as e:
            logger.warning(f"Web search failed (non-blocking): {e}")

    # 编程题（仅求职者模式 + 技术岗）
    if req.coding_enabled and req.mode == "candidate":
        try:
            pos_type = prompt_kwargs.get("position_type", "未知")
            pos_name = req.position_name or ""
            conv_history = [m.content for m in req.messages[-10:]]
            problems = select_problems(
                position_type=pos_type,
                position_name=pos_name,
                conversation_history=conv_history,
                count=3,
            )
            if problems:
                parts.append(format_problems_for_prompt(problems))
        except Exception as e:
            logger.warning(f"Coding problem selection failed (non-blocking): {e}")

    return "\n\n---\n".join(parts) if parts else ""


async def _build_prompt_kwargs(req: ChatRequest, db: AsyncSession, user: Optional[CurrentUser] = None) -> dict:
    """构建静态 prompt 参数（JD / 简历 / 岗位类型 / 代码 / 时间预算）"""
    kwargs: dict = {
        "jd": "暂无岗位描述",
        "resume": req.resume_text or "",
        "code": "",
        "position_type": "未知",
        # 时间预算默认值（会被前端传入覆盖）
        "duration_minutes": "30",
        "intro_min": "3",
        "tech_qa_min": "24",
        "coding_min": "0（无编程题）",
        "reverse_min": "3",
        "question_count": "8",
        "avg_time_per_question": "3",
    }

    if req.position_name:
        from services.position_store import PositionStore
        store = PositionStore(db)
        # 带用户上下文查询，避免同名岗位时命中其他用户的岗位
        pos = await store.get(req.position_name, user_id=user.id if user else None)
        if pos:
            kwargs["position_type"] = pos.position_type
            if pos.jds:
                if req.jd_id:
                    matched = [jd for jd in pos.jds if jd.id == req.jd_id]
                    if matched:
                        kwargs["jd"] = "\n\n".join(jd.content for jd in matched)
                else:
                    kwargs["jd"] = "\n\n".join(jd.content for jd in pos.jds)

    # 题库注入：根据 question_bank_ids 从数据库加载题目
    if req.question_bank_ids:
        try:
            from models.db_models import QuestionBankItem
            qb_result = await db.execute(
                select(QuestionBankItem).where(QuestionBankItem.id.in_(req.question_bank_ids))
            )
            items = qb_result.scalars().all()
            if items:
                mode = req.question_bank_mode or "mixed"

                mode_instructions = {
                    "strict": (
                        "【题库模式：严格】你必须且只能从以下题目中逐题提问，每题原文照读，不可修改、不可跳过、不可自编。"
                        "全部题目问完后方可结束问答环节。"
                    ),
                    "mixed": (
                        "【题库模式：混合】以下题目为必考题，你必须全部问到。此外你还可以根据对话情况，"
                        "自行补充少量相关追问或扩展题。必考题优先，自补题不超过2道。"
                    ),
                    "adaptive": (
                        "【题库模式：灵活改编】以下题目作为出题参考。你可以根据候选人背景、回答水平和对话节奏，"
                        "灵活调整题目措辞、难度和顺序，也可基于题目主题自行延伸。但核心考察点不要偏离。"
                    ),
                }
                instruction = mode_instructions.get(mode, mode_instructions["mixed"])

                qb_parts = [instruction]
                for i, item in enumerate(items, 1):
                    qb_parts.append(
                        f"\n题目{i}（{item.difficulty or 'medium'} | {item.category or 'general'}）：{item.title}\n"
                        f"{item.content[:500]}"
                    )
                kwargs["_question_bank_text"] = "\n".join(qb_parts)
                logger.info(f"Question bank loaded: {len(items)} questions, mode={mode}")
        except Exception as e:
            logger.warning(f"Failed to load question bank: {e}")

    # 代码/项目上下文：不再直接注入 prompt（已通过 RAG 向量检索获取）
    # 仅保留简历作为直接上下文

    # 面试时间预算（从请求参数中获取）
    if req.interview_duration_minutes > 0:
        kwargs["duration_minutes"] = str(req.interview_duration_minutes)
        # 计算各环节时间分配
        intro_min = 3
        reverse_min = 3
        coding_min = req.interview_coding_min if req.coding_enabled else 0
        tech_qa_min = max(1, req.interview_duration_minutes - intro_min - reverse_min - coding_min)
        kwargs["intro_min"] = str(intro_min)
        kwargs["reverse_min"] = str(reverse_min)
        kwargs["tech_qa_min"] = str(tech_qa_min)
        kwargs["coding_min"] = f"{coding_min}" if coding_min > 0 else "0（无编程题）"
        kwargs["question_count"] = str(req.interview_question_count) if req.interview_question_count > 0 else "8"
        if req.interview_question_count > 0:
            kwargs["avg_time_per_question"] = str(round(tech_qa_min / req.interview_question_count, 1))
        else:
            kwargs["avg_time_per_question"] = "3"

    return kwargs


# ============ 路由 ============

@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """SSE 流式对话接口（含上下文窗口管理）"""

    async def event_generator():
        messages = [m.model_dump() for m in req.messages]

        # ====== Phase 1: 构建/维护对话上下文 ======
        has_system = any(m["role"] == "system" for m in messages)

        if req.mode:
            if not has_system:
                # 第一轮：构建完整 system 消息（静态部分只注入一次）
                prompt_kwargs = await _build_prompt_kwargs(req, db, user)
                system_content = load_prompt(
                    req.mode,
                    candidate_level=req.candidate_level or "",
                    interview_round=req.interview_round or "",
                    **prompt_kwargs,
                )

                # 追加用户补充说明
                if req.prompt_notes:
                    system_content += "\n\n---\n【用户补充说明】\n" + req.prompt_notes

                # 第一轮也注入动态上下文到 system 消息中
                dynamic_ctx = _build_dynamic_context(req, prompt_kwargs)
                if dynamic_ctx:
                    system_content += "\n\n---\n" + dynamic_ctx

                messages.insert(0, {"role": "system", "content": system_content})
            else:
                # 后续轮次：动态上下文注入到最后一条 user 消息前
                prompt_kwargs = await _build_prompt_kwargs(req, db, user)
                dynamic_ctx = _build_dynamic_context(req, prompt_kwargs)
                if dynamic_ctx:
                    # 找到最后一条 user 消息，在前面追加动态上下文
                    for i in range(len(messages) - 1, -1, -1):
                        if messages[i]["role"] == "user":
                            messages[i]["content"] = (
                                "【参考上下文】\n" + dynamic_ctx + "\n\n---\n【用户消息】\n" + messages[i]["content"]
                            )
                            break

        # ====== Phase 2: Token 窗口裁剪 ======
        max_tokens = settings.MAX_CONTEXT_TOKENS
        system_reserved = settings.SYSTEM_RESERVED_TOKENS

        # 计算 system 消息占用的 token 数
        system_tokens = 0
        for m in messages:
            if m["role"] == "system":
                system_tokens += estimate_tokens(m["content"]) + 4

        # 为对话历史保留的 token 预算
        dialogue_budget = max(max_tokens - system_tokens - system_reserved, 4096)

        # 分离 system 消息和对话消息
        system_msgs = [m for m in messages if m["role"] == "system"]
        dialogue_msgs = [m for m in messages if m["role"] != "system"]

        # 裁剪对话历史（保留最近的消息）
        if dialogue_msgs:
            trimmed_dialogue = trim_messages(dialogue_msgs, max_tokens=dialogue_budget)
        else:
            trimmed_dialogue = []

        # 重新组装：system 消息始终保留在最前
        messages = system_msgs + trimmed_dialogue

        total_tokens = system_tokens + sum(estimate_tokens(m["content"]) + 4 for m in trimmed_dialogue)
        logger.info(
            f"Context: {len(messages)} messages, ~{total_tokens} tokens "
            f"(budget={max_tokens}, system={system_tokens})"
        )

        # ====== Phase 3: 验证 & 流式输出 ======
        model = req.model
        if model and not validate_model(model):
            yield f"data: {json.dumps({'type': 'error', 'content': f'模型 {model} 不可用'}, ensure_ascii=False)}\n\n"
            yield f"data: [DONE]\n\n"
            return

        async for chunk in stream_chat(
            messages=messages,
            model=req.model,
            thinking_enabled=req.thinking_enabled,
            reasoning_effort=req.reasoning_effort,
            api_key=req.api_key,
        ):
            if chunk["type"] == "done":
                yield f"data: [DONE]\n\n"
            elif chunk["type"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'content': chunk['content']}, ensure_ascii=False)}\n\n"
                yield f"data: [DONE]\n\n"
            else:
                yield f"data: {json.dumps({'type': chunk['type'], 'content': chunk['content']}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
