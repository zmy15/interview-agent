"""
屏幕截图识别服务 — 整屏捕获 + DeepSeek 视觉模型提取题目并作答

职责：
    1) 抓取主显示器画面
    2) 编码为 base64 data URL，交给 DeepSeek 视觉模型
    3) 返回「识别到的题目 + 答案」

捕获后端：windows-capture（Rust 实现，基于 Windows Graphics Capture）
    它是**显示器维度**的捕获接口：monitor_index 从 1 开始
    （1 = 主显示器，0 会被库拒绝）。本模块固定使用 monitor_index=1。

    为什么不做多屏拼接：
        拼接需要每块屏的精确位置与尺寸，而该库只提供按显示器捕获，
        拿不到布局信息。早前版本按「水平依次排布」估算坐标，当副屏
        比主屏高时（2560×1600 配 2560×1440），拼接画布按虚拟桌面高度
        裁切，副屏底部会被切掉。既然只需要一块屏，直接截主显示器
        最稳妥：尺寸精确、无裁切、耗时也只有多屏的一半。

⚠️ 关键：模型必须支持视觉
    纯文本模型（如 deepseek-v4-flash）不具备视觉能力。把图片发给它
    **不会报错**，而是忽略图片、编造一个看似合理的答案 —— 这是最危险的
    失败模式。因此本模块默认使用 settings.SCREENSHOT_VISION_MODEL，
    并在发送前校验模型可用性。
"""

from __future__ import annotations

import base64
import ctypes
import io
import logging
import sys
import threading
import time
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

# ── 可选依赖：缺失时接口返回明确指引，而不是 500 ──
try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    from windows_capture import WindowsCapture, Frame, InternalCaptureControl

    WC_AVAILABLE = True
    WC_IMPORT_ERROR = ""
except Exception as _exc:  # pragma: no cover
    WindowsCapture = None  # type: ignore[assignment]
    Frame = None  # type: ignore[assignment]
    InternalCaptureControl = None  # type: ignore[assignment]
    WC_AVAILABLE = False
    WC_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"


class CaptureError(RuntimeError):
    """截图失败（可预期的错误，会被路由转换成 4xx）"""


# ══════════════════════════════════════════════════════════════
# Win32：让本进程窗口对截屏不可见
# ══════════════════════════════════════════════════════════════
#
# 独立窗口模式下，本应用自己就是一个窗口。如果客户端的「全屏截图」
# 把本应用也拍进去，画面里就只有应用自己，截图毫无意义。
# 因此这里提供 WDA_EXCLUDEFROMCAPTURE 开关，由 desktop.py 在
# 创建窗口后调用，使本应用对截屏/录屏完全不可见。

WDA_EXCLUDEFROMCAPTURE = 0x00000011
WDA_NONE = 0x00000000

_user32 = None
if IS_WINDOWS:
    try:
        _user32 = ctypes.WinDLL("user32", use_last_error=True)
        _user32.SetWindowDisplayAffinity.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        _user32.SetWindowDisplayAffinity.restype = ctypes.c_bool
        _user32.GetWindowDisplayAffinity.argtypes = (
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        )
        _user32.GetWindowDisplayAffinity.restype = ctypes.c_bool
        # 前台窗口捕获所需的 API
        _user32.GetForegroundWindow.restype = ctypes.c_void_p
        _user32.GetAncestor.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
        _user32.GetAncestor.restype = ctypes.c_void_p
        _user32.GetWindowTextW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
        _user32.GetWindowTextW.restype = ctypes.c_int
        _user32.GetClassNameW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int)
        _user32.GetClassNameW.restype = ctypes.c_int
    except Exception as _exc:  # pragma: no cover
        logger.warning("user32 初始化失败，捕获排除不可用: %s", _exc)
        _user32 = None


def set_capture_exclusion(hwnd: int, exclude: bool = True) -> bool:
    """设置窗口是否对截屏/录屏不可见。

    只能作用于「当前进程拥有」的顶层窗口；对别的进程会返回 False。
    """
    if not IS_WINDOWS or not _user32 or not hwnd:
        return False
    affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
    try:
        return bool(_user32.SetWindowDisplayAffinity(ctypes.c_void_p(hwnd), affinity))
    except Exception as exc:  # pragma: no cover
        logger.debug("SetWindowDisplayAffinity 失败: %s", exc)
        return False


