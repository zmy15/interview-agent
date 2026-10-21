"""系统托盘图标测试

托盘本身依赖真实的 Windows Shell（Shell_NotifyIcon / 消息循环），
无法在 CI 里完整跑；这里覆盖的是**不依赖 Shell 的逻辑**以及几个
曾经真的出过问题的边界：

  * ctypes 回调的生命周期（曾导致进程跑几十秒后访问冲突崩溃）
  * 钉住的常量与结构体尺寸（写错会静默失败）
  * 非 Windows 平台与图标缺失时的降级
  * TrayController 的显隐/退出编排（用假 window 对象验证调用次序）
"""

import sys

import pytest

from services import tray as tray_mod

IS_WINDOWS = sys.platform == "win32"


class TestTrayAvailability:
    def test_available_matches_platform(self):
        assert tray_mod.available() == IS_WINDOWS

    @pytest.mark.skipif(not IS_WINDOWS, reason="仅 Windows 有托盘实现")
    def test_non_windows_guard_is_cheap(self):
        # available() 必须是纯判断，不能有副作用（启动路径会先问它）
        assert tray_mod.available() in (True, False)


@pytest.mark.skipif(not IS_WINDOWS, reason="仅 Windows 有托盘实现")
class TestWindowsConstants:
    """常量写错不会报错、只会静默失效，因此钉住它们"""

    def test_message_and_notify_constants(self):
        assert tray_mod.WM_APP == 0x8000
        assert tray_mod.WM_TRAY_CALLBACK == 0x8001
        assert tray_mod.NIM_ADD == 0
        assert tray_mod.NIM_MODIFY == 1
        assert tray_mod.NIM_DELETE == 2
        assert tray_mod.NIF_MESSAGE == 1
        assert tray_mod.NIF_ICON == 2
        assert tray_mod.NIF_TIP == 4

    def test_menu_command_ids_are_distinct(self):
        ids = [
            tray_mod.CMD_TOGGLE, tray_mod.CMD_SHOW, tray_mod.CMD_HIDE,
            tray_mod.CMD_OPEN_LOG, tray_mod.CMD_QUIT,
        ]
        assert len(set(ids)) == len(ids)

    def test_hwnd_message_is_signed(self):
        """HWND_MESSAGE 是 -3；存成 c_void_p 会 OverflowError（曾踩过）"""
        assert tray_mod.HWND_MESSAGE == -3

    def test_struct_sizes_are_plausible(self):
        # cbSize 传错会让 Shell_NotifyIcon / RegisterClassExW 直接失败。
        # 两个结构体的 cbSize 都是构造后由代码填的（不是默认值），
        # 因此这里校验的是 sizeof 是否落在合理范围。
        import ctypes

        nid_size = ctypes.sizeof(tray_mod._NOTIFYICONDATAW)
        wc_size = ctypes.sizeof(tray_mod._WNDCLASSEXW)
        assert nid_size > 500, f"NOTIFYICONDATAW 尺寸异常: {nid_size}"
        assert 40 < wc_size < 200, f"WNDCLASSEXW 尺寸异常: {wc_size}"


@pytest.mark.skipif(not IS_WINDOWS, reason="仅 Windows 有托盘实现")
class TestCallbackLifetime:
    """回归测试：WNDPROC 回调必须一直被强引用

    曾经只保存了 ctypes.cast(...) 出来的 c_void_p，_WNDPROC 实例随即被 GC 回收，
    Windows 之后调用到已释放的跳板 → "Windows fatal exception: access violation"，
    且崩溃点看起来在 GetMessageW 内部，极难定位。
    """

    def test_wndproc_kept_alive_by_instance_and_module(self):
        tray = tray_mod.TrayIcon(tooltip="测试")
        tray._create_window()
        try:
            # 实例上必须持有包装后的回调对象本身（不是 c_void_p）
            assert hasattr(tray, "_wndproc_obj")
            assert isinstance(tray._wndproc_obj, tray_mod._WNDPROC)
            # 模块级列表作为额外兜底
            assert tray._wndproc_obj in tray_mod._wndproc_ref
            assert tray._hwnd, "message-only 窗口应创建成功"
        finally:
            tray._cleanup()

    def test_callback_survives_gc(self):
        import gc

        tray = tray_mod.TrayIcon(tooltip="测试")
        tray._create_window()
        try:
            ref = tray._wndproc_obj
            gc.collect()
            # 强制回收后引用仍在（这正是当年缺的一步）
            assert tray._wndproc_obj is ref
        finally:
            tray._cleanup()


