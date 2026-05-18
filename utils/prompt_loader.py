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
        **kwargs: 占位符变量，如 jd, resume, code, history, position_type

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

    # LangChain ChatPromptTemplate.format() 返回格式化后的消息字符串
    formatted = prompt.format(**kwargs)
    return formatted


def invalidate_cache():
    """清除模板缓存（用于热更新场景）"""
    _template_cache.clear()