def get_capture_exclusion(hwnd: int) -> Optional[bool]:
    """读取窗口当前是否已从屏幕捕获中排除；无法确定时返回 None"""
    if not IS_WINDOWS or not _user32 or not hwnd:
        return None
    value = ctypes.c_uint32(0)
    try:
        if not _user32.GetWindowDisplayAffinity(ctypes.c_void_p(hwnd), ctypes.byref(value)):
            return None
    except Exception:  # pragma: no cover
        return None
    return value.value in (WDA_EXCLUDEFROMCAPTURE, 0x00000001)


# ══════════════════════════════════════════════════════════════
# 截图可用性
# ══════════════════════════════════════════════════════════════


def is_available() -> bool:
    """整屏截图是否可用"""
    return bool(IS_WINDOWS and WC_AVAILABLE and np is not None and Image is not None)


def availability_error() -> str:
    """返回不可用的原因（可用时为空串），用于前端提示"""
    if not IS_WINDOWS:
        return "屏幕截图仅支持 Windows 系统（依赖 Windows Graphics Capture）"
    if not WC_AVAILABLE:
        return (
            f"windows-capture 未安装或加载失败（{WC_IMPORT_ERROR}）。"
            "请执行：pip install windows-capture"
        )
    if np is None:
        return "缺少 numpy，请执行：pip install numpy"
    if Image is None:
        return "缺少 pillow，请执行：pip install pillow"
    return ""


# ══════════════════════════════════════════════════════════════
# 显示器信息
# ══════════════════════════════════════════════════════════════

# GetSystemMetrics 索引
SM_CXSCREEN, SM_CYSCREEN = 0, 1
SM_CMONITORS = 80

# windows-capture 的 monitor_index 从 1 开始，1 即主显示器。
PRIMARY_MONITOR_INDEX = 1

# 等待首帧的超时（秒）。WGC 首帧通常在 100ms 内到达，
# 给足余量以应对高负载或独显首次初始化。
_FIRST_FRAME_TIMEOUT = 3.0

# windows-capture 的 start() 会阻塞直到 stop()，因此做一次全局锁，
# 避免并发请求互相干扰同一个捕获会话。
_capture_lock = threading.Lock()


def _monitor_count() -> int:
    """系统检测到的显示器数量（仅用于展示，不影响截图目标）"""
    if not IS_WINDOWS or not _user32:
        return 0
    try:
        return int(_user32.GetSystemMetrics(SM_CMONITORS))
    except Exception:
        return 0


def primary_size() -> tuple[int, int]:
    """主显示器的 (宽, 高)；取不到时返回 (0, 0)"""
    if not IS_WINDOWS or not _user32:
        return 0, 0
    try:
        return (
            int(_user32.GetSystemMetrics(SM_CXSCREEN)),
            int(_user32.GetSystemMetrics(SM_CYSCREEN)),
        )
    except Exception:
        return 0, 0


def list_monitors() -> list[dict]:
    """返回截图目标（仅主显示器）。

    本项目固定只截主显示器，因此这里只返回一项。

    为什么不做多屏拼接：
        把各块显示器按虚拟桌面坐标拼成一张大图，需要每块屏的精确位置
        与尺寸（要靠 EnumDisplayMonitors），而 windows-capture 只提供
        按显示器捕获。早前的实现按「水平依次排布」估算坐标，当副屏比
        主屏高时（例如 2560×1600 配 2560×1440），拼接画布按虚拟桌面
        高度裁切，副屏底部会被切掉。既然实际只需要一块屏，直接截主屏
        最稳妥：尺寸精确、无裁切、耗时也只有多屏的一半。
    """
    pw, ph = primary_size()
    if pw <= 0 or ph <= 0:
        return []

    return [{
        "id": "primary",
        "name": f"主显示器（{pw}×{ph}）",
        "x": 0, "y": 0, "width": pw, "height": ph,
    }]


