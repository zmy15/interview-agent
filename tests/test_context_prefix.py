"""上下文结构 / 前缀缓存测试

锁定的约定（改动上下文组装前请先看 utils/prompt_loader.py 的模块说明）：

    系统指令 → 简历 → 岗位JD →（历史问答）→ 本轮尾部动态内容(RAG/搜索/编程题)

也就是：
1. 静态指令必须排在简历/JD 之前 —— 跨会话可复用的前缀才够长；
2. system 在同一场面试里必须逐字节不变 —— 服务端前缀缓存才有得命中；
3. RAG 等每轮变化的內容只能落在**最后一条 user 消息的末尾** ——
   放在中间会让它之后的全部 KV 失效。
"""

import asyncio
import types

import pytest

from models.schemas import ChatRequest
from utils.prompt_loader import build_prompt_notes_text, build_question_bank_text, load_prompt

POSITION = "上下文测试岗"
JD_TEXT = "【测试JD】需要精通 Python 与 FastAPI"
RESUME_TEXT = "【测试简历】五年后端经验"
RAG_SENTINEL = "【RAG哨兵】知识库检索到的独有片段"


@pytest.fixture
def position(client):
    """建一个带 JD 的岗位，供 chat 请求触发 RAG 分支"""
    client.delete(f"/positions/{POSITION}")
    client.post("/positions", json={"name": POSITION, "description": "上下文结构测试"})
    client.post(f"/positions/{POSITION}/jds", json={"content": JD_TEXT})
    yield POSITION
    client.delete(f"/positions/{POSITION}")


def _capture_chat(client, monkeypatch, payload, rag_text=None, calls=None, rag_counter=None,
                  collect_events=False):
    """发一次 /chat/stream，并把真正交给模型的 messages 抓出来。

    patching 的是 routers.chat 里的名字（路由用 from ... import stream_chat 引入），
    并同时把 RAG 检索替换成固定哨兵值，避免依赖真实的向量库。

    collect_events=True 时额外返回解析后的 SSE 事件列表（用于检查 system_prefix）。
    """
    import json as _json

    import routers.chat as chat

    captured = []
    events = []
    if calls is None:
        calls = []

    async def fake_stream_chat(messages, **kwargs):
        captured.append(messages)
        calls.append(kwargs)
        yield {"type": "content", "content": "ok"}
        yield {"type": "done", "content": ""}

    monkeypatch.setattr(chat, "stream_chat", fake_stream_chat)

    if rag_text is not None:
        # 每次检索返回不同内容（可用 rag_counter 跨多次请求共享计数），
        # 用来验证「尾部怎么变都不影响前缀」。
        counter = rag_counter if rag_counter is not None else {"n": 0}

        def fake_rag(position_name, query, top_k=None):
            counter["n"] += 1
            return f"{rag_text} #{counter['n']}"

        monkeypatch.setattr(chat, "build_rag_context", fake_rag)

    with client.stream("POST", "/chat/stream", json=payload) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if collect_events and text.startswith("data: ") and text[6:].strip() != "[DONE]":
                try:
                    events.append(_json.loads(text[6:]))
                except ValueError:
                    pass

    assert captured, "stream_chat 没有被调用"
    if collect_events:
        return captured, calls, events
    return captured, calls


