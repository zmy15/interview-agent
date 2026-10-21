"""提示模板加载工具 — 基于 LangChain ChatPromptTemplate

模板结构约定（**改动模板时请务必遵守**）：
    模板从「━━━ 以下为本场面试的固定背景信息 ━━━」之后开始，
    依次是 `经验级别 → 轮次 → 岗位类型 → 简历 → JD`（求职者模式末尾还有时间预算），
    前方全部是静态指令。

    这样排列是为了**前缀缓存（prompt caching）**：一次面试里
    「静态指令 + 简历 + JD」构成逐字节不变的稳定前缀，每轮请求只在尾部
    追加新的问答，服务端就能复用已缓存的 KV。任何放在前缀里的可变内容
    （RAG 检索结果、每轮变化的题库/时间预算等）都会让缓存从该位置起全部失效，
    因此它们一律由调用方放到最后一条 user 消息的尾部。
"""

import os
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

# 缓存已加载的模板，避免重复读取磁盘
_template_cache: dict[str, ChatPromptTemplate] = {}

# 遵循「指令在前、固定背景信息在后」结构的模板（见模块 docstring）。
# 只有这些模板才允许走「只构建一次 system、后续复用」的快路径。
_CACHED_PREFIX_TEMPLATES = frozenset({"interviewer", "candidate"})


def _get_template(template_name: str) -> ChatPromptTemplate:
    """加载并缓存提示模板"""
    if template_name in _template_cache:
        return _template_cache[template_name]

    file_path = os.path.join(PROMPTS_DIR, f"{template_name}.txt")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"提示模板不存在: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        template_text = f.read()

    # 使用 ChatPromptTemplate，单条 system 消息
    prompt = ChatPromptTemplate.from_messages([
        ("system", template_text),
    ])
    _template_cache[template_name] = prompt
    return prompt


def load_prompt(template_name: str, **kwargs) -> str:
    """
    加载提示模板并填充占位符。

    使用 LangChain ChatPromptTemplate 替代原生 str.format()，
    支持变量校验、部分变量等高级特性。

    Args:
        template_name: 模板名称（不含 .txt 后缀），如 "interviewer"
        **kwargs: 占位符变量，如 jd, resume, code, history, position_type,
                  candidate_level, interview_round

    Returns:
        填充后的 system 提示字符串
    """
    prompt = _get_template(template_name)

    # 为缺失的占位符提供默认值
    defaults = {
        "jd": "暂无岗位描述",
        "resume": "",
        "code": "",
        "history": "",
        "position_type": "未知",
        "candidate_level": "",
        "interview_round": "",
        "candidate_level_guide": "",
        "interview_round_guide": "",
        # 时间预算默认值（用于 candidate 模板）
        "duration_minutes": "30",
        "intro_min": "3",
        "tech_qa_min": "24",
        "coding_min": "0（无编程题）",
        "reverse_min": "3",
        "question_count": "8",
        "avg_time_per_question": "3",
        # 动态环节标签（一面/二面 vs HR面）
        "qa_section_label": "技术问答环节",
        "qa_section_instruction": "根据JD中的职责要求和能力要求，结合候选人的经验级别和面试轮次，逐一考察候选人的专业能力",
        "coding_section_note": "仅技术岗",
        "coding_section_instruction": "如果系统提示中包含了\"可选编程题\"，请在专业问答进行一半后，择机插入一道编程题",
        # 稳定前缀里的附加块（由调用方预格式化，含标题和分隔符）
        "question_bank_text": "",
        "prompt_notes": "",
    }
    for key, default_value in defaults.items():
        kwargs.setdefault(key, default_value)

    # 生成候选人经验级别指导
    level = kwargs.get("candidate_level") or ""
    if not kwargs.get("candidate_level_guide"):
        kwargs["candidate_level_guide"] = _build_candidate_level_guide(level) or "（未指定，按通用标准把握深度）"

    # 生成面试轮次指导
    round_ = kwargs.get("interview_round") or ""
    if not kwargs.get("interview_round_guide"):
        kwargs["interview_round_guide"] = _build_interview_round_guide(round_) or "（未指定轮次，按常规技术面把握）"

    # 生成动态环节标签（HR面 vs 技术面）
    _apply_round_section_labels(kwargs, round_)

    # 以下 4 个槽位由调用方传入**已格式化**的文本（可含多行），
    # 这里只负责兜底空值，不再二次包装 —— 包装会破坏前缀的字节稳定性。
    for key in ("resume", "code", "jd", "question_bank_text", "prompt_notes"):
        if not kwargs.get(key):
            kwargs[key] = "（无）" if key in ("resume", "jd", "code") else ""

    # LangChain ChatPromptTemplate.format() 返回格式化后的消息字符串
    formatted = prompt.format(**kwargs)
    return formatted