# ══════════════════════════════════════════════════════════════
# 整屏捕获（windows-capture）
# ══════════════════════════════════════════════════════════════


def capture_monitor(monitor_index: int, *, cursor: bool = False,
                    timeout: float = _FIRST_FRAME_TIMEOUT) -> "Image.Image":
    """捕获**单块**显示器，返回 PIL RGB 图像。

    windows-capture 的 start() 会阻塞直到回调里调用 control.stop()，
    因此这里在回调收到第一帧后立刻停止 —— 只取一帧，不做持续录制。

    monitor_index 从 1 开始（1 = 主显示器）。0 会被库拒绝。
    """
    if not is_available():
        raise CaptureError(availability_error())
    if monitor_index < 1:
        raise CaptureError(
            f"monitor_index 必须从 1 开始（1 = 主显示器），收到 {monitor_index}"
        )

    try:
        capture = WindowsCapture(
            cursor_capture=cursor,
            draw_border=False,
            monitor_index=monitor_index,
        )
    except Exception as exc:
        raise CaptureError(
            f"无法创建显示器 {monitor_index} 的捕获会话: {exc}"
        ) from exc

    holder: dict = {"frame": None, "error": None}
    done = threading.Event()

    @capture.event
    def on_frame_arrived(frame: "Frame", capture_control: "InternalCaptureControl"):
        try:
            # 注意：frame.convert_to_bgr() 返回的是 Frame 而不是 numpy 数组，
            # 真正的像素在 frame_buffer 上，格式为 BGRA。
            buf = frame.frame_buffer
            if buf is None:
                holder["error"] = "回调未提供像素数据"
                return
            arr = np.asarray(buf)
            if arr.ndim != 3 or arr.shape[2] < 3:
                holder["error"] = f"像素格式异常: shape={arr.shape}"
                return
            rgb = arr[:, :, [2, 1, 0]]      # BGRA/BGR -> RGB
            holder["frame"] = Image.fromarray(np.ascontiguousarray(rgb), mode="RGB")
        except Exception as exc:  # pragma: no cover
            holder["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            try:
                capture_control.stop()
            except Exception:
                pass
            done.set()

    @capture.event
    def on_closed():
        # 会话关闭（正常结束或被系统中断）。若此时仍没拿到帧，
        # 说明捕获失败，由下方的超时逻辑统一报错。
        done.set()

    try:
        capture.start()      # 阻塞至 stop()
    except Exception as exc:
        raise CaptureError(
            f"显示器 {monitor_index} 捕获失败: {exc}"
        ) from exc

    # start() 返回后回调可能仍在收尾，稍等 done 置位
    done.wait(timeout=timeout)

    if holder["error"]:
        raise CaptureError(f"显示器 {monitor_index} 捕获异常: {holder['error']}")

    img = holder["frame"]
    if img is None:
        raise CaptureError(
            f"显示器 {monitor_index} 在 {timeout:.0f} 秒内没有返回画面"
        )

    logger.info("捕获显示器成功 | index=%d | %dx%d", monitor_index, img.width, img.height)
    return img


def grab_screen(*, cursor: bool = False) -> "Image.Image":
    """抓取主显示器画面，返回 PIL RGB 图像。

    固定截取主显示器（monitor_index=1），不做多屏拼接 ——
    拼接需要每块屏的精确位置与尺寸，而 windows-capture 只提供
    按显示器捕获；早前的按坐标估算拼接会在副屏更高时裁掉底部。
    单屏捕获尺寸精确、无裁切，耗时也只有多屏的一半。
    """
    if not is_available():
        raise CaptureError(availability_error())

    with _capture_lock:
        return capture_monitor(PRIMARY_MONITOR_INDEX, cursor=cursor)

# ══════════════════════════════════════════════════════════════
# 鼠标光标
# ══════════════════════════════════════════════════════════════
#
# 光标由 windows-capture 的 cursor_capture 参数原生支持
# （见 capture_monitor 的 cursor 形参），无需自己绘制。
# 早期基于 GDI BitBlt 的实现必须手工叠加光标，改用本库后
# 那段逻辑已删除。


# ══════════════════════════════════════════════════════════════
# 图像编码
# ══════════════════════════════════════════════════════════════


def encode_image(img: "Image.Image", max_edge: Optional[int] = None) -> tuple[str, bytes]:
    """缩放并编码为 PNG data URL，返回 (data_url, png_bytes)。

    用 PNG 而非 JPEG：截图里大量是文字，PNG 无损、边缘更锐利，
    OCR 类任务识别率更高；尺寸已经缩过，体积可控。
    """
    if Image is None:
        raise CaptureError("缺少 pillow，请执行：pip install pillow")

    limit = int(max_edge or settings.SCREENSHOT_MAX_IMAGE_EDGE)
    im = img
    if limit > 0 and max(im.width, im.height) > limit:
        scale = limit / float(max(im.width, im.height))
        new_size = (max(1, int(im.width * scale)), max(1, int(im.height * scale)))
        im = im.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    raw = buf.getvalue()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:image/png;base64,{b64}", raw


def save_image(raw: bytes, filename: str) -> str:
    """把 PNG 字节写入截图目录，返回绝对路径"""
    import os

    directory = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        settings.SCREENSHOT_DIR,
    )
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)
    try:
        with open(path, "wb") as f:
            f.write(raw)
    except OSError as exc:
        logger.warning("截图保存失败: %s", exc)
        raise CaptureError(f"截图保存失败: {exc}") from exc
    return path


