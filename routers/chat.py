"""对话流式路由 — SSE 流式输出 + 模型列表 + LCEL RAG 管线 + 上下文窗口管理

上下文结构（**前缀缓存友好，改动前请先读 utils/prompt_loader.py 的模块说明**）：

    稳定前缀（整场面试逐字节不变 → 服务端前缀缓存据此复用 KV）
        system: 静态指令 → 经验级别 → 轮次 → 岗位类型 → 简历 → JD
                → 题库/补充说明 →（求职者模式）时间预算
    历史问答（每轮只在尾部追加，前缀不受影响）
        user / assistant 交替……
    本轮尾部动态内容（放这里只会让缓存 miss 这一小段）
        RAG 检索 / 联网搜索 / 编程题，追加到最后一条 user 消息末尾

system 只构建一次：优先复用请求里已有的 system 消息，其次命中进程内稳定前缀
缓存，最后才现算并写入缓存。
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from config import settings
from database import get_db
from models.schemas import ChatRequest, ModelsResponse
from services import api_key_store, prefix_cache
from services.agent_tools import search_web
from services.api_key_store import resolve_api_key
from services.coding_problem import format_problems_for_prompt, select_problems
from services.llm_client import stream_chat
from services.model_registry import get_available_models, invalidate_cache, validate_model
from services.rag_pipeline import build_rag_context
from utils.auth import CurrentUser, get_optional_user
from utils.context_manager import estimate_tokens, trim_messages
from utils.prompt_loader import (
    build_prompt_notes_text,
    build_question_bank_text,
    is_stable_prefix_template,
    load_prompt,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _effective_api_key(
    request: Request,
    explicit: Optional[str] = None,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """[已废弃，保留以兼容旧调用] 统一 API Key 来源

    新代码请用 ``services.api_key_store.resolve_api_key``：它在请求头之外
    还会回落到数据库里加密保存的 Key。
    """
    key = api_key_store.effective_api_key_from_request(request, explicit=explicit)
    if key:
        return key
    if fallback and fallback.strip():
        return fallback.strip()
    return None


@router.get("/models", response_model=ModelsResponse)
async def list_models(
    request: Request,
    refresh: bool = False,
    user: Optional[CurrentUser] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """返回可用模型列表。

    模型列表来自官方 `GET /models` 接口
    （https://api-docs.deepseek.com/zh-cn/api/list-models），
    因此新增 / 改名模型无需改代码。

    - refresh=true 强制绕过缓存重新拉取
    - API Key 取 `X-DEEPSEEK-API-KEY` 请求头（前端自动带上），
      没有则回落到数据库里加密保存的 Key，最后才回退 .env 的 DEEPSEEK_API_KEY
    - 远端不可用时回退到 .env 的 AVAILABLE_MODELS，并在 source 字段说明
    """
    if refresh:
        invalidate_cache()

    models = await get_available_models(
        api_key=await resolve_api_key(request, db, user)
    )
    source = (
        "fallback"
        if models and all("本地配置" in m.description for m in models)
        else "remote"
    )
    return ModelsResponse(models=models, source=source)


# ============ 辅助函数 ============

def _fingerprint_parts(req: ChatRequest, user: Optional[CurrentUser]) -> dict:
    """收集「整场面试期间不变」的字段，用于计算稳定前缀指纹。

    这里刻意**不含** RAG / 编程题 / 联网搜索 —— 它们每轮都可能变化，
    已经被移到尾部，不该影响 system 的复用判断。
    """
    return {
        "v": 1,  # 结构版本号：模板布局或字段含义变更时递增，避免旧指纹误命中
        "mode": req.mode,
        "position_name": req.position_name,
        "jd_id": req.jd_id,
        "resume_text": req.resume_text or "",
        "code_context": req.code_context or "",
        "candidate_level": req.candidate_level or "",
        "interview_round": req.interview_round or "",
        "prompt_notes": req.prompt_notes or "",
        "duration_minutes": req.interview_duration_minutes,
        "question_count": req.interview_question_count,
        "coding_min": req.interview_coding_min,
        "coding_enabled": req.coding_enabled,
        "question_bank_ids": sorted(req.question_bank_ids or []),
        "question_bank_mode": req.question_bank_mode or "mixed",
        "user_id": user.id if user else None,
    }


async def _resolve_position_type(
    req: ChatRequest,
    db: AsyncSession,
    user: Optional[CurrentUser],
) -> str:
    """查岗位类型（只在需要出编程题时调用，命中缓存时不必付这次查询）"""
    if not req.position_name:
        return "未知"
    try:
        from services.position_store import PositionStore
        pos = await PositionStore(db).get(
            req.position_name, user_id=user.id if user else None
        )
        return pos.position_type if pos else "未知"
    except Exception as e:  # noqa: BLE001 - 仅用于出题选型，失败不该影响对话
        logger.warning("Resolve position type failed (non-blocking): %s", e)
        return "未知"


async def _build_dynamic_context(
    req: ChatRequest,
    db: AsyncSession,
    user: Optional[CurrentUser],
) -> str:
    """构建每轮动态上下文（RAG + 搜索 + 编程题）。

    这些内容**必须**追加到最后一条 user 消息的尾部，不能放进 system：
    它们每轮都变，一旦落在前缀里，服务端缓存的 KV 会从该位置起全部失效。
    题库不在此列 —— 它在整场面试里不变，已随 system 一起构建并缓存。
    """
    parts = []

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
            logger.info(
                "RAG context injected | position=%s | length=%d chars",
                req.position_name, len(rag_context),
            )
        else:
            logger.info(
                "RAG context empty | position=%s — no knowledge base data",
                req.position_name,
            )

    # 联网搜索
    if req.use_search and req.messages:
        try:
            last_user_msg = req.messages[-1].content
            search_result = search_web(last_user_msg)
            if search_result:
                parts.append("网络搜索结果：\n" + search_result)
        except Exception as e:
            logger.warning(f"Web search failed (non-blocking): {e}")

    # 编程题（仅求职者模式 + 技术岗）。
    # 选题依赖当前对话，因此结果每轮都可能不同 —— 属于尾部内容。
    if req.coding_enabled and req.mode == "candidate":
        try:
            pos_type = await _resolve_position_type(req, db, user)
            problems = select_problems(
                position_type=pos_type,
                position_name=req.position_name or "",
                conversation_history=[m.content for m in req.messages[-10:]],
                count=3,
            )
            if problems:
                parts.append(format_problems_for_prompt(problems))
        except Exception as e:
            logger.warning(f"Coding problem selection failed (non-blocking): {e}")

    return "\n\n---\n".join(parts) if parts else ""


async def _build_prompt_kwargs(req: ChatRequest, db: AsyncSession, user: Optional[CurrentUser] = None) -> dict:
    """构建静态 prompt 参数（JD / 简历 / 岗位类型 / 代码 / 时间预算 / 题库）

    这里的所有输入在整场面试里都不变，因此产出的文本可以安全地作为
    稳定前缀的一部分长期复用。
    """
    kwargs: dict = {
        "jd": "暂无岗位描述",
        "resume": req.resume_text or "",
        "code": "",
        "position_type": "未知",
        "question_bank_text": "",
        "prompt_notes": build_prompt_notes_text(req.prompt_notes),
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

    # 题库注入：根据 question_bank_ids 从数据库加载题目。
    # 题目在整场面试里固定不变，所以随 system 一起进稳定前缀（第二次请求起命中缓存）。
    if req.question_bank_ids:
        try:
            from models.db_models import QuestionBankItem
            qb_result = await db.execute(
                select(QuestionBankItem).where(QuestionBankItem.id.in_(req.question_bank_ids))
            )
            # 按请求里的顺序排好：SQL 不保证 IN 的顺序，不排的话
            # 同一场面试两次构建可能得到不同文本 → 前缀缓存直接失效。
            order = {qid: i for i, qid in enumerate(req.question_bank_ids)}
            items = sorted(
                qb_result.scalars().all(),
                key=lambda it: order.get(it.id, 1 << 30),
            )
            if items:
                kwargs["question_bank_text"] = build_question_bank_text(
                    items, req.question_bank_mode or "mixed"
                )
                logger.info(
                    "Question bank loaded | %d questions | mode=%s",
                    len(items), req.question_bank_mode or "mixed",
                )
        except Exception as e:
            logger.warning(f"Failed to load question bank: {e}")

    # 代码/项目上下文：不再直接注入 prompt（已通过 RAG 向量检索获取）
    # 仅保留简历作为直接上下文

    # 面试时间预算（从请求参数中获取）。它同样整场不变，属于稳定前缀。
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


async def _build_stable_system(
    req: ChatRequest,
    db: AsyncSession,
    user: Optional[CurrentUser],
    fingerprint: str,
) -> str:
    """构建权威的稳定前缀 system 消息（不查缓存，调用方负责读写缓存）"""
    prompt_kwargs = await _build_prompt_kwargs(req, db, user)
    return load_prompt(
        req.mode,
        candidate_level=req.candidate_level or "",
        interview_round=req.interview_round or "",
        **prompt_kwargs,
    )


# ============ 路由 ============

@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Optional[CurrentUser] = Depends(get_optional_user),
):
    """SSE 流式对话接口（含上下文窗口管理）"""

    # 在进入生成器之前先解出本次要用的 Key：
    # resolve_api_key 需要读数据库，放在这里可以确保它在请求作用域内完成
    # （生成器里 db 仍然可用，但提前取好更直观，也便于 validate_model 复用）。
    effective_key = await resolve_api_key(request, db, user, explicit=req.api_key)

    # 稳定前缀指纹：只由「整场面试期间不变」的请求字段决定，**不接受前端传入**。
    # 前端若能左右它，就等于把提示词一致性的判断交给了外部输入；
    # 而后端自己算出来的值与请求字段一一对应，永远等价于「同一场面试」。
    fingerprint = prefix_cache.signature(_fingerprint_parts(req, user))

    async def event_generator():
        messages = [m.model_dump() for m in req.messages]

        # ====== Phase 1: 稳定前缀（prompt + 简历 + JD），整场只构建一次 ======
        system_msgs = [m for m in messages if m.get("role") == "system"]
        dialogue_msgs = [m for m in messages if m.get("role") != "system"]

        prefix_source = "none"
        if req.mode and is_stable_prefix_template(req.mode):
            # 前端若回传了 system 消息，先取出它的正文；但**不直接采信** ——
            # 采信外部输入会让「前缀是否一致」由前端决定，一旦它拿着旧简历/
            # 旧 JD 的 system 继续发请求，提示词就与界面设置悄悄脱节了。
            supplied = system_msgs[0]["content"] if system_msgs else None

            canonical = prefix_cache.get(fingerprint)
            if canonical is None:
                # 未命中缓存：按请求字段重建权威前缀并缓存。
                # 注意此时前端那份**仍可能是对的**（例如后端刚重启、缓存丢了），
                # 所以下面统一做一次比对再决定要不要下发。
                canonical = await _build_stable_system(req, db, user, fingerprint)
                prefix_cache.put(fingerprint, canonical)
                rebuilt = True
            else:
                rebuilt = False

            if supplied is not None and supplied == canonical:
                # 前端给的和权威前缀逐字节相同 —— 最理想的情况：不必下发，
                # 服务端前缀缓存整段命中，本轮只新增尾部的问答。
                prefix_source = "client"
            elif supplied is None:
                prefix_source = "build" if rebuilt else "cache"
            else:
                # 前端那份与当前字段不符（如刚改了简历/JD）：用权威前缀覆盖，
                # 宁可让缓存失效一次，也不能让提示词悄悄走样。
                prefix_source = "rebuild(client-stale)"

            system_msgs = [{"role": "system", "content": canonical}]

            # 把权威前缀交给前端保存（仅在前端还没持有、或它那份已经过期时才发）。
            # 前端在后续轮次原样回传，后端就能比对通过、省掉一次重建；
            # 而**是否采信**仍由后端按逐字节比对决定，所以发过去是安全的。
            #
            # 这里刻意不进消息体：它不是对话内容，不影响会话列表与报告；
            # 走 SSE 的独立事件，前端收到后只做本地保存。
            if prefix_source != "client":
                yield "data: " + json.dumps(
                    {
                        "type": "system_prefix",
                        "content": canonical,
                        "fingerprint": fingerprint,
                    },
                    ensure_ascii=False,
                ) + "\n\n"

        # ====== Phase 2: 本轮尾部动态内容（RAG / 搜索 / 编程题）======
        # 只追加到最后一条 user 消息**末尾**：它前面的「system + 历史问答」
        # 完全不受影响，服务端缓存只需为这一小段重新 prefill。
        if req.mode:
            dynamic_ctx = await _build_dynamic_context(req, db, user)
            if dynamic_ctx:
                for i in range(len(dialogue_msgs) - 1, -1, -1):
                    if dialogue_msgs[i].get("role") == "user":
                        dialogue_msgs[i] = {
                            **dialogue_msgs[i],
                            "content": (
                                dialogue_msgs[i]["content"]
                                + "\n\n---\n【参考上下文】\n"
                                + dynamic_ctx
                            ),
                        }
                        break
                logger.info("Dynamic context appended to tail | %d chars", len(dynamic_ctx))

        # ====== Phase 3: Token 窗口裁剪 ======
        # 只裁对话部分：system 是稳定前缀，原样透传（裁它会让前缀变短、缓存失效）。
        max_tokens = settings.MAX_CONTEXT_TOKENS
        system_reserved = settings.SYSTEM_RESERVED_TOKENS

        system_tokens = sum(estimate_tokens(m["content"]) + 4 for m in system_msgs)
        dialogue_budget = max(max_tokens - system_tokens - system_reserved, 4096)

        trimmed_dialogue = (
            trim_messages(dialogue_msgs, max_tokens=dialogue_budget)
            if dialogue_msgs
            else []
        )

        messages = system_msgs + trimmed_dialogue

        total_tokens = system_tokens + sum(
            estimate_tokens(m["content"]) + 4 for m in trimmed_dialogue
        )
        logger.info(
            f"Context: {len(messages)} messages, ~{total_tokens} tokens "
            f"(budget={max_tokens}, system={system_tokens}, prefix={prefix_source}, fp={fingerprint[:12]})"
        )

        # ====== Phase 4: 验证 & 流式输出 ======
        model = req.model
        if model and not await validate_model(model, api_key=effective_key):
            yield f"data: {json.dumps({'type': 'error', 'content': f'模型 {model} 不可用'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return

        async for chunk in stream_chat(
            messages=messages,
            model=req.model,
            thinking_enabled=req.thinking_enabled,
            reasoning_effort=req.reasoning_effort,
            api_key=effective_key,
            cache_label=f"{req.mode or 'chat'}:{fingerprint[:12]}",
        ):
            if chunk["type"] == "done":
                yield "data: [DONE]\n\n"
            elif chunk["type"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'content': chunk['content']}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
            else:
                yield f"data: {json.dumps({'type': chunk['type'], 'content': chunk['content']}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            # 把稳定前缀指纹回给调用方，便于把日志里的 fp 与某一场面试对应起来。
            # 注意别和 DeepSeek 响应里的 system_fingerprint 混淆：那个指后端配置版本，
            # 这个指我们这条「prompt + 简历 + JD」前缀的身份。
            "X-Prefix-Fingerprint": fingerprint,
        },
    )
