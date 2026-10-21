"""系统托盘图标 — 纯 ctypes 实现（不引入第三方依赖）

为什么需要它
------------
桌面版的目标是「界面上只有一个窗口」。但那个窗口本身是 pywebview 创建的原生
窗口，一旦隐藏，用户就没有任何可点的地方 —— 既看不到应用在运行，也无法退出。
托盘图标补上这个缺口：

    单击       显示 / 隐藏主窗口
    右键       菜单：显示/隐藏、打开日志、退出
    首次出现   气泡提示一次「已最小化到托盘」

为什么不用 pystray
------------------
pystray 会连带引入新依赖，而它底层做的事情（Shell_NotifyIcon + 消息窗口 +
TrackPopupMenu）本项目已经在 desktop.py 里用 ctypes 做过同类窗口操作
（置顶、捕获排除、隐藏任务栏）。因此这里沿用同一套 `_user32` 风格自己实现，
不额外增加安装体积与版本风险。

实现要点
--------
* Shell_NotifyIcon 需要一个「能收消息的窗口句柄」，所以这里注册一个窗口类、
  建一个 message-only 窗口（HWND_MESSAGE 作父窗口），托盘事件通过
  uCallbackMessage（WM_APP+1）投递到它。
* 消息循环跑在**独立线程**里：pywebview 的 GUI 事件循环占着主线程，
  而 GetMessage 必须在自己的线程里阻塞等待。
* WndProc 是 ctypes 回调，必须持有引用（否则会被 GC 回收，回调变成空指针）；
  这里用模块级变量 `_wndproc_ref` 保住它。
* 回调（显示/隐藏/退出）运行在托盘线程上，因此调用方必须保证线程安全：
  显示/隐藏走 Win32 ShowWindow（任意线程可用），退出走 pywebview 的
  window.destroy()（该用法在 desktop.py 的 JS API 里已有先例）。

非 Windows 平台：`available()` 返回 False，`start()` 直接返回 False，不影响
应用其余功能（桌面壳本来就只在 Windows 上启用）。
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from ctypes import wintypes
from typing import Callable, Optional

logger = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"

# ── 常量 ──
WM_APP = 0x8000
WM_TRAY_CALLBACK = WM_APP + 1
WM_COMMAND = 0x0111
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_NULL = 0x0000

WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
LR_DEFAULTSIZE = 0x00000040

# message-only 窗口的父句柄。必须用有符号 64 位表示 -3（HWND_MESSAGE），
# 直接传 c_void_p(-3) 会因为 argtypes 是 HWND（无符号）而 OverflowError。
HWND_MESSAGE = -3

# 菜单命令 ID
CMD_TOGGLE = 1001
CMD_SHOW = 1002
CMD_HIDE = 1003
CMD_OPEN_LOG = 1004
CMD_QUIT = 1005

_IDI_APPLICATION = 32512


def available() -> bool:
    """托盘图标是否可用（当前仅 Windows 实现）"""
    return IS_WINDOWS


if IS_WINDOWS:

    class _WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("style", wintypes.UINT),
            ("lpfnWndProc", ctypes.c_void_p),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
            ("hIconSm", wintypes.HICON),
        ]

    class _NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", ctypes.c_byte * 16),
            ("hBalloonIcon", wintypes.HICON),
        ]

    _WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
        wintypes.WPARAM, wintypes.LPARAM,
    )
    _wndproc_ref: list = []  # 保住回调引用，防止被 GC

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # 显式声明签名：不声明时 ctypes 会把句柄当 32 位 int 截断，
    # 在 64 位进程里表现为「调用成功但句柄错乱」或参数溢出。
    _user32.CreateWindowExW.argtypes = (
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
    )
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.DefWindowProcW.argtypes = (
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    )
    _user32.DefWindowProcW.restype = ctypes.c_void_p
    _user32.DestroyWindow.argtypes = (wintypes.HWND,)
    _user32.DestroyWindow.restype = wintypes.BOOL
    _user32.LoadImageW.argtypes = (
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    )
    _user32.LoadImageW.restype = wintypes.HANDLE
    _user32.CreatePopupMenu.restype = wintypes.HMENU
    _user32.AppendMenuW.argtypes = (
        wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR,
    )
    _user32.TrackPopupMenu.argtypes = (
        wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, wintypes.HWND, ctypes.c_void_p,
    )
    _user32.TrackPopupMenu.restype = wintypes.BOOL
    _user32.GetMessageW.argtypes = (
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
    )
    _user32.GetMessageW.restype = ctypes.c_int
    _user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
    _user32.TranslateMessage.restype = wintypes.BOOL
    _user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
    _user32.DispatchMessageW.restype = ctypes.c_void_p
    _user32.PostQuitMessage.argtypes = (ctypes.c_int,)
    _user32.PostQuitMessage.restype = None
    _user32.RegisterClassExW.argtypes = (ctypes.POINTER(_WNDCLASSEXW),)
    _user32.RegisterClassExW.restype = wintypes.WORD
    _user32.PostMessageW.argtypes = (
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    )
    _user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    _kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    _shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.c_void_p)
    _shell32.Shell_NotifyIconW.restype = wintypes.BOOL


class TrayIcon:
    """系统托盘图标

    Args:
        tooltip: 悬停提示文字（≤127 字符）
        icon_path: .ico 文件路径；不存在时退化为系统默认图标
        on_toggle: 单击图标时调用，返回「切换后窗口是否可见」
        on_open_log: 菜单「打开日志」回调
        on_quit: 菜单「退出」回调
        title: 气泡提示标题
        balloon: 首次注册时展示的气泡内容（None 表示不展示）
    """

    _CLASS_NAME = "InterviewAgentTrayWnd"

    def __init__(
        self,
        tooltip: str = "Interview Agent",
        icon_path: Optional[str] = None,
        on_toggle: Optional[Callable[[], bool]] = None,
        on_open_log: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        title: str = "Interview Agent",
        balloon: Optional[str] = None,
    ):
        self.tooltip = tooltip[:127]
        self.icon_path = icon_path if icon_path and os.path.exists(icon_path) else None
        self.on_toggle = on_toggle
        self.on_open_log = on_open_log
        self.on_quit = on_quit
        self.title = title
        self.balloon = balloon

        self._hwnd: Optional[int] = None
        self._hicon: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._window_visible = True

    # ── 对外接口 ──

    def start(self) -> bool:
        """在后台线程注册托盘图标；返回是否注册成功"""
        if not available():
            logger.info("ℹ 非 Windows 平台，跳过托盘图标")
            return False
        if self._thread is not None:
            return True

        self._thread = threading.Thread(target=self._run, name="tray-icon", daemon=True)
        self._thread.start()
        # 等待注册结果（最多 5 秒），便于启动日志明确写出成功/失败
        if not self._ready.wait(timeout=5.0):
            logger.warning("⚠ 托盘图标注册超时")
            return False
        return self._registered

    def stop(self) -> None:
        """注销托盘图标并结束消息循环"""
        self._stop.set()
        if self._hwnd:
            try:
                _user32.PostMessageW(wintypes.HWND(self._hwnd), WM_CLOSE, 0, 0)
            except Exception:  # pragma: no cover
                pass
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def set_tooltip(self, text: str) -> None:
        """更新悬停提示（窗口显示/隐藏状态变化时用）"""
        self.tooltip = text[:127]
        if self._hwnd:
            self._notify(NIM_MODIFY, with_info=False)

    def update_visibility(self, visible: bool) -> None:
        """告诉托盘当前窗口是否可见（决定菜单里显示「显示」还是「隐藏」）"""
        self._window_visible = bool(visible)

    # ── 内部实现 ──

    _registered = False

    def _run(self) -> None:
        try:
            self._create_window()
            self._load_icon()
            self._registered = self._notify(NIM_ADD, with_info=bool(self.balloon))
            if not self._registered:
                logger.warning(
                    "⚠ 托盘图标注册失败（Shell_NotifyIcon error=%s）",
                    ctypes.get_last_error(),
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("⚠ 托盘图标初始化失败: %s", exc)
            self._registered = False
        finally:
            self._ready.set()

        if not self._registered:
            return

        # 消息循环：GetMessage 返回 0 表示收到 WM_QUIT
        msg = wintypes.MSG()
        try:
            while not self._stop.is_set():
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret in (0, -1):
                    break
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self._cleanup()

    def _create_window(self) -> None:
        hinstance = _kernel32.GetModuleHandleW(None)
        wc = _WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)

        # 必须同时保住 **回调对象本身**，而不是它 cast 出来的 c_void_p。
        # 只存 c_void_p 的话，_WNDPROC 实例会被 GC 回收 → Windows 之后调用的是
        # 已释放的跳板代码 → 访问冲突（实测：进程跑几十秒后无栈崩溃，
        # faulthandler 指向 GetMessageW 内部，Thread 停在托盘线程）。
        self._wndproc_obj = _WNDPROC(self._make_wndproc())
        _wndproc_ref.append(self._wndproc_obj)          # 模块级兜底
        wc.lpfnWndProc = ctypes.cast(self._wndproc_obj, ctypes.c_void_p)

        wc.hInstance = hinstance
        wc.lpszClassName = self._CLASS_NAME

        atom = _user32.RegisterClassExW(ctypes.byref(wc))
        if not atom and ctypes.get_last_error() != 1410:  # 1410 = 类已存在
            raise OSError(f"RegisterClassExW 失败: {ctypes.get_last_error()}")

        hwnd = _user32.CreateWindowExW(
            0, self._CLASS_NAME, self._CLASS_NAME, 0,
            0, 0, 0, 0, wintypes.HWND(HWND_MESSAGE), None, hinstance, None,
        )
        if not hwnd:
            raise OSError(f"CreateWindowExW 失败: {ctypes.get_last_error()}")
        self._hwnd = int(hwnd)

    def _load_icon(self) -> None:
        if self.icon_path:
            handle = _user32.LoadImageW(
                None, self.icon_path, IMAGE_ICON, 0, 0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE,
            )
            if handle:
                self._hicon = int(handle)
                return
            logger.warning("⚠ 托盘图标文件加载失败，改用系统默认图标: %s", self.icon_path)
        self._hicon = int(_user32.LoadIconW(None, wintypes.LPCWSTR(_IDI_APPLICATION)))

    def _notify(self, action: int, with_info: bool = False) -> bool:
        if not self._hwnd:
            return False
        nid = _NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATAW)
        nid.hWnd = wintypes.HWND(self._hwnd)
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY_CALLBACK
        nid.hIcon = wintypes.HICON(self._hicon or 0)
        nid.szTip = self.tooltip
        if with_info and self.balloon:
            nid.uFlags |= NIF_INFO
            nid.szInfo = self.balloon
            nid.szInfoTitle = self.title
            nid.dwInfoFlags = 0x00000001  # NIIF_INFO
        return bool(_shell32.Shell_NotifyIconW(action, ctypes.byref(nid)))

    def _cleanup(self) -> None:
        try:
            if self._hwnd and self._registered:
                self._notify(NIM_DELETE)
        except Exception:  # pragma: no cover
            pass
        try:
            if self._hwnd:
                _user32.DestroyWindow(wintypes.HWND(self._hwnd))
        except Exception:  # pragma: no cover
            pass
        self._hwnd = None

    def _show_menu(self) -> None:
        """在鼠标位置弹出右键菜单（TPM_RETURNCMD 直接拿到选中的命令 ID）"""
        menu = _user32.CreatePopupMenu()
        if not menu:
            return
        try:
            # 可见时给「隐藏窗口」，不可见时给「显示窗口」，避免用户猜
            if self._window_visible:
                _user32.AppendMenuW(menu, MF_STRING, CMD_HIDE, "隐藏窗口")
            else:
                _user32.AppendMenuW(menu, MF_STRING, CMD_SHOW, "显示窗口")
            _user32.AppendMenuW(menu, MF_STRING, CMD_TOGGLE, "切换显示/隐藏")
            _user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            _user32.AppendMenuW(menu, MF_STRING, CMD_OPEN_LOG, "打开日志")
            _user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            _user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, "退出")

            pt = wintypes.POINT()
            _user32.GetCursorPos(ctypes.byref(pt))
            # TrackPopupMenu 前必须把本窗口设为前台，否则菜单点外面不会消失
            _user32.SetForegroundWindow(wintypes.HWND(self._hwnd))
            cmd = _user32.TrackPopupMenu(
                menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                pt.x, pt.y, 0, wintypes.HWND(self._hwnd), None,
            )
            _user32.PostMessageW(wintypes.HWND(self._hwnd), WM_NULL, 0, 0)
        finally:
            _user32.DestroyMenu(menu)

        if cmd:
            self._handle_command(int(cmd))

    def _handle_command(self, cmd: int) -> None:
        if cmd in (CMD_TOGGLE, CMD_SHOW, CMD_HIDE):
            self._toggle(force_show=cmd == CMD_SHOW, force_hide=cmd == CMD_HIDE)
        elif cmd == CMD_OPEN_LOG:
            if self.on_open_log:
                try:
                    self.on_open_log()
                except Exception as exc:  # pragma: no cover
                    logger.warning("打开日志失败: %s", exc)
        elif cmd == CMD_QUIT:
            logger.info("🖱 托盘菜单：退出")
            if self.on_quit:
                try:
                    self.on_quit()
                except Exception as exc:  # pragma: no cover
                    logger.warning("退出回调失败: %s", exc)

    def _toggle(self, force_show: bool = False, force_hide: bool = False) -> None:
        if self.on_toggle is None:
            return
        try:
            if force_show:
                self.on_toggle(True)
            elif force_hide:
                self.on_toggle(False)
            else:
                self.on_toggle(None)
        except Exception as exc:  # pragma: no cover
            logger.warning("切换窗口显示状态失败: %s", exc)

    def _make_wndproc(self):
        """返回**未包装**的窗口过程函数（由 _create_window 包装并持有引用）"""
        def _proc(hwnd, msg, wparam, lparam):
            if msg == WM_TRAY_CALLBACK:
                event = lparam & 0xFFFF
                if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self._toggle()
                elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._show_menu()
                return 0
            if msg == WM_CLOSE:
                _user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                _user32.PostQuitMessage(0)
                return 0
            return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        return _proc
