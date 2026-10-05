"""
面试 Agent — 独立窗口启动器（桌面应用模式）

在一个独立的原生窗口中启动整个服务（后端 + 已构建前端），
并支持：窗口置顶、从屏幕捕获中排除（截屏/录屏不可见）、隐藏任务栏图标。

启动方式：
    python desktop.py                          # 默认 1280x800，置顶 + 捕获排除
    python desktop.py --no-topmost             # 关闭置顶
    python desktop.py --width 1600 --height 900
    python desktop.py --port 8123              # 自定义端口
    python desktop.py --capture-exclude false  # 允许被截屏捕获（用于调试）
    python desktop.py --window-title "我的面试"
    python desktop.py --shell browser          # 强制使用浏览器窗口（不依赖 pywebview）

    # 等价写法：作为 main.py 的参数（会转发给本模块）
    python main.py --desktop
    python main.py --desktop --no-topmost --width 1366

窗口实现（--shell 可选 auto / native / browser）：

  native（默认，推荐）
      使用 pywebview + Edge WebView2 内核创建窗口。
      窗口由「本进程」拥有，因此：
        * SetWindowDisplayAffinity 生效 —— 截屏/录屏无法看到窗口内容；
        * 置顶 / 隐藏任务栏图标同样直接作用于本进程窗口，稳定可靠。
      UI 仍由后端自身托管（frontend/dist），窗口加载 http://127.0.0.1:<port>/，
      与生产模式完全一致，同源访问 /api，无需 CORS。

  browser（回退方案）
      使用系统自带浏览器（Edge / Chrome）的 --app 模式。
      优点：零额外依赖。
      限制：窗口属于浏览器进程，Windows 的 SetWindowDisplayAffinity
            只对「本进程拥有的窗口」生效，因此「捕获排除」在跨进程时
            会被系统拒绝（实测返回 False），仅置顶可用。

依赖说明：
    native 模式需要 pywebview（pip install pywebview）与 Edge WebView2 运行时
    （Win10/11 通常已预装）。若两者缺失，会自动回退到 browser 模式。
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger("desktop")

IS_WINDOWS = sys.platform == "win32"

# 记录调用方显式传入的参数（用于区分「命令行指定」与「.env 默认值」）
_EXPLICIT_ARGS: list[str] = []

# 与前端 index.html 的 <title> 保持一致：使用该标题时无需额外改写窗口标题
_DEFAULT_WINDOW_TITLE = "面试 Agent — AI 模拟面试助手"

# ══════════════════════════════════════════════════════════════
# Windows 窗口控制（置顶 / 捕获排除 / 隐藏任务栏图标）
# ══════════════════════════════════════════════════════════════

# SetWindowDisplayAffinity 的 affinity 取值
WDA_NONE = 0x00000000
WDA_MONITOR = 0x00000001
WDA_EXCLUDEFROMCAPTURE = 0x00000011  # Win10 2004+：截屏/录屏中完全不可见

# GetWindowLongPtr / SetWindowLongPtr 的索引与样式位
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080   # 不在任务栏 / Alt-Tab 中显示
WS_EX_APPWINDOW = 0x00040000    # 强制在任务栏显示（与 TOOLWINDOW 互斥）
WS_EX_LAYERED = 0x00080000      # 分层窗口（透明度的前提）

# SetLayeredWindowAttributes 的 flags
LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002

# 透明度取值范围（0-255）；低于该下限窗口将难以操作，因此做保护性限制
MIN_OPACITY = 0.20
MAX_OPACITY = 1.0

SW_HIDE = 0
SW_SHOW = 5
SW_SHOWNA = 8
SW_RESTORE = 9

_user32 = None
if IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    _user32.SetWindowDisplayAffinity.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    _user32.SetWindowDisplayAffinity.restype = ctypes.c_bool
    _user32.GetWindowDisplayAffinity.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
    )
    _user32.GetWindowDisplayAffinity.restype = ctypes.c_bool
    _user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
    _user32.GetAncestor.restype = ctypes.c_void_p
    _user32.SetWindowPos.argtypes = (
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, ctypes.c_uint32,
    )
    _user32.SetWindowPos.restype = ctypes.c_bool
    _user32.SetForegroundWindow.argtypes = (ctypes.c_void_p,)
    _user32.SetForegroundWindow.restype = ctypes.c_bool
    _user32.ShowWindow.argtypes = (ctypes.c_void_p, ctypes.c_int)
    _user32.ShowWindow.restype = ctypes.c_bool
    _user32.IsWindow.argtypes = (ctypes.c_void_p,)
    _user32.IsWindow.restype = ctypes.c_bool
    _user32.SetWindowTextW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    _user32.SetWindowTextW.restype = ctypes.c_bool
    _user32.SetLayeredWindowAttributes.argtypes = (
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_ubyte, ctypes.c_uint32,
    )
    _user32.SetLayeredWindowAttributes.restype = ctypes.c_bool
    _user32.GetLayeredWindowAttributes.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(ctypes.c_uint32),
    )
    _user32.GetLayeredWindowAttributes.restype = ctypes.c_bool

    if hasattr(ctypes, "WINFUNCTYPE"):
        # 64 位下窗口句柄为 8 字节，必须使用 LongPtr 版本
        _get_window_long = _user32.GetWindowLongPtrW
        _set_window_long = _user32.SetWindowLongPtrW
    else:  # pragma: no cover - 32 位 Python
        _get_window_long = _user32.GetWindowLongW
        _set_window_long = _user32.SetWindowLongW
    _get_window_long.argtypes = (ctypes.c_void_p, ctypes.c_int)
    _get_window_long.restype = ctypes.c_ssize_t
    _set_window_long.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t)
    _set_window_long.restype = ctypes.c_ssize_t

    _EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
    )
    _user32.EnumWindows.argtypes = (_EnumWindowsProc, ctypes.c_void_p)
    _user32.EnumWindows.restype = ctypes.c_bool
    _user32.GetWindowThreadProcessId.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)
    )
    _user32.GetWindowThreadProcessId.restype = ctypes.c_uint32
    _user32.IsWindowVisible.argtypes = (ctypes.c_void_p,)
    _user32.IsWindowVisible.restype = ctypes.c_bool
    _user32.GetWindowTextLengthW.argtypes = (ctypes.c_void_p,)
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
    _user32.GetWindowTextW.restype = ctypes.c_int


def top_level_hwnd(win_id: int) -> int:
    """把 Tk 等内部窗口句柄转换为顶层窗口句柄（需要时可用于嵌入式窗口）"""
    if not IS_WINDOWS:
        return 0
    root = _user32.GetAncestor(ctypes.c_void_p(win_id), 2)  # GA_ROOT
    return int(root or win_id)


def set_capture_exclusion(hwnd: int, exclude: bool = True) -> bool:
    """设置窗口是否从屏幕捕获（截屏 / 录屏 / 直播）中排除。

    注意：SetWindowDisplayAffinity 只能作用于「当前进程拥有」的顶层窗口，
    因此对另一个进程（浏览器）的窗口调用会失败并返回 False。
    在 native 模式下窗口由本进程创建，运行中可随时切换。
    """
    if not IS_WINDOWS:
        return False
    affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
    ok = _user32.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), affinity)
    if not ok:
        err = ctypes.get_last_error()
        logger.debug("SetWindowDisplayAffinity 失败 (hwnd=%s, err=%s)", hwnd, err)
    return bool(ok)


def get_capture_exclusion(hwnd: int) -> Optional[bool]:
    """读取窗口当前是否已从屏幕捕获中排除；无法确定时返回 None"""
    if not IS_WINDOWS or not hwnd:
        return None
    value = ctypes.c_uint32(0)
    ok = _user32.GetWindowDisplayAffinity(ctypes.c_void_p(hwnd), ctypes.byref(value))
    if not ok:
        return None
    # WDA_EXCLUDEFROMCAPTURE(0x11) 与 WDA_MONITOR(0x01) 都表示“不可被正常捕获”
    return value.value in (WDA_EXCLUDEFROMCAPTURE, WDA_MONITOR)


def set_topmost(hwnd: int, enabled: bool = True) -> bool:
    """窗口置顶（HWND_TOPMOST = -1 / HWND_NOTOPMOST = -2）"""
    if not IS_WINDOWS:
        return False
    hwnd_insert_after = -1 if enabled else -2
    ok = _user32.SetWindowPos(
        ctypes.c_void_p(hwnd), ctypes.c_void_p(hwnd_insert_after),
        0, 0, 0, 0,
        0x0001 | 0x0002 | 0x0010,  # NOSIZE | NOMOVE | NOACTIVATE
    )
    return bool(ok)


def set_taskbar_hidden(hwnd: int, hidden: bool = True) -> bool:
    """隐藏/显示任务栏图标（切换 WS_EX_TOOLWINDOW 扩展样式）。

    关键点：Windows 在窗口「首次显示」时就已向任务栏注册了按钮，
    之后再改 WS_EX_TOOLWINDOW 并不会让已存在的按钮消失 ——
    必须先把窗口隐藏，改完样式再显示，任务栏才会重新判定并移除按钮。
    （仅设置样式而不做隐藏/显示循环，是「任务栏图标没隐藏」的原因。）

    同时保留窗口原有可见性状态，避免把用户手动最小化的窗口强行弹出来。
    """
    if not IS_WINDOWS or not hwnd:
        return False

    hwnd_ptr = ctypes.c_void_p(hwnd)
    was_visible = bool(_user32.IsWindowVisible(hwnd_ptr))

    # 1) 先隐藏，让任务栏移除/重建按钮
    if was_visible:
        _user32.ShowWindow(hwnd_ptr, SW_HIDE)

    # 2) 改扩展样式
    ex_style = int(_get_window_long(hwnd_ptr, GWL_EXSTYLE))
    if hidden:
        ex_style |= WS_EX_TOOLWINDOW
        ex_style &= ~WS_EX_APPWINDOW
    else:
        ex_style &= ~WS_EX_TOOLWINDOW
        ex_style |= WS_EX_APPWINDOW
    _set_window_long(hwnd_ptr, GWL_EXSTYLE, ex_style)

    # 3) 恢复显示；用 ShowWindow 直接显示，避免抢焦点
    if was_visible:
        _user32.ShowWindow(hwnd_ptr, SW_SHOWNA)

    return True


def refresh_taskbar_button(hwnd: int) -> bool:
    """强制任务栏重新注册该窗口的按钮（隐藏→显示）。

    某些情况下窗口在样式生效前就已被任务栏登记，需要再触发一次重建。
    """
    if not IS_WINDOWS or not hwnd:
        return False
    hwnd_ptr = ctypes.c_void_p(hwnd)
    if not _user32.IsWindowVisible(hwnd_ptr):
        return False
    _user32.ShowWindow(hwnd_ptr, SW_HIDE)
    time.sleep(0.05)
    _user32.ShowWindow(hwnd_ptr, SW_SHOWNA)
    return True


def _has_toolwindow_style(hwnd: int) -> bool:
    """检查窗口是否已带上 WS_EX_TOOLWINDOW（用于确认隐藏任务栏图标是否生效）"""
    if not IS_WINDOWS or not hwnd:
        return False
    ex_style = int(_get_window_long(ctypes.c_void_p(hwnd), GWL_EXSTYLE))
    return bool(ex_style & WS_EX_TOOLWINDOW)


def focus_window(hwnd: int) -> bool:
    """把窗口带到前台"""
    if not IS_WINDOWS:
        return False
    _user32.ShowWindow(ctypes.c_void_p(hwnd), SW_RESTORE)
    return bool(_user32.SetForegroundWindow(ctypes.c_void_p(hwnd)))


def set_window_title(hwnd: int, title: str) -> bool:
    """设置窗口标题。

    浏览器的 --app 模式会用页面 <title> 覆盖窗口标题，
    因此自定义标题需要在窗口出现之后由系统 API 直接写入。
    """
    if not IS_WINDOWS or not hwnd or not title:
        return False
    ok = _user32.SetWindowTextW(ctypes.c_void_p(hwnd), title)
    return bool(ok)


def _install_title_keeper(hwnd: int, title: str) -> None:
    """持续保持自定义窗口标题（页面加载完成时会再次改写标题）。"""
    if not IS_WINDOWS or not hwnd or not title:
        return

    def _keeper() -> None:
        # 页面 <title> 在加载完成后才生效，这里在一段时间内反复纠正
        for _ in range(60):  # 约 30 秒
            if not _user32.IsWindow(ctypes.c_void_p(hwnd)):
                return
            set_window_title(hwnd, title)
            time.sleep(0.5)

    threading.Thread(target=_keeper, name="window-title", daemon=True).start()


def clamp_opacity(value: float) -> float:
    """把透明度限制在可用范围内（过低会导致窗口无法操作）"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return MAX_OPACITY
    return max(MIN_OPACITY, min(MAX_OPACITY, number))