class TestTrayIconDegradation:
    def test_missing_icon_file_falls_back(self):
        """图标文件不存在时不应抛异常（退化为系统默认图标）"""
        tray = tray_mod.TrayIcon(icon_path="不存在的图标.ico")
        assert tray.icon_path is None

    def test_tooltip_is_truncated(self):
        """szTip 只有 128 字符，超长会让 Shell_NotifyIcon 失败"""
        tray = tray_mod.TrayIcon(tooltip="长" * 300)
        assert len(tray.tooltip) == 127

    def test_stop_without_start_is_safe(self):
        tray = tray_mod.TrayIcon()
        tray.stop()  # 不应抛异常
        tray.set_tooltip("无所谓")  # 未注册时应静默忽略

    def test_update_visibility_tracks_state(self):
        tray = tray_mod.TrayIcon()
        tray.update_visibility(False)
        assert tray._window_visible is False
        tray.update_visibility(True)
        assert tray._window_visible is True

    def test_handle_command_ignores_unknown(self):
        tray = tray_mod.TrayIcon()
        tray._handle_command(999999)  # 未知命令不应抛异常

    def test_toggle_without_callback_is_safe(self):
        tray = tray_mod.TrayIcon(on_toggle=None)
        tray._toggle()  # 无回调时不应抛异常


class FakeWindow:
    """假窗口：记录托盘对它的每一次操作"""

    def __init__(self, hwnd=1234, visible=True):
        self.hwnd = hwnd
        self._visible = visible
        self.taskbar_calls = []
        self.closed = 0

    def apply_taskbar_visibility(self, hidden):
        self.taskbar_calls.append(hidden)
        return True

    def close(self):
        self.closed += 1

    def is_running(self):
        return self.closed == 0


