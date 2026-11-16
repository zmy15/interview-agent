"""提示词附加文档 — 文档块渲染 / 上传解析 / 在 messages 中的位置

需求：允许用户上传一份文档（txt/md 等）直接进提示词，
位置在**系统提示词之后、对话循环之前**。
"""

import json

from utils.prompt_loader import build_prompt_documents_text, truncate_document_text

# ============ 文档块渲染 ============

class TestBuildDocumentsText:
    def test_empty_documents_render_nothing(self):
        assert build_prompt_documents_text(None) == ""
        assert build_prompt_documents_text([]) == ""
        # 只有空白正文的文档视为空
        assert build_prompt_documents_text([{"name": "a.md", "text": "   \n "}]) == ""

    def test_renders_in_order_with_names(self):
        text = build_prompt_documents_text([
            {"name": "personal.md", "text": "我叫张三，5 年 Python 经验"},
            {"name": "project.md", "text": "项目：面试 Agent"},
        ])

        assert text.startswith("【附加资料】")
        assert "文档 1/2：personal.md" in text
        assert "文档 2/2：project.md" in text
        # 顺序必须稳定（同输入逐字节一致，前缀缓存才不会失效）
        assert text.index("我叫张三") < text.index("项目：面试 Agent")

    def test_missing_name_gets_default(self):
        text = build_prompt_documents_text([{"text": "内容"}])
        assert "：文档1）" in text

    def test_is_byte_stable(self):
        docs = [{"name": "a.md", "text": "同样的输入"}]
        assert build_prompt_documents_text(docs) == build_prompt_documents_text(docs)

    def test_single_document_truncated(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "PROMPT_DOC_MAX_CHARS", 5)

        text = build_prompt_documents_text([{"name": "long.md", "text": "0123456789"}])
        assert "01234" in text
        assert "56789" not in text
        assert "已截断" in text

    def test_total_length_capped(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "PROMPT_DOC_MAX_CHARS", 1000)
        monkeypatch.setattr(settings, "PROMPT_DOC_MAX_TOTAL_CHARS", 120)

        text = build_prompt_documents_text([
            {"name": "a.md", "text": "A" * 100},
            {"name": "b.md", "text": "B" * 100},
        ])

        assert "A" * 100 in text
        # 第二份放不下，应提示被略过而不是整段拼进去
        assert "B" * 100 not in text
        assert "超出总长度上限" in text

    def test_file_count_capped(self, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "PROMPT_DOC_MAX_FILES", 1)

        text = build_prompt_documents_text([
            {"name": "a.md", "text": "AAA"},
            {"name": "b.md", "text": "BBB"},
        ])

        assert "AAA" in text
        assert "BBB" not in text
        assert "超出数量上限" in text

    def test_accepts_objects_with_attributes(self):
        """请求体里是 PromptDocument 对象，单元测试里也允许传 dict"""

        class _Doc:
            name = "obj.md"
            text = "对象正文"

        assert "对象正文" in build_prompt_documents_text([_Doc()])

    def test_truncate_is_idempotent(self):
        once, truncated = truncate_document_text("x" * 50, max_chars=10)
        assert truncated is True
        assert once.endswith("已截断）")

        twice, truncated_again = truncate_document_text(once, max_chars=10)
        assert twice == once
        assert truncated_again is False


# ============ 上传接口 ============