def screenshot_dir() -> str:
    """截图目录绝对路径（供路由列举历史截图）"""
    import os

    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        settings.SCREENSHOT_DIR,
    )


# ══════════════════════════════════════════════════════════════
# 视觉模型调用
# ══════════════════════════════════════════════════════════════

# 视觉模型候选：按顺序尝试。
# 官方文档中 deepseek-v4-flash-vision-exp 已下线（请求仍由最新 Flash 承接），
# 保留为兜底以兼容旧账号。
VISION_MODEL_CANDIDATES = [
    "deepseek-flash",
    "deepseek-v4-flash-vision-exp",
]

# 进程内缓存「账号可用的视觉模型」，避免每次截图都打一次 /models
_resolved_model: Optional[str] = None
_model_lock = threading.Lock()


def _candidate_models() -> list[str]:
    out: list[str] = []
    preferred = (settings.SCREENSHOT_VISION_MODEL or "").strip()
    if preferred:
        out.append(preferred)
    for m in VISION_MODEL_CANDIDATES:
        if m not in out:
            out.append(m)
    return out


async def resolve_vision_model(api_key: Optional[str] = None) -> str:
    """选出账号下实际可用的视觉模型。

    纯文本模型无法看图，若直接发送会得到「假装看过」的幻觉答案，
    因此这里必须确认模型真实存在，而不是盲目使用配置值。
    """
    global _resolved_model

    with _model_lock:
        if _resolved_model:
            return _resolved_model

    from services.llm_client import get_client

    client = get_client(api_key=api_key)

    try:
        resp = await client.models.list()
        available = [m.id for m in getattr(resp, "data", []) or []]
    except Exception as exc:
        text = str(exc)
        # 鉴权失败必须上抛：否则「拿不到列表」会被误判为「模型名没问题」
        if "401" in text or "Authentication" in text or "invalid_api_key" in text.lower():
            raise CaptureError(
                "DeepSeek API Key 无效或已失效（401）。"
                "请检查 .env 中的 DEEPSEEK_API_KEY，或在前端设置中填入有效 Key。"
            ) from exc
        logger.warning("获取模型列表失败，沿用配置值 %s: %s", settings.SCREENSHOT_VISION_MODEL, exc)
        return settings.SCREENSHOT_VISION_MODEL

    if not available:
        return settings.SCREENSHOT_VISION_MODEL

    chosen: Optional[str] = None
    for cand in _candidate_models():
        if cand in available:
            chosen = cand
            break

    if chosen is None:
        # 退而求其次：任何同时带 vision 与 flash 的模型
        fuzzy = [m for m in available if "vision" in m.lower() and "flash" in m.lower()]
        if fuzzy:
            chosen = sorted(fuzzy, key=len, reverse=True)[0]

    if chosen is None:
        raise CaptureError(
            "当前 API Key 下没有可用的 DeepSeek 视觉模型，无法识别截图。"
            f"可用模型：{', '.join(available)}。"
            "纯文本模型不支持图片输入，请改用支持视觉的模型"
            "（如 deepseek-flash），或在 .env 中设置 SCREENSHOT_VISION_MODEL。"
        )

    with _model_lock:
        _resolved_model = chosen
    logger.info("使用视觉模型: %s", chosen)
    return chosen