class TestTemplateLayout:
    """模板布局：静态指令在前，简历/JD 在后"""

    def test_interviewer_instructions_come_first(self):
        system = load_prompt(
            "interviewer",
            jd=JD_TEXT,
            resume=RESUME_TEXT,
        )
        i_instr = system.index("角色要求")
        i_resume = system.index("【测试简历】")
        i_jd = system.index("【测试JD】")

        assert i_instr < i_resume, "静态指令必须排在简历之前"
        assert i_resume < i_jd, "按约定顺序：简历在 JD 之前"

    def test_candidate_instructions_come_first(self):
        system = load_prompt(
            "candidate",
            jd=JD_TEXT,
            resume=RESUME_TEXT,
        )
        assert system.index("面试流程") < system.index("【测试简历】") < system.index("【测试JD】")

    def test_cross_session_prefix_is_shareable(self):
        """两份不同简历/JD 的 system，开头应共享同一段静态指令"""
        a = load_prompt("interviewer", jd="JD-A", resume="简历A", candidate_level="intern")
        b = load_prompt("interviewer", jd="JD-B", resume="简历B", candidate_level="experienced")

        shared = 0
        for ca, cb in zip(a, b):
            if ca != cb:
                break
            shared += 1
        # 至少共享「角色要求」整段（数百字符），否则缓存前缀太短没有意义
        assert shared > 300, f"跨会话共享前缀只有 {shared} 字符"
        assert "简历A" not in a[:shared]

    def test_empty_slots_render_stable_placeholder(self):
        """空简历/空 JD 用固定占位符，避免出现悬空标题"""
        system = load_prompt("interviewer")
        assert "候选人简历：\n（无）" in system
        assert "相关代码：\n（无）" in system
        # JD 的兜底文案沿用历史行为（"暂无岗位描述"），同样必须稳定
        assert "岗位描述：\n暂无岗位描述" in system
        assert load_prompt("interviewer") == load_prompt("interviewer")

    def test_prompt_notes_block(self):
        assert build_prompt_notes_text(None) == ""
        assert build_prompt_notes_text("  ") == ""
        assert build_prompt_notes_text("多问算法") == "【用户补充说明】\n多问算法"

    def test_question_bank_block_is_deterministic(self):
        items = [
            types.SimpleNamespace(id="b", title="题B", content="内容B", difficulty="hard", category="algo"),
            types.SimpleNamespace(id="a", title="题A", content="内容A", difficulty="easy", category="base"),
        ]
        first = build_question_bank_text(items, "strict")
        second = build_question_bank_text(items, "strict")
        assert first == second
        assert "严格" in first and "题B" in first


class TestStableSystemAcrossTurns:
    """同一场面试：system 逐字节不变，问答只在尾部增长"""

    def test_system_identical_across_turns(self, client, monkeypatch, position):
        payload = {
            "messages": [{"role": "user", "content": "请开始面试"}],
            "mode": "candidate",
            "position_name": position,
            "resume_text": RESUME_TEXT,
        }
        first, _ = _capture_chat(client, monkeypatch, payload)

        payload2 = {
            **payload,
            "messages": [
                {"role": "user", "content": "请开始面试"},
                {"role": "assistant", "content": "你好，请自我介绍"},
                {"role": "user", "content": "我是张三"},
            ],
        }
        second, _ = _capture_chat(client, monkeypatch, payload2)

        sys1 = first[0][0]
        sys2 = second[0][0]
        assert sys1["role"] == "system" and sys2["role"] == "system"
        assert sys1["content"] == sys2["content"], "同一场面试的 system 必须逐字节一致"

        # 前缀（system + 已有问答）在第二轮里原样保留
        assert second[0][:3] == first[0][:1] + payload2["messages"][:2]

    def test_second_turn_hits_prefix_cache(self, client, monkeypatch, position):
        """第二轮应命中进程内前缀缓存，不再重建 system"""
        from services import prefix_cache

        prefix_cache.clear()

        payload = {
            "messages": [{"role": "user", "content": "请开始面试"}],
            "mode": "interviewer",
            "position_name": position,
            "resume_text": RESUME_TEXT,
        }
        _capture_chat(client, monkeypatch, payload)
        after_first = prefix_cache.stats()
        assert after_first["entries"] >= 1, "第一轮就该把稳定前缀写入缓存"

        _capture_chat(client, monkeypatch, {**payload, "messages": payload["messages"] + [
            {"role": "assistant", "content": "回答"},
            {"role": "user", "content": "继续"},
        ]})
        assert prefix_cache.stats()["entries"] == after_first["entries"], "第二轮不应重复建缓存"

    def test_different_session_builds_new_prefix(self, client, monkeypatch, position):
        """换了简历 = 换了一场面试：前缀必须重建（否则提示词与界面脱节）"""
        from services import prefix_cache

        prefix_cache.clear()
        base = {
            "messages": [{"role": "user", "content": "开始"}],
            "mode": "interviewer",
            "position_name": position,
        }
        first, _ = _capture_chat(client, monkeypatch, {**base, "resume_text": "简历甲"})
        second, _ = _capture_chat(client, monkeypatch, {**base, "resume_text": "简历乙"})

        assert first[0][0]["content"] != second[0][0]["content"]
        assert "简历甲" in first[0][0]["content"]
        assert "简历乙" in second[0][0]["content"]