def set_window_opacity(hwnd: int, opacity: float) -> bool:
    """设置窗口整体透明度。

    opacity: 0.2 ~ 1.0（1.0 = 完全不透明）

    实现要点：
      * 必须先给窗口加上 WS_EX_LAYERED 扩展样式，否则
        SetLayeredWindowAttributes 会失败（ERROR_INVALID_PARAMETER）；
      * WS_EX_LAYERED 与 WebView2 渲染兼容（实测 alpha 255/180/120/60 均生效）。

    注意：透明度作用于整个顶层窗口，包括标题栏与其中的 WebView 内容。
    """
    if not IS_WINDOWS or not hwnd:
        return False

    opacity = clamp_opacity(opacity)
    alpha = int(round(opacity * 255))
    hwnd_ptr = ctypes.c_void_p(hwnd)

    ex_style = int(_get_window_long(hwnd_ptr, GWL_EXSTYLE))
    if not (ex_style & WS_EX_LAYERED):
        _set_window_long(hwnd_ptr, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)

    ok = _user32.SetLayeredWindowAttributes(hwnd_ptr, 0, alpha, LWA_ALPHA)
    if not ok:
        logger.debug("SetLayeredWindowAttributes 失败 (hwnd=%s, alpha=%s)", hwnd, alpha)
    return bool(ok)


