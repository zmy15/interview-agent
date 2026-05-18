"""提示模板加载工具 — 基于 LangChain ChatPromptTemplate"""

import os

from langchain_core.prompts import ChatPromptTemplate

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")

# 缓存已加载的模板，避免重复读取磁盘
_template_cache: dict[str, ChatPromptTemplate] = {}


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
        "candidate_level_guide": "",
        "interview_round_guide": "",
        # 时间预算默认值（用于 interviewer prompt 模板）
        "duration_minutes": "30",
        "intro_min": "3",
        "tech_qa_min": "24",
        "coding_min": "0（无编程题）",
        "reverse_min": "3",
        "question_count": "8",
        "avg_time_per_question": "3",
    }
    for key, default_value in defaults.items():
        kwargs.setdefault(key, default_value)

    # 格式化 resume 和 code（添加标签头）
    if kwargs.get("resume"):
        kwargs["resume"] = f"\n候选人简历：\n{kwargs['resume']}\n"
    else:
        kwargs["resume"] = ""

    if kwargs.get("code"):
        kwargs["code"] = f"\n相关代码：\n{kwargs['code']}\n"
    else:
        kwargs["code"] = ""

    # 生成候选人经验级别指导
    candidate_level = kwargs.get("candidate_level", "")
    if not kwargs.get("candidate_level_guide"):
        kwargs["candidate_level_guide"] = _build_candidate_level_guide(candidate_level)

    # 生成面试轮次指导
    interview_round = kwargs.get("interview_round", "")
    if not kwargs.get("interview_round_guide"):
        kwargs["interview_round_guide"] = _build_interview_round_guide(interview_round)

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
            "- 项目提问：深挖实习或毕业设计的项目细节、技术选型理由、优化思路\n"
            "- 非技术岗侧重：逻辑分析能力、团队协作经历、对行业的理解\n"
        ),
        "experienced": (
            "\n【候选人经验级别：社招生】\n"
            "- 侧重考察：项目落地经验、系统设计能力、技术选型与权衡、业务理解深度、团队协作和推动能力\n"
            "- 提问难度：以实际场景和项目经验为主，考察解决复杂问题的能力\n"
            "- 项目提问：深挖工作项目中的架构设计、难点攻克、性能优化、团队管理、业务指标\n"
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
            "\n【面试轮次：一面（技术初筛）】\n"
            "- 目标：快速筛选基础能力合格的候选人\n"
            "- 侧重：基础知识扎实度、编程能力、学习能力\n"
            "- 提问数量：8-12 个技术问题，覆盖面要广\n"
            "- 深度：中浅，确认候选人具备岗位所需的基本技能\n"
        ),
        "second": (
            "\n【面试轮次：二面（技术深挖）】\n"
            "- 目标：深度评估候选人的技术深度和项目经验\n"
            "- 侧重：系统设计、架构能力、项目难点攻克、技术视野\n"
            "- 提问数量：4-6 个深度问题，每个问题要充分追问\n"
            "- 深度：深入挖掘，关注候选人的思考过程和解决方案\n"
        ),
        "hr": (
            "\n【面试轮次：HR面】\n"
            "- 目标：评估候选人的综合素质、文化匹配度和职业规划\n"
            "- 侧重：沟通能力、团队协作、职业发展规划、薪资期望、离职原因、价值观\n"
            "- 提问数量：6-10 个问题\n"
            "- 深度：中等，以开放式问题为主，观察候选人的表达和态度\n"
            "- 注意：HR面不涉及技术细节，主要关注软技能和综合素质，但对技术岗可简单了解项目经历\n"
        ),
    }
    return guides.get(round, "")


def invalidate_cache():
    """清除模板缓存（用于热更新场景）"""
    _template_cache.clear()