class TestDynamicContextGoesToTail:
    """每轮变化的内容只能落在最后一条 user 消息末尾"""

    def test_rag_not_in_system_but_in_last_user_message(self, client, monkeypatch, position):
        payload = {
            "messages": [{"role": "user", "content": "请开始面试"}],
            "mode": "candidate",
            "position_name": position,
        }
        captured, _ = _capture_chat(client, monkeypatch, payload, rag_text=RAG_SENTINEL)
        messages = captured[0]

        system = messages[0]
        assert system["role"] == "system"
        assert RAG_SENTINEL not in system["content"], "RAG 不能进 system，否则整条前缀失效"

        last = messages[-1]
        assert last["role"] == "user"
        assert RAG_SENTINEL in last["content"], "RAG 应该追加到最后一条 user 消息"
        # 原问题必须保留在动态内容之前
        assert last["content"].startswith("请开始面试")

    def test_tail_change_keeps_prefix_stable(self, client, monkeypatch, position):
        """RAG 每轮取到不同片段时，前缀仍要逐字节相同"""
        base = {
            "messages": [{"role": "user", "content": "第一个问题"}],
            "mode": "candidate",
            "position_name": position,
        }
        # 两次请求共用一个计数器，让第二轮确实检索到不同的片段
        counter = {"n": 0}
        first, _ = _capture_chat(
            client, monkeypatch, base, rag_text=RAG_SENTINEL, rag_counter=counter
        )
        second, _ = _capture_chat(
            client,
            monkeypatch,
            {
                **base,
                "messages": base["messages"] + [
                    {"role": "assistant", "content": "回答一"},
                    {"role": "user", "content": "第二个问题"},
                ],
            },
            rag_text=RAG_SENTINEL,
            rag_counter=counter,
        )

        assert first[0][0]["content"] == second[0][0]["content"]
        # 两轮的检索片段确实不同（否则这个用例证明不了什么）
        assert first[0][-1]["content"] != second[0][-1]["content"]
        assert "#1" in first[0][-1]["content"] and "#2" in second[0][-1]["content"]

    def test_history_untouched_by_dynamic_injection(self, client, monkeypatch, position):
        """动态内容只动最后一条 user 消息，历史消息原样透传"""
        payload = {
            "messages": [
                {"role": "user", "content": "第一个问题"},
                {"role": "assistant", "content": "第一个回答"},
                {"role": "user", "content": "第二个问题"},
            ],
            "mode": "candidate",
            "position_name": position,
        }
        captured, _ = _capture_chat(client, monkeypatch, payload, rag_text=RAG_SENTINEL)
        messages = captured[0]

        assert messages[1] == {"role": "user", "content": "第一个问题"}
        assert messages[2] == {"role": "assistant", "content": "第一个回答"}
        assert messages[3]["content"].startswith("第二个问题")