def get_window_opacity(hwnd: int) -> Optional[float]:
    """读取窗口当前透明度（非分层窗口返回 None）"""
    if not IS_WINDOWS or not hwnd:
        return None
    key = ctypes.c_uint32(0)
    alpha = ctypes.c_ubyte(0)
    flags = ctypes.c_uint32(0)
    ok = _user32.GetLayeredWindowAttributes(
        ctypes.c_void_p(hwnd), ctypes.byref(key), ctypes.byref(alpha), ctypes.byref(flags)
    )
    if not ok or not (flags.value & LWA_ALPHA):
        return None
    return alpha.value / 255.0


def find_window_by_pid(pid: int, need_title: bool = False) -> int:
    """在所有顶层窗口中查找属于指定进程（或其后代进程）的窗口。

    浏览器进程会派生多个子进程（GPU / 渲染 / 网络），--app 窗口可能由子进程创建，
    因此这里按「进程树 + 可见性 + 标题」综合匹配。
    """
    if not IS_WINDOWS or pid <= 0:
        return 0

    pids = _process_tree_pids(pid)
    candidates: list[tuple[int, int, str]] = []

    def _callback(hwnd, _lparam):  # noqa: ANN001
        try:
            if not _user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
                return True
            win_pid = ctypes.c_uint32(0)
            _user32.GetWindowThreadProcessId(
                ctypes.c_void_p(hwnd), ctypes.byref(win_pid)
            )
            if win_pid.value not in pids:
                return True
            length = _user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, length + 1)
            title = buf.value
            if need_title and not title:
                return True
            candidates.append((int(hwnd), length, title))
        except Exception:  # pragma: no cover - 枚举过程中的偶发失败可忽略
            pass
        return True

    try:
        _user32.EnumWindows(_EnumWindowsProc(_callback), None)
    except Exception as exc:  # pragma: no cover
        logger.debug("EnumWindows 失败: %s", exc)

    if not candidates:
        return 0
    # 标题最长的一般就是主窗口（辅助窗口通常标题很短或为空）
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0][0]


def _process_tree_pids(root_pid: int) -> set[int]:
    """获取 root_pid 及其所有子孙进程的 PID"""
    pids = {root_pid}
    try:
        import subprocess as _sp
        out = _sp.run(
            ["wmic", "process", "get", "ProcessId,ParentProcessId", "/format:csv"],
            capture_output=True, text=True, timeout=8,
            creationflags=getattr(_sp, "CREATE_NO_WINDOW", 0),
        ).stdout
    except Exception:
        return pids

    children: dict[int, list[int]] = {}
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            parent, child = int(parts[1]), int(parts[2])
        except (ValueError, IndexError):
            continue
        children.setdefault(parent, []).append(child)

    stack = [root_pid]
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            if child not in pids:
                pids.add(child)
                stack.append(child)
    return pids


# ══════════════════════════════════════════════════════════════
# 浏览器 --app 窗口定位
# ══════════════════════════════════════════════════════════════

