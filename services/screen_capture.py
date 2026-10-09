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
    失败模式。因此本模块不写死模型名，而是在发送前调用官方
    `GET /models` 接口（services/model_registry.py），用模型元数据里的
    `input_modalities` 判断它能否看图；不支持时直接返回「不支持图片输入」，
    绝不把图片发出去赌运气。

    使用哪个模型、是否开启思考，均以界面上的选择为准（前端把当前选中的
    模型与思考开关透传给 /screenshot/capture）。
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
# 思考强度（reasoning_effort）
# ══════════════════════════════════════════════════════════════

# 官方规范档位：{"reasoning_effort": "low/high/max"}
# 服务端还会做一次映射：minimal→low、medium/xhigh→high、ultra→max，
# 这里统一收敛到三个规范值，避免把映射关系散落在各处。
VALID_EFFORTS = ("low", "high", "max")

# 常见别名 → 规范档位（兼容手写 .env 或旧数据）
_EFFORT_ALIASES = {
    "minimal": "low",
    "medium": "high",
    "xhigh": "high",
    "ultra": "max",
}

DEFAULT_EFFORT = "high"


def normalize_effort(value: Optional[str]) -> str:
    """把任意 reasoning_effort 输入归一化成 low / high / max。

    未知值回落到 high（官方默认），并记一条警告 —— 直接透传非法值
    虽然服务端不一定报错，但会让「界面显示」与「实际生效」对不上。
    """
    raw = (value or "").strip().lower()
    if not raw:
        return DEFAULT_EFFORT
    if raw in VALID_EFFORTS:
        return raw
    if raw in _EFFORT_ALIASES:
        return _EFFORT_ALIASES[raw]
    logger.warning("未知的 reasoning_effort=%r，回落到 %s", value, DEFAULT_EFFORT)
    return DEFAULT_EFFORT


# ══════════════════════════════════════════════════════════════
# 视觉模型调用
# ══════════════════════════════════════════════════════════════
#
# 模型不写死：候选模型完全来自官方 `GET /models` 接口
# （services/model_registry.py），并以其 input_modalities 是否含
# "image" 判断该模型能否看图。
#
# ⚠️ 关键：纯文本模型收到图片**不会报错**，而是忽略图片、编造一个
# 看似合理的答案。因此发送前必须完成「能否看图」的校验，不支持时
# 直接返回明确的不支持提示，而不是把图片发出去赌运气。


async def resolve_capture_model(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> tuple[str, bool]:
    """决定本次截图使用哪个模型，并确认它支持图片输入。

    参数：
        model   —— 界面当前选中的模型；为空时由后端按账号可用模型挑选。
    返回：
        (model_id, supports_vision)
    异常：
        CaptureError —— 模型不存在 / 不支持图片 / 账号下没有视觉模型。
    """
    from services import model_registry as registry

    models = await registry.get_available_models(api_key=api_key)
    by_id = {m.id: m for m in models}
    vision_models = [m.id for m in models if m.supports_vision]

    # ── 情况 1：界面选了模型，就用它（不再静默替换成别的模型）──
    if model:
        info = by_id.get(model)
        if info is None:
            listed = "、".join(by_id) or "（空）"
            raise CaptureError(
                f"模型 {model} 不在当前 API Key 的可用模型列表中，无法截图识别。"
                f"可用模型：{listed}。"
            )
        if not info.supports_vision:
            hint = (
                f"当前账号支持图片输入的模型：{'、'.join(vision_models)}。"
                if vision_models
                else "当前 API Key 下没有任何支持图片输入的模型。"
            )
            raise CaptureError(
                f"模型 {model} 不支持图片输入，无法识别截图。"
                "请在模型选择器中改用支持视觉的模型。"
                + hint
            )
        return model, True

    # ── 情况 2：未指定模型，挑账号下第一个可用的视觉模型 ──
    preferred = (settings.SCREENSHOT_VISION_MODEL or "").strip()
    if preferred and preferred in vision_models:
        return preferred, True
    if vision_models:
        return vision_models[0], True

    # ── 情况 3：远端列表拿不到（回退到本地配置）时，无法确认视觉能力 ──
    fallback = preferred or (settings.DEEPSEEK_MODEL or "").strip()
    if fallback:
        logger.warning(
            "无法从模型列表确认 %s 是否支持图片输入（远端列表不可用），将按配置尝试",
            fallback,
        )
        return fallback, False

    raise CaptureError(
        "当前 API Key 下没有可用的视觉模型，无法识别截图。"
        "纯文本模型不支持图片输入，请改用支持图片的模型"
        "（可在界面的模型选择器中查看带「🖼」标记的模型）。"
    )


async def ask_vision(
    image_data_url: str,
    prompt: str,
    system_prompt: str = "",
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: Optional[int] = None,
    thinking: Optional[bool] = None,
    reasoning_effort: Optional[str] = None,
) -> tuple[str, str, bool]:
    """把截图交给 DeepSeek 视觉模型，返回 (回答文本, 实际模型名, 是否开启思考)。

    模型与思考模式均以界面选择为准：
        - model 为界面选中的模型；为空时才由后端挑选账号下的视觉模型。
        - thinking / reasoning_effort 透传界面的思考开关与推理强度。
          思考模式下 temperature / presence_penalty / frequency_penalty
          不生效（传了不报错但被忽略），所以这里不传 temperature。
    """
    from services.llm_client import get_client

    _model, _vision_ok = await resolve_capture_model(api_key=api_key, model=model)

    # 无法确认视觉能力（远端列表不可用且未显式选模型）时给出提示，
    # 但不阻断：用户可能配置了文档未登记的视觉模型。
    _notice = ""
    if not _vision_ok:
        _notice = (
            f"\n\n---\n\n> ⚠️ 未能确认模型 `{_model}` 是否支持图片输入"
            "（模型列表接口不可用）。若下方内容与截图无关，"
            "说明该模型不具备视觉能力，请改用支持图片的模型。"
        )

    client = get_client(api_key=api_key)
    _max_tokens = int(max_tokens or settings.SCREENSHOT_MAX_TOKENS)

    if thinking is None:
        _thinking = settings.SCREENSHOT_THINKING_ENABLED
    else:
        _thinking = bool(thinking)
    _effort = normalize_effort(reasoning_effort or settings.DEEPSEEK_REASONING_EFFORT)

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
        extra_body["reasoning_effort"] = _effort
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
                "请在模型选择器中改用当前 API Key 下可用的模型。"
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
            "视觉问答完成 | model=%s | thinking=%s(%s) | prompt_tokens=%s | "
            "completion_tokens=%s | reasoning_chars=%d | content_chars=%d | finish=%s",
            _model,
            _thinking,
            _effort if _thinking else "-",
            getattr(usage, "prompt_tokens", "?"),
            getattr(usage, "completion_tokens", "?"),
            len(reasoning),
            len(content),
            finish_reason,
        )

    if _notice:
        content += _notice
    return content, _model, _thinking