class TestTrayController:
    """TrayController 的编排逻辑（不依赖真实 Shell）"""

    def _make(self, monkeypatch, window, tray_start_ok=True):
        from desktop import TrayController

        made = {}

        class FakeTray:
            def __init__(self, **kwargs):
                made.update(kwargs)
                self.visibility = []
                self.tooltips = []
                self.stopped = 0

            def start(self):
                return tray_start_ok

            def stop(self):
                self.stopped += 1

            def update_visibility(self, v):
                self.visibility.append(v)

            def set_tooltip(self, t):
                self.tooltips.append(t)

        monkeypatch.setattr(tray_mod, "TrayIcon", FakeTray)
        monkeypatch.setattr(tray_mod, "available", lambda: True)
        ctrl = TrayController(window, log_path=None)
        # 屏蔽等待 hwnd 的后台线程，让用例保持同步
        monkeypatch.setattr(ctrl, "_sync_visibility_when_ready", lambda *a, **k: None)
        return ctrl, made

    def test_start_passes_our_callbacks(self, monkeypatch):
        ctrl, made = self._make(monkeypatch, FakeWindow())
        assert ctrl.start() is True
        assert made["on_toggle"] == ctrl._on_toggle
        assert made["on_quit"] == ctrl._request_quit
        assert "显示" in made["tooltip"] and "隐藏" in made["tooltip"]
        assert made["balloon"], "首次注册应带气泡提示，否则用户不知道图标在哪"

    def test_toggle_hides_then_taskbar_follows(self, monkeypatch):
        """隐藏窗口时必须先把任务栏按钮摘掉（否则留下点不开的死按钮）"""
        import desktop

        window = FakeWindow(visible=True)
        ctrl, _ = self._make(monkeypatch, window)
        ctrl.start()

        monkeypatch.setattr(desktop, "is_window_visible", lambda hwnd: True)
        monkeypatch.setattr(desktop, "hide_window", lambda hwnd: True)

        result = ctrl._on_toggle()
        assert result is False, "可见时切换应变成隐藏"
        assert window.taskbar_calls == [True]
        assert ctrl.tray.visibility[-1] is False

    def test_toggle_shows_and_restores_taskbar(self, monkeypatch):
        import desktop

        window = FakeWindow(visible=False)
        ctrl, _ = self._make(monkeypatch, window)
        ctrl.start()

        monkeypatch.setattr(desktop, "is_window_visible", lambda hwnd: False)
        monkeypatch.setattr(desktop, "show_window", lambda hwnd: True)

        result = ctrl._on_toggle()
        assert result is True, "不可见时切换应变成显示"
        assert window.taskbar_calls == [False]
        assert ctrl.tray.visibility[-1] is True

    def test_force_show_and_force_hide(self, monkeypatch):
        import desktop

        window = FakeWindow(visible=True)
        ctrl, _ = self._make(monkeypatch, window)
        ctrl.start()
        monkeypatch.setattr(desktop, "is_window_visible", lambda hwnd: True)
        monkeypatch.setattr(desktop, "show_window", lambda hwnd: True)
        monkeypatch.setattr(desktop, "hide_window", lambda hwnd: True)

        assert ctrl._on_toggle(True) is True   # 菜单「显示窗口」
        assert ctrl._on_toggle(False) is False  # 菜单「隐藏窗口」

    def test_toggle_without_hwnd_is_safe(self, monkeypatch):
        window = FakeWindow(hwnd=0)
        ctrl, _ = self._make(monkeypatch, window)
        ctrl.start()
        assert ctrl._on_toggle() is False  # 无句柄时应安全返回

    def test_quit_callback_is_invoked(self, monkeypatch):
        window = FakeWindow()
        from desktop import TrayController

        ctrl = TrayController(window, quit_callback=window.close)
        ctrl._request_quit()
        assert ctrl.quit_requested is True
        assert window.closed == 1

    def test_quit_without_callback_sets_flag(self):
        from desktop import TrayController

        ctrl = TrayController(FakeWindow())
        ctrl._request_quit()
        assert ctrl.quit_requested is True

    def test_start_returns_false_when_unavailable(self, monkeypatch):
        from desktop import TrayController

        monkeypatch.setattr(tray_mod, "available", lambda: False)
        ctrl = TrayController(FakeWindow())
        assert ctrl.start() is False

    def test_stop_is_idempotent(self, monkeypatch):
        ctrl, _ = self._make(monkeypatch, FakeWindow())
        ctrl.start()
        ctrl.stop()
        ctrl.stop()
        assert ctrl.tray is None


class TestTrayFlagDefaults:
    """--tray 与 --hide-taskbar 的组合规则

    _apply_env_defaults 通过 sys.argv + _EXPLICIT_ARGS 判断「哪些开关是显式传的」，
    因此这里直接改这两处来构造场景。
    """

    def _resolve(self, monkeypatch, argv):
        import desktop

        monkeypatch.setattr(sys, "argv", ["desktop.py"] + argv)
        monkeypatch.setattr(desktop, "_EXPLICIT_ARGS", [], raising=False)
        args = desktop.build_parser().parse_args(argv)
        desktop._apply_env_defaults(args)
        return args

    def test_tray_defaults_to_hiding_taskbar(self, monkeypatch):
        args = self._resolve(monkeypatch, ["--tray"])
        assert args.hide_taskbar is True, "托盘模式应默认隐藏任务栏图标"

    def test_explicit_hide_taskbar_false_wins(self, monkeypatch):
        args = self._resolve(monkeypatch, ["--tray", "--hide-taskbar", "false"])
        assert args.hide_taskbar is False, "显式传的 --hide-taskbar 优先"

    def test_no_tray_keeps_taskbar_visible(self, monkeypatch):
        args = self._resolve(monkeypatch, [])
        assert args.tray is False
        assert args.hide_taskbar is False, "不开托盘时不应擅自隐藏任务栏"