_CANDIDATE_BROWSERS = [
    # (可执行文件路径, 显示名称)
    (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Google Chrome"),
    (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "Google Chrome"),
    (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "Microsoft Edge"),
    (r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", "Microsoft Edge"),
    (os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"), "Google Chrome"),
    (os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"), "Microsoft Edge"),
]


def _browser_from_env() -> Optional[tuple[str, str]]:
    explicit = os.getenv("DESKTOP_BROWSER") or os.getenv("BROWSER")
    if explicit and os.path.isfile(explicit):
        return explicit, os.path.basename(explicit)
    return None


def _browser_from_path(names: list[str]) -> Optional[tuple[str, str]]:
    for name in names:
        found = shutil.which(name)
        if found:
            return found, name
    return None


def find_browser() -> Optional[tuple[str, str]]:
    """查找可用的 Chromium 内核浏览器（支持 --app 独立窗口模式）"""
    env_browser = _browser_from_env()
    if env_browser:
        return env_browser

    for path, label in _CANDIDATE_BROWSERS:
        if path and os.path.isfile(path):
            return path, label

    return _browser_from_path(["chrome", "msedge", "chromium", "brave", "google-chrome"])


class DesktopWindow:
    """独立窗口 —— 承载完整服务的浏览器 --app 窗口"""

    def __init__(
        self,
        url: str,
        title: str = "面试 Agent",
        width: int = 1280,
        height: int = 800,
        topmost: bool = True,
        capture_exclude: bool = True,
        hide_taskbar: bool = False,
        browser: Optional[str] = None,
        user_data_dir: Optional[str] = None,
        fullscreen: bool = False,
    ):
        self.url = url
        self.title = title
        # 默认标题：与前端页面 <title> 一致，此时无需改写窗口标题
        self._default_title = _DEFAULT_WINDOW_TITLE
        self.width = width
        self.height = height
        self.topmost = topmost
        self.capture_exclude = capture_exclude
        self.hide_taskbar = hide_taskbar
        self.fullscreen = fullscreen
        self.process: Optional[subprocess.Popen] = None
        self.hwnd: int = 0
        self._closed = False

        found = (browser, os.path.basename(browser)) if browser else find_browser()
        if not found:
            raise RuntimeError(
                "未找到可用的浏览器（Chrome / Edge）。\n"
                "独立窗口模式依赖 Chromium 内核的 --app 模式，请安装 Edge 或 Chrome，\n"
                "或通过环境变量 DESKTOP_BROWSER 指定浏览器可执行文件路径。"
            )
        self.browser_path, self.browser_label = found

        if user_data_dir:
            self.user_data_dir = user_data_dir
        else:
            self.user_data_dir = os.path.join(
                os.path.expanduser("~"), ".interview-agent", "desktop-profile"
            )
        os.makedirs(self.user_data_dir, exist_ok=True)

    # ── 命令构造 ──

    def build_command(self) -> list[str]:
        size = f"--window-size={self.width},{self.height}"
        args = [
            self.browser_path,
            f"--app={self.url}",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate,TranslateUI,AutofillServerCommunication",
            "--disable-infobars",
            "--disable-session-crashed-bubble",
            size,
        ]
        if self.fullscreen:
            args.append("--start-fullscreen")
        return args

    # ── 生命周期 ──

    def start(self) -> None:
        cmd = self.build_command()
        logger.info("🪟 启动独立窗口：%s", self.browser_label)
        logger.debug("命令: %s", " ".join(cmd))
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0,
        )

    def apply_window_effects(self, timeout: float = 20.0, interval: float = 0.5) -> bool:
        """等待窗口出现并应用置顶 / 捕获排除 / 隐藏任务栏图标"""
        if not IS_WINDOWS or self.process is None:
            return False

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.process.poll() is not None:
                logger.error("❌ 浏览器窗口在初始化前已退出（code=%s）", self.process.returncode)
                return False
            hwnd = find_window_by_pid(self.process.pid, need_title=True)
            if hwnd:
                self.hwnd = hwnd
                break
            time.sleep(interval)

        if not self.hwnd:
            logger.warning("⚠ 未能定位浏览器窗口句柄，置顶/捕获排除未生效")
            return False

        self._apply_topmost(self.topmost)
        if self.hide_taskbar:
            set_taskbar_hidden(self.hwnd, True)
        self._apply_capture_exclusion()

        # 浏览器 --app 模式会用页面 <title> 覆盖窗口标题，
        # 因此这里在窗口出现后把自定义标题写回（并短暂保持）。
        if self.title and self.title != self._default_title:
            set_window_title(self.hwnd, self.title)
            _install_title_keeper(self.hwnd, self.title)

        logger.info(
            "🪟 窗口已就绪 (HWND=%s)：置顶=%s, 捕获排除=%s, 隐藏任务栏=%s",
            self.hwnd,
            "开" if self.topmost else "关",
            "开" if self.capture_exclude and IS_WINDOWS else "关",
            "开" if self.hide_taskbar else "关",
        )
        return True

    def _apply_topmost(self, enabled: bool) -> None:
        if self.hwnd:
            set_topmost(self.hwnd, enabled)

    def _apply_capture_exclusion(self) -> None:
        """尝试把窗口从屏幕捕获中排除。

        说明：Windows 的 SetWindowDisplayAffinity 只对「当前进程拥有」的窗口生效。
        独立窗口使用的是浏览器进程的窗口，因此跨进程调用通常会被系统拒绝
        （返回 False），此时保持默认可被捕获的状态，不影响正常使用。
        """
        if not IS_WINDOWS or not self.capture_exclude or not self.hwnd:
            return
        if set_capture_exclusion(self.hwnd, True):
            logger.info("🛡 窗口已从屏幕捕获中排除")
        else:
            logger.debug(
                "ℹ 跨进程设置捕获排除失败（系统限制），窗口仍可正常使用"
            )

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def wait(self) -> None:
        if self.process is not None:
            self.process.wait()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.hwnd:
            # 先解除置顶，避免影响后续前台窗口
            set_topmost(self.hwnd, False)
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:  # pragma: no cover
                pass


# ══════════════════════════════════════════════════════════════
# 原生窗口（pywebview + Edge WebView2）
# ══════════════════════════════════════════════════════════════

def is_native_available() -> bool:
    """检查 pywebview 是否可用"""
    try:
        import webview  # noqa: F401
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════
# 前端 ↔ 窗口控制 桥接 API
# ══════════════════════════════════════════════════════════════

class WindowControlApi:
    """暴露给前端 JS 的窗口控制接口（webview.js_api）。

    前端通过 window.pywebview.api.<方法名>(...) 调用，返回 Promise。
    所有方法都返回统一的 dict，便于前端判断成功与否：
        {"ok": bool, "opacity": float, "error": str|None}

    只有在 native 窗口模式下才可用；浏览器模式下 window.pywebview 不存在，
    前端会据此隐藏相关控件。
    """

    def __init__(self, controller: "NativeWindow"):
        self._controller = controller

    # ── 透明度 ──

    def set_opacity(self, value) -> dict:
        """设置窗口透明度，value 取 0.2 ~ 1.0（也可传 20~100 的百分数）"""
        opacity = _parse_opacity_arg(value)
        ctrl = self._controller
        if not ctrl.hwnd:
            return {"ok": False, "opacity": opacity, "error": "窗口句柄尚未就绪"}
        if not set_window_opacity(ctrl.hwnd, opacity):
            return {"ok": False, "opacity": opacity,
                    "error": "设置透明度失败（可能是当前系统或窗口不支持）"}
        ctrl.opacity = opacity
        return {"ok": True, "opacity": opacity, "error": None}

    def get_opacity(self) -> dict:
        ctrl = self._controller
        value = get_window_opacity(ctrl.hwnd) if ctrl.hwnd else None
        if value is None:
            value = ctrl.opacity
        return {"ok": True, "opacity": value, "error": None}

    # ── 其它窗口开关（便于前端统一放置设置项）──

    def set_topmost(self, enabled) -> dict:
        ctrl = self._controller
        ctrl.topmost = _parse_bool_arg(enabled)
        ok = set_topmost(ctrl.hwnd, ctrl.topmost) if ctrl.hwnd else False
        return {"ok": bool(ok), "topmost": ctrl.topmost, "error": None if ok else "设置置顶失败"}

    def set_taskbar_hidden(self, hidden) -> dict:
        """隐藏/显示任务栏图标（运行中即时生效）"""
        ctrl = self._controller
        ctrl.hide_taskbar = _parse_bool_arg(hidden)
        if not ctrl.hwnd:
            return {"ok": False, "hide_taskbar": ctrl.hide_taskbar,
                    "error": "窗口句柄尚未就绪"}
        ok = set_taskbar_hidden(ctrl.hwnd, ctrl.hide_taskbar)
        if ok and ctrl.hide_taskbar:
            # 确认样式确实写入，并再刷新一次任务栏
            if not _has_toolwindow_style(ctrl.hwnd):
                ok = False
            else:
                refresh_taskbar_button(ctrl.hwnd)
        return {"ok": bool(ok), "hide_taskbar": ctrl.hide_taskbar,
                "error": None if ok else "设置任务栏图标失败"}

    def set_capture_exclude(self, exclude) -> dict:
        """从屏幕捕获（截屏 / 录屏）中排除或恢复该窗口（运行中即时生效）"""
        ctrl = self._controller
        want = _parse_bool_arg(exclude)
        if not ctrl.hwnd:
            return {"ok": False, "capture_exclude": ctrl.capture_exclude,
                    "error": "窗口句柄尚未就绪"}
        ok = set_capture_exclusion(ctrl.hwnd, want)
        if ok:
            # 回读确认，避免「返回成功但实际没生效」
            actual = get_capture_exclusion(ctrl.hwnd)
            if actual is not None and actual != want:
                ok = False
            else:
                ctrl.capture_exclude = want
        if not ok:
            return {"ok": False, "capture_exclude": ctrl.capture_exclude,
                    "error": "设置失败：该窗口不支持捕获排除"
                             "（浏览器 --app 模式下窗口属于浏览器进程）"}
        return {"ok": True, "capture_exclude": ctrl.capture_exclude, "error": None}

    def get_state(self) -> dict:
        """返回当前窗口状态，供前端初始化控件。

        透明度同时提供两种单位，避免前后端单位混淆：
            opacity          —— 0.0-1.0 小数（权威值）
            opacity_percent  —— 20-100 整数百分数（便于直接绑定滑块）
        """
        ctrl = self._controller
        value = get_window_opacity(ctrl.hwnd) if ctrl.hwnd else ctrl.opacity
        if value is None:
            value = ctrl.opacity
        # 捕获排除以系统实际状态为准（可能被外部或启动参数改变）
        actual_capture = get_capture_exclusion(ctrl.hwnd) if ctrl.hwnd else None
        if actual_capture is not None:
            ctrl.capture_exclude = actual_capture
        return {
            "ok": True,
            "opacity": value,
            "opacity_percent": int(round(value * 100)),
            "topmost": ctrl.topmost,
            "capture_exclude": ctrl.capture_exclude,
            "capture_supported": actual_capture is not None,
            "hide_taskbar": ctrl.hide_taskbar,
            "min_opacity": MIN_OPACITY,
            "max_opacity": MAX_OPACITY,
            "error": None,
        }

    def close_window(self) -> dict:
        """关闭窗口（前端可提供退出按钮）"""
        try:
            if self._controller.window is not None:
                self._controller.window.destroy()
            return {"ok": True, "error": None}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "error": str(exc)}


def _parse_opacity_arg(value) -> float:
    """解析透明度入参：接受 0.2~1.0 或 20~100（百分数）"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return MAX_OPACITY
    if number > 1.0:  # 视为百分数
        number = number / 100.0
    return clamp_opacity(number)


def _parse_bool_arg(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on", "是", "开")


class NativeWindow:
    """基于 pywebview（Edge WebView2 内核）的独立窗口。

    关键优势：窗口由本进程直接拥有，因此 SetWindowDisplayAffinity
    （从屏幕捕获中排除）能够真正生效 —— 截屏 / 录屏 / 直播看不到窗口内容。
    浏览器 --app 方案因跨进程而做不到这一点。
    """

    def __init__(
        self,
        url: str,
        title: str = _DEFAULT_WINDOW_TITLE,
        width: int = 1280,
        height: int = 800,
        topmost: bool = True,
        capture_exclude: bool = True,
        hide_taskbar: bool = False,
        fullscreen: bool = False,
        debug: bool = False,
        opacity: float = MAX_OPACITY,
    ):
        self.url = url
        self.title = title
        self.width = width
        self.height = height
        self.topmost = topmost
        self.capture_exclude = capture_exclude
        self.hide_taskbar = hide_taskbar
        self.fullscreen = fullscreen
        self.debug = debug
        self.opacity = clamp_opacity(opacity)

        self.window = None
        self.hwnd: int = 0
        self._closed = False
        self._started = threading.Event()
        # 暴露给前端的桥接 API（window.pywebview.api）
        self.api = WindowControlApi(self)

    # ── 生命周期 ──

    def start(self) -> None:
        """创建并显示窗口（阻塞直到窗口关闭）"""
        import webview

        self.window = webview.create_window(
            self.title,
            url=self.url,
            width=self.width,
            height=self.height,
            fullscreen=self.fullscreen,
            min_size=(800, 600),
            confirm_close=False,
            text_select=True,
            js_api=self.api,
        )

        # 窗口就绪后应用窗口特效（置顶 / 捕获排除 / 隐藏任务栏）
        threading.Thread(target=self._apply_effects_when_ready, daemon=True).start()

        # gui='edgechromium' 强制使用 WebView2，保证前端渲染与 Chrome 一致
        webview.start(gui="edgechromium", debug=self.debug)
        self._closed = True

    def _apply_effects_when_ready(self, timeout: float = 20.0) -> None:
        """等待窗口句柄可用后应用特效"""
        if not IS_WINDOWS:
            return
        deadline = time.time() + timeout
        hwnd = 0
        while time.time() < deadline:
            hwnd = self._find_own_hwnd()
            if hwnd:
                break
            time.sleep(0.3)

        if not hwnd:
            logger.warning("⚠ 未定位到原生窗口句柄，置顶/捕获排除未生效")
            return

        self.hwnd = hwnd
        set_topmost(hwnd, self.topmost)
        if self.title:
            set_window_title(hwnd, self.title)

        # 隐藏任务栏图标：必须在窗口已经显示之后做，并且依赖 set_taskbar_hidden
        # 内部的「隐藏→改样式→显示」循环，否则已注册的按钮不会消失。
        taskbar_state = "关"
        if self.hide_taskbar:
            set_taskbar_hidden(hwnd, True)
            # 任务栏可能在窗口首次显示时抢先登记了按钮，这里确认样式并补一次刷新
            if not _has_toolwindow_style(hwnd):
                logger.warning("⚠ 隐藏任务栏图标未生效（样式未写入）")
                taskbar_state = "失败"
            else:
                refresh_taskbar_button(hwnd)
                taskbar_state = "开"

        # 透明度：仅当小于 1.0 时才启用分层窗口（避免无谓地改动窗口样式）
        opacity_state = "100%（不透明）"
        if self.opacity < MAX_OPACITY:
            if set_window_opacity(hwnd, self.opacity):
                opacity_state = f"{int(round(self.opacity * 100))}%"
            else:
                opacity_state = "设置失败"

        capture_state = "关"
        if self.capture_exclude:
            if set_capture_exclusion(hwnd, True):
                capture_state = "开（截图/录屏不可见）"
            else:
                capture_state = "失败（系统拒绝）"

        logger.info(
            "🪟 原生窗口已就绪 (HWND=%s)：置顶=%s, 透明度=%s, 捕获排除=%s, 隐藏任务栏=%s",
            hwnd,
            "开" if self.topmost else "关",
            opacity_state,
            capture_state,
            taskbar_state,
        )
        self._started.set()

    def _find_own_hwnd(self) -> int:
        """查找属于本进程的可见顶层窗口（pywebview 的窗口在本进程内）"""
        # 窗口标题即我们设置的自定义标题，优先精确匹配
        hwnd = find_window_by_pid(os.getpid(), need_title=True)
        return hwnd

    def is_running(self) -> bool:
        return not self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self.hwnd and IS_WINDOWS:
            set_topmost(self.hwnd, False)
        try:
            if self.window is not None:
                self.window.destroy()
        except Exception:  # pragma: no cover
            pass


# ══════════════════════════════════════════════════════════════
# 服务启动辅助
# ══════════════════════════════════════════════════════════════

def _configure_console() -> None:
    """在 Windows 上把标准输出切到 UTF-8。

    Windows 控制台默认使用 GBK，日志中的 emoji（🪟 / 🚀 / ✅）会触发
    UnicodeEncodeError 并被 logging 记为「Logging error」。
    这里显式切换为 UTF-8（失败则退回 ASCII 安全模式）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):  # pragma: no cover
            pass


def _load_fastapi_app():
    """获取 FastAPI 应用实例。

    两种情况：
      1. `python desktop.py`  —— main 尚未被导入，正常 `import main` 即可。
      2. `python main.py --desktop` —— main 正在以 __main__ 身份执行，
         此时不能 `import main`（会得到半初始化的模块，甚至循环导入），
         必须直接读取已在构建中的应用对象。
    """
    import __main__ as main_module

    # 情况 2：main.py 作为脚本运行，app 会挂在 __main__ 上
    app = getattr(main_module, "app", None)
    if app is not None and getattr(main_module, "__file__", "").endswith("main.py"):
        return app

    # 情况 1：以库的方式导入 main
    import main as imported_main

    app = getattr(imported_main, "app", None)
    if app is None:
        raise RuntimeError("未能从 main 模块中获取 FastAPI 应用实例")
    return app


def _wait_for_server(url: str, timeout: float = 60.0, interval: float = 0.4) -> bool:
    """轮询等待 HTTP 服务就绪"""
    import urllib.error
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3):
                return True
        except urllib.error.HTTPError:
            # 有响应即算就绪（4xx/5xx 说明服务已在监听）
            return True
        except Exception:
            time.sleep(interval)
    return False


