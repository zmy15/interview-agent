"""应用路径解析 — 兼容「源码运行」与「PyInstaller 冻结运行」两种形态

为什么需要这个模块：
    用 PyInstaller 把 desktop.py 打成 exe 后，进程分化为两个世界：

    * **只读资源**（前端构建产物 frontend/dist、种子题库 data/question_bank.db、
      提示词 prompts/）位于打包解包目录（PyInstaller 注入的 sys._MEIPASS）。
      代码里 `os.path.dirname(__file__)` 拼出来的相对路径在冻结模式下
      仍然指向 _MEIPASS，因此这类资源**无需改代码**，打包时收进去即可；
    * **可变数据**（SQLite、日志、截图、模型缓存）绝不能写进打包目录：
      安装目录可能在 Program Files（无管理员权限写不进去），且会随
      卸载/升级丢失。必须落到用户目录 `%LOCALAPPDATA%\\InterviewAgent`。

本模块把这两个概念显式分开。源码运行时的行为与以前完全一致
（项目根目录下的 data/、hf_cache/、logs/），不会影响现有部署。

可用环境变量覆盖默认位置（高级用户 / 便携模式）：
    INTERVIEW_AGENT_HOME   可变数据根目录（默认 %LOCALAPPDATA%\\InterviewAgent）
"""

import os
import sys

# 应用名（同时用于用户目录名与窗口标题）
APP_NAME = "InterviewAgent"
# 便携/绿色模式：把可变数据放到 exe 同目录的 portable_data/ 下
PORTABLE_DIR_NAME = "portable_data"


def is_frozen() -> bool:
    """是否运行在 PyInstaller 打包出的可执行文件里"""
    return getattr(sys, "frozen", False)


def bundle_dir() -> str:
    """只读资源目录

    冻结运行时：PyInstaller 的解包目录（onefile 在临时目录，onedir 在
    _internal/）。源码运行时：项目根目录（本文件所在目录）。
    """
    if is_frozen():
        return getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def exe_dir() -> str:
    """可执行文件所在目录（安装目录）；源码运行时等同 bundle_dir()"""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return bundle_dir()


def user_data_dir() -> str:
    """可变数据根目录

    冻结运行：%LOCALAPPDATA%\\InterviewAgent（可用 INTERVIEW_AGENT_HOME 覆盖；
    exe 同目录存在 portable_data/ 标记目录时改用便携目录，便于 U 盘分发）。
    源码运行：项目根目录 —— 与历史行为一致。
    """
    if not is_frozen():
        return bundle_dir()

    override = os.getenv("INTERVIEW_AGENT_HOME", "").strip()
    if override:
        path = os.path.abspath(override)
    else:
        # 便携模式：安装目录下放一个空的 portable_data 目录即触发
        portable_marker = os.path.join(exe_dir(), PORTABLE_DIR_NAME)
        if os.path.isdir(portable_marker):
            path = portable_marker
        else:
            base = os.getenv("LOCALAPPDATA") or os.path.expanduser("~")
            path = os.path.join(base, APP_NAME)

    # 首次启动时该目录尚不存在 —— desktop.py 的 chdir、SQLite 建库、
    # 日志写入都依赖它，这里统一创建（幂等）。
    os.makedirs(path, exist_ok=True)
    return path


def data_dir() -> str:
    """持久化数据目录（SQLite 等）。目录不存在时创建。"""
    path = os.path.join(user_data_dir(), "data")
    os.makedirs(path, exist_ok=True)
    return path


def logs_dir() -> str:
    """日志目录。目录不存在时创建。"""
    path = os.path.join(user_data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def models_dir() -> str:
    """模型缓存目录（HuggingFace 缓存等）。目录不存在时创建。"""
    path = os.path.join(user_data_dir(), "hf_cache")
    os.makedirs(path, exist_ok=True)
    return path