def invalidate_model_cache() -> None:
    """清除视觉模型缓存（Key 变更后调用）"""
    global _resolved_model
    with _model_lock:
        _resolved_model = None


async def ask_vision(
    image_data_url: str,
    prompt: str,
    system_prompt: str = "",
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    thinking: Optional[bool] = None,
) -> tuple[str, str]:
    """把截图交给 DeepSeek 视觉模型，返回 (回答文本, 实际使用的模型名)。

    为什么默认关闭思考模式：
        DeepSeek 的思考模式**默认是开启的**（effort 默认 high），思维链
        与正文共享 max_tokens 预算。截图答题是「照抄题干 + 给答案」，
        不需要长链推理，开着思考会让推理占掉大量预算、正文被截断
        （实测表现：回答写到一半突然中断）。因此这里显式传
        {"thinking": {"type": "disabled"}}。

        注意：思考模式下 temperature / presence_penalty / frequency_penalty
        **不生效**（传了不报错但被忽略），所以本函数不再传 temperature。
    """
    from services.llm_client import get_client

    _model = model or await resolve_vision_model(api_key=api_key)
    client = get_client(api_key=api_key)
    _max_tokens = int(max_tokens or settings.SCREENSHOT_MAX_TOKENS)
    _thinking = settings.SCREENSHOT_THINKING_ENABLED if thinking is None else thinking

    messages: list[dict] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    # 图片只能出现在 user 消息中，放 system/assistant 会返回 400
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        }
    )

    extra_body: dict = {}
    if _thinking:
        extra_body["thinking"] = {"type": "enabled"}
        extra_body["reasoning_effort"] = settings.DEEPSEEK_REASONING_EFFORT
    else:
        extra_body["thinking"] = {"type": "disabled"}

    try:
        resp = await client.chat.completions.create(
            model=_model,
            messages=messages,
            max_tokens=_max_tokens,
            extra_body=extra_body,
            stream=False,
        )
    except Exception as exc:
        text = str(exc)
        if "401" in text or "Authentication" in text:
            raise CaptureError(
                "DeepSeek API Key 无效或已失效（401），请检查配置。"
            ) from exc
        if "404" in text or ("model" in text.lower() and "not" in text.lower()):
            raise CaptureError(
                f"模型 {_model} 调用失败：{text}。"
                "请在 .env 中把 SCREENSHOT_VISION_MODEL 设为账号下可用的视觉模型。"
            ) from exc
        raise CaptureError(f"视觉模型调用失败：{text}") from exc

    if not resp.choices:
        raise CaptureError("视觉模型没有返回任何结果")

    choice = resp.choices[0]
    content = (choice.message.content or "").strip()

    # ── 截断检测：finish_reason=length 表示撞上了 max_tokens 上限 ──
    # 必须显式告知用户，否则「答案写到一半没了」会被误认为是模型能力问题。
    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason == "length":
        logger.warning(
            "视觉回答因达到 max_tokens=%s 被截断（model=%s）", _max_tokens, _model
        )
        content += (
            f"\n\n---\n\n> ⚠️ **回答被截断**：已达到单次输出上限 "
            f"（`SCREENSHOT_MAX_TOKENS={_max_tokens}`）。"
            "可在 `.env` 中调大该值后重试。"
        )

    usage = getattr(resp, "usage", None)
    if usage:
        reasoning = getattr(choice.message, "reasoning_content", None) or ""
        logger.info(
            "视觉问答完成 | model=%s | thinking=%s | prompt_tokens=%s | "
            "completion_tokens=%s | reasoning_chars=%d | content_chars=%d | finish=%s",
            _model,
            _thinking,
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            len(reasoning),
            len(content),
            finish_reason,
        )
    return content, _model