def _port_available(host: str, port: int) -> bool:
    """检测端口是否可被本进程独占使用。

    注意：Windows 上 SO_REUSEADDR 允许重复绑定同一地址（会「成功」返回），
    因此这里：
      1) 不设置 SO_REUSEADDR，让已被监听的端口直接绑定失败；
      2) 额外尝试 connect 一次，捕获「已被监听但绑定未报错」的边界情况。
    """
    # 先尝试连接：若已有服务在监听，则端口不可用
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        if probe.connect_ex((host, port)) == 0:
            return False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _find_free_port(host: str, start: int, attempts: int = 20) -> int:
    for offset in range(attempts):
        candidate = start + offset
        if _port_available(host, candidate):
            return candidate
    raise RuntimeError(f"在 {start}-{start + attempts - 1} 范围内找不到可用端口")


# ══════════════════════════════════════════════════════════════
# 命令行参数
# ══════════════════════════════════════════════════════════════

def _str2bool(value: str) -> bool:
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in ("1", "true", "yes", "y", "on", "是", "开"):
        return True
    if lowered in ("0", "false", "no", "n", "off", "否", "关"):
        return False
    raise argparse.ArgumentTypeError(f"无法解析布尔值: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="desktop.py",
        description="在独立窗口中启动面试 Agent（后端 + 前端一体）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python desktop.py\n"
            "  python desktop.py --width 1600 --height 900 --no-topmost\n"
            "  python desktop.py --port 8123 --capture-exclude false\n"
            "  python desktop.py --shell browser            # 不依赖 pywebview\n"
            "  python main.py --desktop --window-title \"模拟面试\"\n"
        ),
    )

    # ── 服务参数 ──
    service = parser.add_argument_group("服务参数")
    service.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1，仅本机可访问）")
    service.add_argument("--port", type=int, default=8000, help="服务端口（默认 8000）")
    service.add_argument("--auto-port", type=_str2bool, nargs="?", const=True, default=False,
                         help="端口被占用时自动向后查找可用端口（默认关闭）")
    service.add_argument("--reload", type=_str2bool, nargs="?", const=True, default=False,
                         help="开启热重载（开发用，默认关闭）")

    # ── 窗口参数 ──
    window = parser.add_argument_group("窗口参数")
    window.add_argument("--shell", choices=("auto", "native", "browser"), default="auto",
                        help="窗口实现：native=pywebview 原生窗口（可真正排除屏幕捕获，默认优先）；"
                             "browser=系统浏览器 --app 窗口（零依赖，但捕获排除无效）；"
                             "auto=优先 native，不可用时自动回退 browser")
    window.add_argument("--window-title", default=_DEFAULT_WINDOW_TITLE,
                        help="窗口标题（同时用于任务栏显示）")
    window.add_argument("--width", type=int, default=1280, help="窗口宽度（默认 1280）")
    window.add_argument("--height", type=int, default=800, help="窗口高度（默认 800）")
    window.add_argument("--topmost", type=_str2bool, nargs="?", const=True, default=True,
                        help="窗口置顶（默认开启，用 --topmost false 关闭）")
    window.add_argument("--no-topmost", dest="topmost", action="store_false",
                        help="等价于 --topmost false")
    window.add_argument("--capture-exclude", type=_str2bool, nargs="?", const=True, default=True,
                        help="从屏幕捕获（截屏/录屏）中排除窗口（默认开启；仅 native 窗口真正生效）")
    window.add_argument("--fullscreen", type=_str2bool, nargs="?", const=True, default=False,
                        help="全屏启动窗口（默认关闭）")
    window.add_argument("--app", dest="app_path", default="",
                        help="启动后自动打开的页面路径，如 /login（默认打开首页）")
    window.add_argument("--browser", default="",
                        help="[browser 模式] 指定浏览器可执行文件路径（默认自动查找 Edge / Chrome）")
    window.add_argument("--user-data-dir", default="",
                        help="[browser 模式] 浏览器用户数据目录（默认 ~/.interview-agent/desktop-profile）")
    window.add_argument("--hide-taskbar", type=_str2bool, nargs="?", const=True, default=False,
                        help="隐藏任务栏图标（默认关闭）")
    window.add_argument("--opacity", type=float, default=MAX_OPACITY,
                        help=f"窗口透明度 {MIN_OPACITY}-{MAX_OPACITY}（1.0=不透明，默认 1.0）；"
                             f"也可传 20-100 的百分数，运行中可在界面顶栏拖动滑块调整")
    window.add_argument("--debug", type=_str2bool, nargs="?", const=True, default=False,
                        help="[native 模式] 开启 WebView 开发者工具与调试日志（默认关闭）")

    # ── 其他 ──
    parser.add_argument("--no-console", type=_str2bool, nargs="?", const=True, default=False,
                        help="不输出启动日志（适合无控制台的打包运行）")
    parser.add_argument("--open-timeout", type=float, default=90.0,
                        help="等待服务就绪的最长秒数（默认 90）")
    return parser