class TestUploadPromptDocument:
    def test_upload_markdown(self, client):
        content = "# 我的项目\n\n负责后端接口与调度".encode("utf-8")
        response = client.post(
            "/upload/document",
            files={"file": ("profile.md", content, "text/markdown")},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["type"] == "document"
        assert body["filename"] == "profile.md"
        assert "我的项目" in body["text"]

    def test_upload_gbk_text_is_decoded(self, client):
        """Windows 上常见 GBK 编码的 txt，解析器要能认出来"""
        content = "个人简历：擅长 Python".encode("gbk")
        response = client.post(
            "/upload/document",
            files={"file": ("info.txt", content, "text/plain")},
        )

        assert response.status_code == 200
        assert "擅长 Python" in response.json()["text"]

    def test_upload_oversized_text_is_truncated(self, client, monkeypatch):
        from config import settings

        monkeypatch.setattr(settings, "PROMPT_DOC_MAX_CHARS", 20)

        response = client.post(
            "/upload/document",
            files={"file": ("long.txt", ("字" * 100).encode("utf-8"), "text/plain")},
        )

        assert response.status_code == 200
        text = response.json()["text"]
        assert "已截断" in text
        assert len(text) < 100

    def test_upload_rejects_unsupported_extension(self, client):
        response = client.post(
            "/upload/document",
            files={"file": ("virus.exe", b"MZ...", "application/octet-stream")},
        )
        assert response.status_code == 400


# ============ 在 /chat/stream 中的位置 ============

def _capture_chat_messages(monkeypatch):
    """把 stream_chat 换成「记录 messages 就结束」的假实现"""
    captured: dict = {}

    async def fake_stream(messages, **kwargs):
        captured["messages"] = messages
        captured["kwargs"] = kwargs
        yield {"type": "content", "content": "好的"}
        yield {"type": "done", "content": ""}

    import routers.chat as chat_router

    monkeypatch.setattr(chat_router, "stream_chat", fake_stream)
    return captured


def _post_chat(client, **extra):
    body = {
        "messages": [{"role": "user", "content": "请开始面试"}],
        "mode": "interviewer",
        **extra,
    }
    response = client.post("/chat/stream", json=body)
    assert response.status_code == 200
    # SSE 流要读完，生成器才会把 messages 交给 stream_chat
    assert "[DONE]" in response.text
    return response


class TestChatStreamDocumentPosition:
    def test_document_sits_between_system_and_dialogue(self, client, monkeypatch):
        captured = _capture_chat_messages(monkeypatch)

        _post_chat(
            client,
            prompt_documents=[
                {"name": "personal.md", "text": "我叫张三，做过支付系统"},
                {"name": "project.md", "text": "项目：面试 Agent"},
            ],
        )

        messages = captured["messages"]
        assert len(messages) == 3

        # 0: 系统提示词（模板）
        assert messages[0]["role"] == "system"
        assert "你正在参加一场面试" in messages[0]["content"]

        # 1: 附加文档 —— 位于系统提示词与对话之间
        assert messages[1]["role"] == "system"
        assert "【附加资料】" in messages[1]["content"]
        assert "我叫张三，做过支付系统" in messages[1]["content"]
        assert "项目：面试 Agent" in messages[1]["content"]

        # 2: 真正的对话从用户提问开始
        assert messages[2] == {"role": "user", "content": "请开始面试"}

    def test_without_documents_no_extra_message(self, client, monkeypatch):
        captured = _capture_chat_messages(monkeypatch)
        _post_chat(client)

        messages = captured["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "请开始面试"}

    def test_same_documents_produce_identical_prefix(self, client, monkeypatch):
        """同一批文档两轮请求的文档消息必须逐字节一致（前缀缓存的前提）"""
        captured = _capture_chat_messages(monkeypatch)
        docs = [{"name": "a.md", "text": "稳定内容"}]

        _post_chat(client, prompt_documents=docs)
        first = captured["messages"][1]["content"]
        first_fp = _post_chat(client, prompt_documents=docs).headers["X-Prefix-Fingerprint"]

        _post_chat(client, prompt_documents=docs)
        assert captured["messages"][1]["content"] == first
        assert _post_chat(client, prompt_documents=docs).headers["X-Prefix-Fingerprint"] == first_fp

    def test_changing_documents_changes_fingerprint(self, client, monkeypatch):
        _capture_chat_messages(monkeypatch)

        fp_a = _post_chat(
            client, prompt_documents=[{"name": "a.md", "text": "版本 A"}]
        ).headers["X-Prefix-Fingerprint"]
        fp_b = _post_chat(
            client, prompt_documents=[{"name": "a.md", "text": "版本 B"}]
        ).headers["X-Prefix-Fingerprint"]

        assert fp_a != fp_b

    def test_document_survives_serialization(self, client, monkeypatch):
        """文档块在 SSE 帧之后仍然可解析（确保没被 JSON 包裹破坏）"""
        captured = _capture_chat_messages(monkeypatch)
        response = _post_chat(
            client, prompt_documents=[{"name": "a.md", "text": "内容 \"引号\" \n 换行"}]
        )

        # 帧仍是合法 JSON
        frames = [
            line[len("data: "):]
            for line in response.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        assert frames
        for frame in frames:
            json.loads(frame)

        assert "内容 \"引号\"" in captured["messages"][1]["content"]