def _build_candidate_level_guide(level: str) -> str:
    """根据候选人经验级别生成指导文本"""
    if not level:
        return ""
    guides = {
        "intern": (
            "\n【候选人经验级别：实习生】\n"
            "- 侧重考察：编程语言基础、数据结构与算法基础、计算机网络/操作系统基本概念、简单的项目经历\n"
            "- 提问难度：以基础概念和八股文为主，关注学习能力和潜力\n"
            "- 项目提问：围绕学校项目或实习经历，重点问'你做了什么、遇到什么困难、怎么解决的'\n"
            "- 非技术岗侧重：沟通表达能力、学习意愿、基本业务理解\n"
        ),
        "new_grad": (
            "\n【候选人经验级别：校招生】\n"
            "- 侧重考察：扎实的计算机基础、一到两门精通语言、项目深度、实习经验总结\n"
            "- 提问难度：基础+进阶，考察知识体系的完整性，可以适当追问深度问题\n"
            "- 项目提问：深挖实习或毕业设计的项目细节、技术选型理由、优化思路；回答时请严格遵循STAR法则（情境→任务→行动→结果），用数据量化成果\n"
            "- 非技术岗侧重：逻辑分析能力、团队协作经历、对行业的理解\n"
        ),
        "experienced": (
            "\n【候选人经验级别：社招生】\n"
            "- 侧重考察：项目落地经验、系统设计能力、技术选型与权衡、业务理解深度、团队协作和推动能力\n"
            "- 提问难度：以实际场景和项目经验为主，考察解决复杂问题的能力\n"
            "- 项目提问：深挖工作项目中的架构设计、难点攻克、性能优化、团队管理、业务指标；回答时请严格遵循STAR法则（情境→任务→行动→结果），行动部分需占回答50%以上篇幅，结果部分务必用数据说话\n"
            "- 非技术岗侧重：业务成果量化、跨部门协调经验、管理能力、行业资源\n"
        ),
    }
    return guides.get(level, "")


def _build_interview_round_guide(round: str) -> str:
    """根据面试轮次生成指导文本"""
    if not round:
        return ""
    guides = {
        "first": (
            "\n【面试轮次：一面（基础初筛）】\n"
            "- 目标：快速验证候选人基础能力是否达标\n"
            "- 侧重：计算机基础（网络/OS/数据库）、编程语言基础、数据结构与算法、基本概念和八股文\n"
            "- 提问数量：8-12 个基础问题，覆盖面要广\n"
            "- 深度：中浅，确认候选人具备岗位所需的基本功，不要深挖\n"
            "- 禁止：不要问系统设计、架构权衡、项目难点等深度问题（留给二面）\n"
        ),
        "second": (
            "\n【面试轮次：二面（工程实战深挖）】\n"
            "- 目标：深度评估候选人的工程实战经验和解决复杂问题的能力\n"
            "- 侧重：系统设计、架构选型与权衡、项目落地经验、性能优化、难点攻克、技术视野\n"
            "- 提问数量：4-6 个深度问题，每个问题要充分追问 2-3 层\n"
            "- 深度：深入挖掘，重点关注候选人的思考过程、技术决策理由（why）和 trade-off\n"
            "- 禁止：不要再问基础概念和八股文（一面已覆盖），聚焦实际项目经验和工程能力\n"
        ),
        "hr": (
            "\n【面试轮次：HR面（综合素质评估）】\n"
            "- 目标：评估候选人的综合素质、文化匹配度、稳定性和发展潜力\n"
            "- 侧重：职业发展规划、薪资期望、团队协作与沟通能力、抗压能力与冲突处理、离职原因、价值观与企业文化匹配度\n"
            "- 提问数量：6-10 个问题，以开放式行为问题为主\n"
            "- 深度：中等，通过候选人的叙述观察其思维方式、态度和情商\n"
            "- ⚠️ 严格禁止：HR面绝不涉及任何技术内容（不问八股文、不问算法、不问系统设计、不问项目技术细节）\n"
            "- ⚠️ 如果候选人主动提及技术细节，礼貌引导回综合素质话题\n"
            "- ⚠️ 时长严格控制在 30 分钟以内，不包含编程题环节\n"
        ),
    }
    return guides.get(round, "")


def _apply_round_section_labels(kwargs: dict, interview_round: str):
    """根据面试轮次覆盖环节标签和说明文本"""
    if interview_round == "hr":
        kwargs["qa_section_label"] = "综合素质问答环节"
        kwargs["qa_section_instruction"] = (
            "严格不涉及任何技术内容！围绕职业规划、薪资期望、团队协作、"
            "抗压能力、冲突处理、离职原因、价值观等维度提问，以开放式行为问题为主"
        )
        kwargs["coding_section_note"] = "HR面不包含此环节"
        kwargs["coding_section_instruction"] = "HR面不包含编程题，请严格跳过此环节，不要出任何编程题"
    else:
        # 技术面（一面/二面）保持默认值
        pass


def build_question_bank_text(items: list, mode: str) -> str:
    """把题库条目渲染成固定前缀里的一段文本。

    与 ``_build_dynamic_context`` 不同，这段内容在整个会话期间不变，
    因此可以安全地放在稳定前缀中（第二次请求就能命中缓存）。
    """
    if not items:
        return ""

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
    parts = ["【指定题库】", mode_instructions.get(mode, mode_instructions["mixed"])]
    for i, item in enumerate(items, 1):
        difficulty = getattr(item, "difficulty", None) or "medium"
        category = getattr(item, "category", None) or "general"
        content = getattr(item, "content", "") or ""
        parts.append(
            f"\n题目{i}（{difficulty} | {category}）：{getattr(item, 'title', '')}\n"
            f"{content[:500]}"
        )
    return "\n".join(parts)


def build_prompt_notes_text(notes: Optional[str]) -> str:
    """把用户补充说明渲染成固定前缀里的一段文本"""
    notes = (notes or "").strip()
    if not notes:
        return ""
    return "【用户补充说明】\n" + notes


def is_stable_prefix_template(template_name: str) -> bool:
    """判断模板是否遵循「指令在前、固定背景信息在后」的缓存友好结构"""
    return template_name in _CACHED_PREFIX_TEMPLATES


def invalidate_cache():
    """清除模板缓存（用于热更新场景）"""
    _template_cache.clear()