# ══════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════

def run_desktop(args: argparse.Namespace) -> int:
    """以独立窗口模式启动应用（阻塞直到窗口关闭）"""
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    _configure_console()

    if not args.no_console:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )

    # 独立窗口模式固定使用桌面配置（可被 .env 覆盖）
    os.environ.setdefault("DESKTOP_MODE", "true")
    os.environ.setdefault("HOST", args.host)
    os.environ.setdefault("PORT", str(args.port))

    logger.info("=" * 56)
    logger.info("  面试 Agent — 独立窗口模式")
    logger.info("=" * 56)

    # ── 1. 选择端口 ──
    host, port = args.host, args.port
    if not _port_available(host, port):
        if args.auto_port:
            port = _find_free_port(host, port)
            logger.warning("⚠ 端口 %s 已被占用，自动改用 %s", args.port, port)
        else:
            logger.error(
                "❌ 端口 %s 已被占用。请关闭占用该端口的程序，"
                "或使用 --port 指定其他端口 / --auto-port 自动选择。", port
            )
            return 1
    os.environ["PORT"] = str(port)

    # ── 2. 检查前端构建产物 ──
    root = os.path.dirname(os.path.abspath(__file__))
    dist_index = os.path.join(root, "frontend", "dist", "index.html")
    if not os.path.isfile(dist_index):
        logger.error(
            "❌ 未找到前端构建产物: %s\n"
            "   请先执行:  cd frontend  &&  npm install  &&  npm run build", dist_index
        )
        return 1
    logger.info("📦 前端构建产物: %s", os.path.dirname(dist_index))

    # ── 3. 启动后端服务（含前端静态托管）──
    #    注意：必须在独立线程中启动 uvicorn。
    #    uvicorn 的信号处理要求运行在主线程，非主线程会自动跳过安装 signal handler。
    import uvicorn

    try:
        fastapi_app = _load_fastapi_app()
    except Exception as exc:
        logger.error("❌ 后端模块加载失败: %s: %s", type(exc).__name__, exc)
        logger.error("   请检查依赖是否完整（pip install -r requirements.txt）"
                     "以及 .env 配置是否正确。")
        logger.debug("导入 main 失败详情", exc_info=True)
        return 1

    config = uvicorn.Config(
        fastapi_app,
        host=host,
        port=port,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        reload=bool(args.reload),
        access_log=False,
    )
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, name="uvicorn-server", daemon=True)
    server_thread.start()

    base_url = f"http://{host}:{port}"
    if not _wait_for_server(base_url + "/", timeout=args.open_timeout):
        logger.error("❌ 服务启动超时（%s 秒），请检查上方日志。", args.open_timeout)
        server.should_exit = True
        return 1
    logger.info("🚀 服务已就绪: %s", base_url)

    # ── 4. 打开独立窗口 ──
    url = base_url + (args.app_path if args.app_path.startswith("/") or not args.app_path else "/" + args.app_path)

    shell = args.shell
    if shell == "auto":
        shell = "native" if (IS_WINDOWS and is_native_available()) else "browser"
        if shell == "browser" and args.capture_exclude:
            logger.warning(
                "⚠ 未检测到 pywebview，回退到浏览器窗口模式 ——"
                "该模式下「捕获排除」受系统限制无法生效（窗口属于浏览器进程）。"
            )

    if shell == "native":
        if not is_native_available():
            logger.error("❌ 未安装 pywebview，无法使用 native 窗口。"
                         "请执行: pip install pywebview")
            server.should_exit = True
            return 1
        if not IS_WINDOWS:
            logger.warning("⚠ native 窗口的「置顶 / 捕获排除」仅在 Windows 上生效。")
        logger.info("🧩 窗口实现: native（pywebview / Edge WebView2）")
        window = NativeWindow(
            url=url,
            title=args.window_title,
            width=args.width,
            height=args.height,
            topmost=args.topmost,
            capture_exclude=args.capture_exclude,
            hide_taskbar=args.hide_taskbar,
            fullscreen=args.fullscreen,
            debug=args.debug,
            opacity=_parse_opacity_arg(args.opacity),
        )
        logger.info("ℹ 关闭窗口或按 Ctrl+C 即可退出应用")
        try:
            # 阻塞直到窗口关闭（webview.start 内部运行 GUI 事件循环）
            window.start()
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在退出...")
        except Exception as exc:
            logger.error("❌ 原生窗口运行失败: %s", exc)
            logger.info("   可改用浏览器窗口重试:  python desktop.py --shell browser")
            window.close()
            server.should_exit = True
            server_thread.join(timeout=10)
            return 1
        finally:
            window.close()
            server.should_exit = True
            server_thread.join(timeout=10)
        logger.info("👋 已退出")
        return 0

    # ── browser 模式 ──
    logger.info("🧩 窗口实现: browser（系统浏览器 --app）")
    if args.capture_exclude:
        logger.info("ℹ 浏览器窗口属于浏览器进程，系统不允许跨进程排除屏幕捕获，"
                    "该设置不会生效（置顶仍然可用）。")
    window = DesktopWindow(
        url=url,
        title=args.window_title,
        width=args.width,
        height=args.height,
        topmost=args.topmost,
        capture_exclude=args.capture_exclude,
        hide_taskbar=args.hide_taskbar,
        browser=args.browser or None,
        user_data_dir=args.user_data_dir or None,
        fullscreen=args.fullscreen,
    )

    try:
        window.start()
    except Exception as exc:
        logger.error("❌ 打开独立窗口失败: %s", exc)
        logger.info("   回退方案：请手动在浏览器中访问 %s", base_url)
        server.should_exit = True
        return 1

    # 窗口特效在后台应用（等待窗口出现期间不阻塞服务）
    threading.Thread(
        target=window.apply_window_effects, name="window-effects", daemon=True
    ).start()

    logger.info("ℹ 关闭窗口或按 Ctrl+C 即可退出应用")

    # ── 5. 阻塞直到窗口关闭 / 用户中断 ──
    try:
        while window.is_running():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在退出...")
    finally:
        window.close()
        server.should_exit = True
        server_thread.join(timeout=10)
        logger.info("👋 已退出")

    return 0


