"""端到端验证：模拟前端的「稳定前缀回传」链路

跑法：.venv\\Scripts\\python.exe scripts\\verify_app_prefix_cache.py

与裸 API 验证的区别：这里走完整的 /chat/stream 路由，并且**模拟前端行为** ——
从 SSE 的 system_prefix 事件里取回权威前缀，下一轮放进 messages[0] 原样回传。
因此它验证的是真实的前端+后端协作：前缀逐字节稳定、服务端缓存持续命中。

会在最后清理临时岗位。
"""

import json
import logging
import os
import re
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

_USAGE_RE = re.compile(
    r"LLM usage \| model=(?P<model>\S+) \| label=(?P<label>\S+) \| "
    r"prompt=(?P<prompt>\S+) \(cache_hit=(?P<hit>\S+), cache_miss=(?P<miss>\S+)\)"
)
_PREFIX_RE = re.compile(r"prefix=(?P<source>[\w\-()]+) \| fp=")

POSITION = f"前缀回传验证岗-{uuid.uuid4().hex[:6]}"
RESUME = "五年后端经验，负责过支付网关、检索服务与高并发订单系统。" * 6


class LogCollector(logging.Handler):
    """收集 usage 与 prefix 来源两类日志"""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.usages: list[dict] = []
        self.prefix_sources: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()

        m = _USAGE_RE.search(msg)
        if m:
            d = m.groupdict()

            def num(key):
                v = d.get(key)
                return int(v) if v and v.isdigit() else None

            hit, miss = num("hit"), num("miss")
            total = (hit + miss) if (hit is not None and miss is not None) else None
            self.usages.append({
                "prompt": num("prompt"),
                "hit": hit,
                "miss": miss,
                "rate": (hit / total * 100) if total else None,
            })

        p = _PREFIX_RE.search(msg)
        if p:
            self.prefix_sources.append(p.group("source"))


def stream_turn(client: TestClient, messages: list[dict]) -> tuple[str, str | None]:
    """发一轮请求；返回 (错误, 本轮下发的 system_prefix)"""
    body = {
        "messages": messages,
        "mode": "candidate",
        "position_name": POSITION,
        "resume_text": RESUME,
        "thinking_enabled": False,
    }
    error = ""
    prefix = None
    with client.stream("POST", "/chat/stream", json=body) as response:
        assert response.status_code == 200, response.status_code
        for line in response.iter_lines():
            if not line:
                continue
            text = line.decode("utf-8") if isinstance(line, bytes) else line
            if not text.startswith("data: ") or text[6:].strip() == "[DONE]":
                continue
            try:
                event = json.loads(text[6:])
            except ValueError:
                continue
            if event.get("type") == "error":
                error = event.get("content", "")
            elif event.get("type") == "system_prefix":
                prefix = event.get("content")
    return error, prefix


def main() -> int:
    collector = LogCollector()
    for name in ("services.llm_client", "routers.chat"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.addHandler(collector)

    with TestClient(app) as client:
        creds = {
            "email": "prefix-verify@example.com",
            "password": "prefix-verify-password",
            "display_name": "Prefix Verify",
        }
        auth = client.post("/auth/register", json=creds)
        if auth.status_code == 409:
            auth = client.post("/auth/login", json={
                "email": creds["email"], "password": creds["password"],
            })
        assert auth.status_code in (200, 201), auth.text
        client.headers.update({"Authorization": f"Bearer {auth.json()['access_token']}"})

        client.post("/positions", json={"name": POSITION, "description": "验证用"})
        client.post(f"/positions/{POSITION}/jds", json={
            "content": "岗位要求：精通 Python / FastAPI，有向量检索与性能优化经验。" * 5
        })

        try:
            stored_prefix: str | None = None
            history: list[dict] = []

            print("模拟前端：从 system_prefix 事件取回权威前缀，下一轮放进 messages[0]\n")
            for turn in range(1, 4):
                history = history + [{"role": "user", "content": f"第{turn}轮：请开始面试"}]
                # 前端行为：手上有前缀就放在最前面原样回传
                sent = (
                    [{"role": "system", "content": stored_prefix}] + history
                    if stored_prefix else history
                )
                error, prefix = stream_turn(client, sent)
                if error:
                    print(f"第 {turn} 轮失败：{error[:200]}")
                    return 1
                if prefix is not None:
                    stored_prefix = prefix
                    print(f"  第 {turn} 轮 | 后端下发了前缀（{len(prefix)} 字符），已保存")
                else:
                    print(f"  第 {turn} 轮 | 未下发前缀（说明前端回传的那份被采信了）")

                usage = collector.usages[-1] if collector.usages else {}
                source = collector.prefix_sources[-1] if collector.prefix_sources else "?"
                rate = f"{usage['rate']:.1f}%" if usage.get("rate") is not None else "n/a"
                print(
                    f"            prefix={source} | prompt={usage.get('prompt')} "
                    f"cache_hit={usage.get('hit')} cache_miss={usage.get('miss')} 命中率={rate}"
                )
                history = history + [{"role": "assistant", "content": "（上一轮的回答）"}]
        finally:
            client.delete(f"/positions/{POSITION}")

    print()
    sources = collector.prefix_sources
    if sources:
        print("prefix 来源序列：", " → ".join(sources))
        print("期望：build（首轮构建）→ client（前端回传被采信）→ client")
    if collector.usages and collector.usages[0].get("hit") is not None:
        hits = [u["hit"] for u in collector.usages]
        print("cache_hit 序列：", hits, "（应保持稳定的大值）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
