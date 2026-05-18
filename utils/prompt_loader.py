"""提示模板加载工具"""

import os

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "prompts")


def load_prompt(template_name: str, **kwargs) -> str:
    """
    加载提示模板并填充占位符。

    Args:
        template_name: 模板名称（不含 .txt 后缀），如 "interviewer"
        **kwargs: 占位符变量，如 jd, resume, code

    Returns:
        填充后的提示字符串
    """
    file_path = os.path.join(PROMPTS_DIR, f"{template_name}.txt")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"提示模板不存在: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        template = f.read()

    # 为缺失的占位符提供默认值
    defaults = {
        "jd": "暂无岗位描述",
        "resume": "",
        "code": "",
        "history": "",
        "position_type": "未知",
    }
    for key, default_value in defaults.items():
        if key not in kwargs:
            kwargs[key] = default_value

    # 格式化 resume 和 code
    if kwargs.get("resume"):
        kwargs["resume"] = f"\n候选人简历：\n{kwargs['resume']}\n"
    else:
        kwargs["resume"] = ""

    if kwargs.get("code"):
        kwargs["code"] = f"\n相关代码：\n{kwargs['code']}\n"
    else:
        kwargs["code"] = ""

    return template.format(**kwargs)