def _load_dotenv_early() -> None:
    """尽早加载 .env，使 DESKTOP_* / HOST / PORT 等配置在解析参数前可用。

    config.py 也会调用 load_dotenv()，但那是后续导入时才发生；
    窗口参数的默认值需要在解析命令行时就能读到，因此这里提前加载一次。
    load_dotenv 默认不覆盖已存在的环境变量，重复调用是安全的。
    """
    try:
        from dotenv import load_dotenv

        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        load_dotenv(env_path)
    except Exception as exc:  # pragma: no cover - .env 缺失或 dotenv 未安装
        logger.debug("加载 .env 失败（可忽略）: %s", exc)


def _apply_env_defaults(args: argparse.Namespace) -> None:
    """用 .env 中的 DESKTOP_* 配置补齐命令行未显式指定的窗口参数。

    命令行优先级最高：只有当用户没有传入对应开关时，才采用 .env 的值。
    """
    explicit = sys.argv[1:] + list(_EXPLICIT_ARGS)
    took_arg = _explicit_arg_names(explicit)

    def env_bool(name: str, fallback: bool) -> bool:
        raw = os.getenv(name)
        if raw is None or raw == "":
            return fallback
        try:
            return _str2bool(raw)
        except argparse.ArgumentTypeError:
            logger.warning("⚠ %s 的值无法解析为布尔值: %r（已忽略）", name, raw)
            return fallback

    def env_int(name: str, fallback: int) -> int:
        raw = os.getenv(name)
        if raw is None or raw == "":
            return fallback
        try:
            return int(raw)
        except ValueError:
            logger.warning("⚠ %s 的值无法解析为整数: %r（已忽略）", name, raw)
            return fallback

    if "width" not in took_arg:
        args.width = env_int("DESKTOP_WIDTH", args.width)
    if "height" not in took_arg:
        args.height = env_int("DESKTOP_HEIGHT", args.height)
    if "topmost" not in took_arg:
        args.topmost = env_bool("DESKTOP_TOPMOST", args.topmost)
    if "capture_exclude" not in took_arg:
        args.capture_exclude = env_bool("DESKTOP_CAPTURE_EXCLUDE", args.capture_exclude)
    if "hide_taskbar" not in took_arg:
        args.hide_taskbar = env_bool("DESKTOP_HIDE_TASKBAR", args.hide_taskbar)
    if "host" not in took_arg:
        args.host = os.getenv("HOST") or args.host
    if "port" not in took_arg:
        raw_port = os.getenv("PORT")
        if raw_port:
            try:
                args.port = int(raw_port)
            except ValueError:
                logger.warning("⚠ PORT 的值无法解析为整数: %r（已忽略）", raw_port)
    if "browser" not in took_arg and not args.browser:
        args.browser = os.getenv("DESKTOP_BROWSER", "")
    if "opacity" not in took_arg:
        raw_opacity = os.getenv("DESKTOP_OPACITY")
        if raw_opacity:
            args.opacity = _parse_opacity_arg(raw_opacity)


def _explicit_arg_names(argv: list[str]) -> set[str]:
    """把命令行中出现的开关映射为参数名集合（dest 名）。"""
    parser = build_parser()
    names: set[str] = set()
    option_to_dest = {}
    for action in parser._actions:  # noqa: SLF001 - 需要读取内部映射
        for opt in action.option_strings:
            option_to_dest[opt] = action.dest
    for token in argv:
        key = token.split("=", 1)[0]
        if key in option_to_dest:
            names.add(option_to_dest[key])
    return names


def main(argv: Optional[list[str]] = None) -> int:
    _configure_console()
    _load_dotenv_early()
    _EXPLICIT_ARGS.clear()
    if argv is not None:
        _EXPLICIT_ARGS.extend(argv)
    args = build_parser().parse_args(argv)
    _apply_env_defaults(args)

    if not IS_WINDOWS:
        logger.warning("⚠ 独立窗口模式的「置顶 / 捕获排除」仅支持 Windows，"
                       "其他系统仍可使用 --app 窗口。")

    try:
        return run_desktop(args)
    except RuntimeError as exc:
        logging.getLogger("desktop").error("❌ %s", exc)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())