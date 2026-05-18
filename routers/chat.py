"""对话流式路由 — SSE 流式输出 + 模型列表 + LCEL RAG 管线"""

import json
import logging
from typing import Optional

from fastapi import APIRouter
from starlette.responses import StreamingResponse

from config import settings
from models.schemas import ChatRequest, ModelsResponse
from services.llm_client import stream_chat
from services.model_registry import get_available_models, validate_model
from services.agent_tools import search_web
from services.coding_problem import select_problems, format_problems_for_prompt
from services.rag_pipeline import build_rag_context
from utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/models", response_model=ModelsResponse)
async def list_models():
    """返回可用模型列表"""
    return ModelsResponse(models=get_available_models())


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """SSE 流式对话接口"""

    async def event_generator():
        messages = [m.model_dump() for m in req.messages]

        # 自动注入 system 提示（如果 mode 有值且消息列表中没有 system 消息）
        has_system = any(m["role"] == "system" for m in messages)
        if req.mode and not has_system:
            try:
                prompt_kwargs = {}
                # 如果传了 position_name，从岗位管理获取 JD 和岗位类型
                if req.position_name:
                    from services.position_store import PositionStore
                    store = PositionStore()
                    pos = store.get(req.position_name)
                    if pos:
                        prompt_kwargs["position_type"] = pos.position_type
                        if pos.jds:
                            # 按 jd_id 过滤：指定了则只取匹配的 JD，否則用全部
                            if req.jd_id:
                                matched_jds = [jd for jd in pos.jds if jd.id == req.jd_id]
                                if matched_jds:
                                    jd_text = "\n\n".join(jd.content for jd in matched_jds)
                                    prompt_kwargs["jd"] = jd_text
                                else:
                                    prompt_kwargs["jd"] = "暂无岗位描述"
                            else:
                                jd_text = "\n\n".join(jd.content for jd in pos.jds)
                                prompt_kwargs["jd"] = jd_text
                        else:
                            prompt_kwargs["jd"] = "暂无岗位描述"
                    else:
                        prompt_kwargs["jd"] = "暂无岗位描述"

                # 简历文本：两个模式都能看到
                prompt_kwargs["resume"] = req.resume_text or ""

                # 代码上下文：仅面试官模式可见
                if req.mode == "interviewer":
                    prompt_kwargs["code"] = req.code_context or ""
                else:
                    prompt_kwargs["code"] = ""

                # RAG 检索：使用 LCEL 管线（检索 + 格式化一步完成）
                rag_context = ""
                if req.position_name and req.messages:
                    last_user_msg = req.messages[-1].content
                    rag_context = build_rag_context(
                        position_name=req.position_name,
                        query=last_user_msg,
                        top_k=settings.VECTOR_SEARCH_TOP_K,
                    )

                # 联网搜索
                search_context = ""
                if req.use_search and req.messages:
                    try:
                        last_user_msg = req.messages[-1].content
                        search_result = search_web(last_user_msg)
                        if search_result:
                            search_context = "\n\n---\n网络搜索结果：\n" + search_result
                    except Exception as e:
                        logger.warning(f"Web search failed (non-blocking): {e}")

                # 编程题注入（仅求职者模式 + 开关开启 + 技术岗/未知）
                coding_context = ""
                if req.coding_enabled and req.mode == "candidate":
                    try:
                        pos_type = prompt_kwargs.get("position_type", "未知")
                        pos_name = req.position_name or ""
                        # 获取最近的对话内容用于自适应难度
                        conv_history = [m.content for m in req.messages[-10:]]
                        problems = select_problems(
                            position_type=pos_type,
                            position_name=pos_name,
                            conversation_history=conv_history,
                            count=3,
                        )
                        if problems:
                            coding_context = format_problems_for_prompt(problems)
                    except Exception as e:
                        logger.warning(f"Coding problem selection failed (non-blocking): {e}")

                system_content = load_prompt(req.mode, **prompt_kwargs)
                if rag_context:
                    system_content += rag_context
                if search_context:
                    system_content += search_context
                if coding_context:
                    system_content += coding_context

                messages.insert(0, {"role": "system", "content": system_content})
            except FileNotFoundError:
                pass  # 模板文件不存在时跳过自动注入

        # 验证 model 参数
        model = req.model
        if model and not validate_model(model):
            yield f"data: {json.dumps({'type': 'error', 'content': f'模型 {model} 不可用'}, ensure_ascii=False)}\n\n"
            yield f"data: [DONE]\n\n"
            return

        # 流式输出
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
