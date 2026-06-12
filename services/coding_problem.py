"""编程题服务 — 根据岗位类型和答题情况智能选题（优先数据库，回退 JSON）"""

import asyncio
import json
import random
import os
from typing import Optional

from sqlalchemy import select

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "leetcode_problems.json")

# 题目难度对应的分值：easy=1, medium=2, hard=3
DIFFICULTY_SCORE = {"easy": 1, "medium": 2, "hard": 3}

# 岗位类型 → 难度偏移
# 正值 = 偏好更难的题，负值 = 偏好更简单的题
POSITION_DIFFICULTY_BIAS = {
    "开发": 1,    # 开发岗：偏好 medium/hard
    "工程师": 1,
    "架构": 2,
    "算法": 2,
    "研发": 1,
    "全栈": 1,
    "后端": 1,
    "前端": 0,
    "AI": 2,
    "测试": -1,   # 测试岗：偏好 easy/medium
    "QA": -1,
    "运维": 0,
    "DevOps": 0,
    "数据": 0,
    "安全": 1,
    "嵌入式": 0,
    "游戏": 1,
}


def _load_problems() -> list[dict]:
    """加载题库（优先数据库，回退 JSON 文件）"""
    try:
        # 尝试从数据库加载
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在异步上下文中，创建新的事件循环来运行同步查询会有问题
            # 但 select_problems 本身是同步函数，在 async handler 中通过 run_in_executor 调用
            # 所以这里优先用 JSON 回退（DB 查询是 async 的，不能在同步函数中直接用）
            pass
    except RuntimeError:
        pass

    # 回退到 JSON 文件
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


async def load_problems_from_db(db) -> list[dict]:
    """从数据库加载题库（异步版本，供路由使用）"""
    from models.db_models import QuestionBankItem
    result = await db.execute(
        select(QuestionBankItem).where(QuestionBankItem.category == "algorithm")
    )
    items = result.scalars().all()
    return [
        {
            "id": item.id,
            "title": item.title,
            "title_cn": item.title,
            "difficulty": item.difficulty,
            "description": item.content,
            "examples": "",
            "hint": "",
            "tags": item.tags or [],
        }
        for item in items
    ]


def _get_difficulty_bias(position_type: str, position_name: str) -> int:
    """
    根据岗位类型计算难度偏移。
    
    优先根据 position_type（关键词分类结果），
    然后根据 position_name 中的具体关键词微调。
    """
    bias = 0

    # 根据岗位类型
    if position_type == "技术岗":
        # 从岗位名称中提取更细粒度的偏向
        name_lower = position_name.lower()
        for kw, b in POSITION_DIFFICULTY_BIAS.items():
            if kw.lower() in name_lower:
                bias = b
                break
        # 未匹配到具体方向，默认中等
        if bias == 0 and position_type == "技术岗":
            bias = 0  # 中性
    elif position_type == "非技术岗":
        bias = -2  # 非技术岗基本不出编程题
    else:
        bias = 0

    return bias


def _get_adaptive_adjustment(conversation_history: list[str]) -> int:
    """
    根据对话历史评估候选人的回答质量，返回难度调整值。
    
    简单策略：分析最近几轮 AI 面试官的评价。
    如果 AI 多次给出正面评价（"很好"、"不错"、"正确"等），上调难度；
    如果多次给出负面评价（"不对"、"错误"、"需要加强"等），下调难度。
    
    Returns:
        -1: 降低难度, 0: 不变, 1: 提高难度
    """
    if not conversation_history:
        return 0

    # 只分析最近的 assistant 消息（AI 面试官的评价）
    recent = conversation_history[-6:]  # 最近6条
    positive = 0
    negative = 0

    positive_words = ["很好", "不错", "正确", "优秀", "很棒", "回答得很好", "理解到位", "没问题", "对的"]
    negative_words = ["不对", "错误", "不太准确", "需要加强", "有待提升", "有偏差", "不正确", "可以更好"]

    for msg in recent:
        for pw in positive_words:
            if pw in msg:
                positive += 1
                break
        for nw in negative_words:
            if nw in msg:
                negative += 1
                break

    if positive > negative + 1:
        return 1   # 表现好，上难度
    elif negative > positive + 1:
        return -1  # 表现差，降难度
    return 0


def select_problems(
    position_type: str = "未知",
    position_name: str = "",
    conversation_history: Optional[list[str]] = None,
    count: int = 3,
) -> list[dict]:
    """
    智能选择编程题。

    Args:
        position_type: 岗位类型（"技术岗"/"非技术岗"/"未知"）
        position_name: 岗位名称（用于更细粒度的关键词匹配）
        conversation_history: 对话历史（用于自适应难度调整）
        count: 选择题目数量（默认3道，覆盖不同难度）

    Returns:
        选中的题目列表，每道题包含 id, title, title_cn, difficulty, description, examples, hint
    """
    problems = _load_problems()
    if not problems:
        return []

    # 计算目标难度分值
    base_bias = _get_difficulty_bias(position_type, position_name)
    adaptive = _get_adaptive_adjustment(conversation_history or [])
    total_bias = base_bias + adaptive

    # 目标难度分值：2 代表 medium, 1-2 偏 easy, 2-3 偏 hard
    target_score = max(1, min(3, 2 + total_bias))

    # 非技术岗直接返回空（不出编程题）
    if position_type == "非技术岗":
        return []

    # 为每道题计算"适配分数"——越接近目标难度越好
    def fit_score(p: dict) -> float:
        ds = DIFFICULTY_SCORE.get(p["difficulty"], 2)
        # 距离目标越近分数越高，同时加入随机扰动避免每次都选一样
        return -abs(ds - target_score) + random.uniform(0, 0.5)

    # 按适配分数排序
    sorted_problems = sorted(problems, key=fit_score, reverse=True)

    # 从排名靠前的中随机选取 count 道，同时尽量覆盖不同难度
    selected = []
    difficulties_used: set[str] = set()

    # 第一轮：尝试选不同难度的题
    for p in sorted_problems:
        if len(selected) >= count:
            break
        if p["difficulty"] not in difficulties_used:
            selected.append(p)
            difficulties_used.add(p["difficulty"])

    # 第二轮：如果还不够，补足
    for p in sorted_problems:
        if len(selected) >= count:
            break
        if p not in selected:
            selected.append(p)

    # 按难度排序（easy → medium → hard）
    difficulty_order = {"easy": 0, "medium": 1, "hard": 2}
    selected.sort(key=lambda p: difficulty_order.get(p["difficulty"], 1))

    return selected


def format_problems_for_prompt(problems: list[dict]) -> str:
    """
    将选中的题目格式化为可注入 prompt 的文本。
    """
    if not problems:
        return ""

    parts = ["\n## 可选编程题（供面试过程中随机抽选）\n"]
    parts.append("请根据候选人的实际水平和岗位要求，从以下题目中灵活选择。不必全部使用，也不必严格按顺序。\n")

    for i, p in enumerate(problems):
        difficulty_label = {"easy": "⭐ 简单", "medium": "⭐⭐ 中等", "hard": "⭐⭐⭐ 困难"}.get(p["difficulty"], p["difficulty"])
        category_label = p.get("category_cn", p.get("category", ""))
        parts.append(f"### 题目{i + 1}：{p['title_cn']}（{p['title']}）{difficulty_label} | {category_label}")
        parts.append(f"\n{p['description']}\n")

        if p.get("hint"):
            parts.append(f"**解题提示（仅供面试官参考，请勿直接透露给候选人）：**{p['hint']}")

        parts.append("\n---\n")

    return "\n".join(parts)