class TestClientReplay:
    """前端回传稳定前缀时的行为（SSE system_prefix 事件 + 采信判定）"""

    def test_prefix_event_sent_on_first_turn_and_reused_after(self, client, monkeypatch, position):
        """首轮下发前缀；前端回传后应被采信（不再重复下发）"""
        from services import prefix_cache

        prefix_cache.clear()

        base = {
            "mode": "interviewer",
            "position_name": position,
            "resume_text": RESUME_TEXT,
        }

        # --- 第 1 轮：前端手上没有前缀 → 后端构建并通过事件下发 ---
        first, _, events = _capture_chat(
            client,
            monkeypatch,
            {**base, "messages": [{"role": "user", "content": "开始"}]},
            collect_events=True,
        )
        prefix_events = [e for e in events if e.get("type") == "system_prefix"]
        assert len(prefix_events) == 1, "首轮应下发一次稳定前缀"
        canonical = prefix_events[0]["content"]
        assert canonical == first[0][0]["content"]
        assert prefix_events[0]["fingerprint"]

        # --- 第 2 轮：前端把它放在 messages[0] 原样回传 ---
        second, _, events2 = _capture_chat(
            client,
            monkeypatch,
            {
                **base,
                "messages": [
                    {"role": "system", "content": canonical},
                    {"role": "user", "content": "开始"},
                    {"role": "assistant", "content": "请自我介绍"},
                    {"role": "user", "content": "我是张三"},
                ],
            },
            collect_events=True,
        )
        assert second[0][0]["content"] == canonical, "采信的必须是逐字节相同的那份"
        assert not [e for e in events2 if e.get("type") == "system_prefix"], \
            "前端已持有且一致时不必重复下发"

    def test_stale_client_prefix_is_replaced(self, client, monkeypatch, position):
        """前端拿的是旧简历的前缀：必须被权威版本覆盖，并重新下发正确的"""
        from services import prefix_cache

        prefix_cache.clear()

        _, _, events = _capture_chat(
            client,
            monkeypatch,
            {
                "messages": [{"role": "user", "content": "开始"}],
                "mode": "interviewer",
                "position_name": position,
                "resume_text": "旧简历",
            },
            collect_events=True,
        )
        stale = next(e["content"] for e in events if e.get("type") == "system_prefix")

        # 简历换了，但前端仍回传旧前缀
        captured, _, events2 = _capture_chat(
            client,
            monkeypatch,
            {
                "messages": [
                    {"role": "system", "content": stale},
                    {"role": "user", "content": "开始"},
                ],
                "mode": "interviewer",
                "position_name": position,
                "resume_text": "新简历",
            },
            collect_events=True,
        )

        system_content = captured[0][0]["content"]
        assert system_content != stale, "旧前缀不能继续被采信"
        assert "新简历" in system_content
        refreshed = [e for e in events2 if e.get("type") == "system_prefix"]
        assert refreshed, "覆盖后应把正确的前缀重新下发给前端"
        assert refreshed[0]["content"] == system_content

    def test_no_prefix_event_without_mode(self, client, monkeypatch):
        """不带 mode 的普通对话不受影响：不下发前缀、也不注入 system"""
        captured, _, events = _capture_chat(
            client,
            monkeypatch,
            {"messages": [{"role": "user", "content": "你好"}]},
            collect_events=True,
        )
        assert all(m["role"] != "system" for m in captured[0])
        assert not [e for e in events if e.get("type") == "system_prefix"]

    def test_matching_client_prefix_skips_resend_after_cache_loss(self, client, monkeypatch, position):
        """后端缓存丢了（如刚重启）但前端那份仍然正确时，不应重复下发前缀"""
        from services import prefix_cache

        prefix_cache.clear()
        _, _, events = _capture_chat(
            client,
            monkeypatch,
            {
                "messages": [{"role": "user", "content": "开始"}],
                "mode": "interviewer",
                "position_name": position,
                "resume_text": RESUME_TEXT,
            },
            collect_events=True,
        )
        canonical = next(e["content"] for e in events if e.get("type") == "system_prefix")

        # 模拟后端重启：清空进程内缓存，前端照旧回传那份正确的 system
        prefix_cache.clear()
        captured, _, events2 = _capture_chat(
            client,
            monkeypatch,
            {
                "messages": [
                    {"role": "system", "content": canonical},
                    {"role": "user", "content": "开始"},
                ],
                "mode": "interviewer",
                "position_name": position,
                "resume_text": RESUME_TEXT,
            },
            collect_events=True,
        )

        assert captured[0][0]["content"] == canonical
        assert not [e for e in events2 if e.get("type") == "system_prefix"], \
            "内容一致就没必要再传一遍"


