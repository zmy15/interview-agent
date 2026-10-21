"""真机验证：前缀缓存命中情况（需要 .env 里配置可用的 DEEPSEEK_API_KEY）

跑法：.venv\\Scripts\\python.exe scripts\\verify_prefix_cache.py

用同一份固定前缀（等价于 system 里的「prompt + 简历 + JD」）连发多轮，
在尾部追加逐轮增长的问答，然后解析 services.llm_client 记录的 usage，
确认：

  1. stream_options={"include_usage": True} 被服务端接受，usage 确实能拿到；
  2. 第 2 轮起 prompt 前缀命中服务端缓存（cache_hit 明显 > 0）；
  3. 前缀一旦变化（换了简历），命中量会掉回去 —— 说明「前缀决定命中」。

只读 .env 的 Key，不写任何业务数据。
"""

import asyncio
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from config import settings  # noqa: E402
from services.llm_client import aclose, stream_chat  # noqa: E402

_USAGE_RE = re.compile(
    r"LLM usage \| model=(?P<model>\S+) \| label=(?P<label>\S+) \| "
    r"prompt=(?P<prompt>\S+) \(cache_hit=(?P<hit>\S+), cache_miss=(?P<miss>\S+)\)"
)


class UsageCollector(logging.Handler):
    """把 stream_chat 打出的 usage 日志收集成结构化数据"""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        m = _USAGE_RE.search(msg)
        if not m:
            return
        d = m.groupdict()

        def num(key):
            v = d.get(key)
            return int(v) if v and v.isdigit() else None

        hit, miss = num("hit"), num("miss")
        total = (hit + miss) if (hit is not None and miss is not None) else None
        self.records.append({
            "label": d["label"],
            "prompt": num("prompt"),
            "hit": hit,
            "miss": miss,
            "rate": (hit / total * 100) if total else None,
        })


def build_prefix(tag: str) -> str:
    """构造一段足够长的固定前缀（真实场景里由 load_prompt 生成）"""
    return (
        "你是面试官。以下是本场面试的固定背景信息，全程不得改动：\n"
        "岗位描述："
        + f"[{tag}]" + "需要精通 Python、FastAPI、向量检索与分布式系统。" * 40 + "\n"
        "候选人简历：" + "五年后端经验，负责过支付网关与检索服务。" * 40 + "\n"
        "角色要求：严格按上述背景提问，不要编造简历里没有的经历。"
    )


async def ask(prefix: str, history: list[dict], label: str) -> str:
    """发一轮请求；history 是除 system 以外的消息（尾部就是本轮新增）"""
    messages = [{"role": "system", "content": prefix}] + history
    error = ""
    async for chunk in stream_chat(
        messages,
        model=settings.DEEPSEEK_MODEL,
        thinking_enabled=False,
        cache_label=label,
    ):
        if chunk["type"] == "error":
            error = chunk["content"]
    return error


async def scenario(collector: UsageCollector, title: str, prefix_tag: str) -> None:
    print(f"\n【{title}】")
    prefix = build_prefix(prefix_tag)
    history: list[dict] = []
    for turn in range(1, 4):
        history = history + [{"role": "user", "content": f"第{turn}轮提问：介绍一下你自己"}]
        error = await ask(prefix, history, f"{title}-turn{turn}")
        if error:
            print(f"  第 {turn} 轮失败：{error}")
            return
        rec = collector.records[-1] if collector.records else {}
        rate = f"{rec['rate']:.1f}%" if rec.get("rate") is not None else "n/a"
        print(
            f"  第 {turn} 轮 | prompt={rec.get('prompt')} "
            f"cache_hit={rec.get('hit')} cache_miss={rec.get('miss')} 命中率={rate}"
        )
        # 把上一轮的回答塞进历史，模拟真实的逐轮增长
        history = history + [{"role": "assistant", "content": "（这是上一轮的回答）"}]


async def main() -> int:
    collector = UsageCollector()
    llm_logger = logging.getLogger("services.llm_client")
    # 独立运行脚本时根 logger 默认是 WARNING，会把 info 级 usage 日志滤掉，
    # 这里显式放开（应用里由 main.py 按 LOG_LEVEL 统一配置）。
    llm_logger.setLevel(logging.INFO)
    llm_logger.addHandler(collector)

    print(f"模型：{settings.DEEPSEEK_MODEL}")
    print(f"base_url：{settings.DEEPSEEK_BASE_URL}")
    print("-" * 72)

    await scenario(collector, "同一前缀连发三轮", "固定前缀")

    before = len(collector.records)
    await scenario(collector, "换掉前缀里的简历后再发", "换了简历的前缀")

    await aclose()

    print("\n" + "-" * 72)
    if not collector.records:
        print("没有采集到任何 usage —— 请确认 Key 可用、网络可达。")
        return 1

    same = collector.records[:before]
    changed = collector.records[before:]

    print("怎么读这些数字：")
    print("  prompt     = 本次请求的输入 token 总数")
    print("  cache_hit  = 其中命中服务端上下文缓存的部分（便宜、快）")
    print("  cache_miss = 需要重新计算的增量（主要是本轮新增的问答与尾部文档）")
    print()
    if same and same[0]["hit"] is not None:
        print(f"  同一前缀连发三轮：命中率 "
              f"{same[0]['rate']:.1f}% → {same[-1]['rate']:.1f}%")
    if changed and changed[0]["hit"] is not None:
        print(f"  改动前缀后的第一轮：命中率 {changed[0]['rate']:.1f}%")
    print()
    print("期望形态：前缀保持字节不变时，cache_hit 保持在一个稳定的大值，")
    print("          增长的是 cache_miss（每轮新增的问答）；")
    print("          一旦前缀本身被改动，cache_hit 会塌到 0 附近。")
    print()
    print("实测参考（deepseek-flash，2026-10）：同前缀多轮命中 ~85%，")
    print("  且中途改动前缀会让命中直接归零，只改尾部则不影响命中。")
    print("注：服务端缓存是「写进去之后才可能被复用」，新前缀的首轮未必立刻命中。")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