class TestUsageObservability:
    """LLM 用量/前缀缓存命中率的可观测性"""

    def test_stream_chat_requests_usage(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        import services.llm_client as llm

        chunk = MagicMock()
        chunk.choices = []
        chunk.usage = types.SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=10,
            prompt_cache_hit_tokens=900,
            prompt_cache_miss_tokens=100,
        )

        stream = MagicMock()
        stream.__aiter__.return_value = [chunk]

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=stream)

        async def _run():
            events = []
            async for event in llm.stream_chat([{"role": "user", "content": "hi"}]):
                events.append(event)
            return events

        with patch.object(llm, "get_client", return_value=mock_client):
            asyncio.run(_run())

        kwargs = mock_client.chat.completions.create.call_args[1]
        assert kwargs["stream_options"] == {"include_usage": True}, \
            "必须显式要求 usage，否则观测不到前缀缓存命中"

    def test_usage_log_reports_cache_hit_rate(self, caplog):
        """usage 日志要同时给出命中量与命中率，便于直接判断前缀是否被复用"""
        import logging

        from services.llm_client import _log_cache_usage

        usage = types.SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=20,
            prompt_cache_hit_tokens=900,
            prompt_cache_miss_tokens=100,
        )
        with caplog.at_level(logging.INFO, logger="services.llm_client"):
            _log_cache_usage(usage, "deepseek-flash", "candidate:abcd1234")

        text = caplog.text
        assert "cache_hit=900" in text
        assert "cache_miss=100" in text
        assert "cache_hit_rate=90.0%" in text

    def test_usage_log_falls_back_to_prompt_tokens_details(self, caplog):
        """部分响应把命中量放在 prompt_tokens_details.cached_tokens 里"""
        import logging

        from services.llm_client import _log_cache_usage

        usage = types.SimpleNamespace(
            prompt_tokens=1000,
            completion_tokens=20,
            prompt_tokens_details=types.SimpleNamespace(cached_tokens=750),
            prompt_cache_miss_tokens=250,
        )
        with caplog.at_level(logging.INFO, logger="services.llm_client"):
            _log_cache_usage(usage, "deepseek-flash", "candidate:abcd1234")

        assert "cache_hit=750" in caplog.text
        assert "cache_hit_rate=75.0%" in caplog.text

    def test_usage_log_without_usage_is_harmless(self, caplog):
        """拿不到 usage 时只记一行提示，不能抛异常（否则整个 SSE 流会断）"""
        import logging

        from services.llm_client import _log_cache_usage

        with caplog.at_level(logging.INFO, logger="services.llm_client"):
            _log_cache_usage(None, "deepseek-flash", "chat:abcd1234")

        assert "usage unavailable" in caplog.text


class TestFingerprintParts:
    """指纹只覆盖整场不变的字段"""

    def test_rag_related_switches_do_not_affect_prefix_signature(self):
        """联网搜索开关不属于前缀（它落在尾部），改它不该让前缀作废"""
        from routers.chat import _fingerprint_parts
        from services import prefix_cache

        base = ChatRequest(messages=[{"role": "user", "content": "hi"}], mode="candidate")
        with_search = base.model_copy(update={"use_search": True})

        assert prefix_cache.signature(_fingerprint_parts(base, None)) == \
            prefix_cache.signature(_fingerprint_parts(with_search, None))

    def test_session_fields_do_affect_prefix_signature(self):
        from routers.chat import _fingerprint_parts
        from services import prefix_cache

        base = ChatRequest(messages=[{"role": "user", "content": "hi"}], mode="candidate")
        changed = base.model_copy(update={"resume_text": "新简历"})

        assert prefix_cache.signature(_fingerprint_parts(base, None)) != \
            prefix_cache.signature(_fingerprint_parts(changed, None))

    def test_question_bank_order_does_not_change_signature(self):
        """题库 id 顺序不同不该算两场面试（后端会按请求顺序排序渲染）"""
        from routers.chat import _fingerprint_parts
        from services import prefix_cache

        a = ChatRequest(
            messages=[{"role": "user", "content": "hi"}],
            mode="candidate",
            question_bank_ids=["x", "y"],
        )
        b = a.model_copy(update={"question_bank_ids": ["y", "x"]})
        assert prefix_cache.signature(_fingerprint_parts(a, None)) == \
            prefix_cache.signature(_fingerprint_parts(b, None))
