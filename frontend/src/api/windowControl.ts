/**
 * 桌面窗口控制桥接 — 与 Python 侧 WindowControlApi 通信
 *
 * 仅在「独立窗口模式」（desktop.py + pywebview）下可用：
 * 此时 window.pywebview.api 由 pywebview 注入。
 * 在普通浏览器中打开时，window.pywebview 不存在，所有接口返回可用性=false，
 * 界面据此隐藏窗口控制相关的控件。
 */

/** pywebview 注入的 API 形状（只声明我们用到的方法） */
interface PywebviewApi {
  set_opacity: (value: number) => Promise<OpacityResult>
  get_opacity: () => Promise<OpacityResult>
  get_state: () => Promise<WindowStateResult>
  set_topmost: (enabled: boolean) => Promise<TopmostResult>
  set_taskbar_hidden: (hidden: boolean) => Promise<TaskbarResult>
  set_capture_exclude: (exclude: boolean) => Promise<CaptureResult>
  close_window: () => Promise<{ ok: boolean; error: string | null }>
  register_screenshot_hotkey: () => Promise<HotkeyResult>
  unregister_screenshot_hotkey: () => Promise<HotkeyResult>
  get_hotkey_state: () => Promise<HotkeyStateResult>
  on_hotkey: (jsFunctionName: string) => Promise<HotkeyCallbackResult>
}

interface PywebviewBridge {
  api: PywebviewApi
}

declare global {
  interface Window {
    pywebview?: PywebviewBridge
  }
}

export interface OpacityResult {
  ok: boolean
  opacity: number | null
  error: string | null
}

export interface WindowStateResult {
  ok: boolean
  opacity: number | null
  topmost: boolean
  capture_exclude: boolean
  /** 当前窗口是否支持捕获排除（browser 模式下为 false） */
  capture_supported?: boolean
  hide_taskbar: boolean
  min_opacity: number
  max_opacity: number
  /** 透明度百分数（20 ~ 100），便于直接绑定滑块 */
  opacity_percent?: number | null
  error: string | null
}

interface TopmostResult {
  ok: boolean
  topmost: boolean
  error: string | null
}

interface TaskbarResult {
  ok: boolean
  hide_taskbar: boolean
  error: string | null
}

interface CaptureResult {
  ok: boolean
  capture_exclude: boolean
  error: string | null
}

export interface HotkeyResult {
  ok: boolean
  hotkey: string
  error: string | null
}

export interface HotkeyStateResult extends HotkeyResult {
  /** 当前环境是否支持全局热键（仅独立窗口模式为 true） */
  available: boolean
}

interface HotkeyCallbackResult {
  ok: boolean
  callback?: string
  error: string | null
}

/** 桥接是否可用（即是否运行在独立窗口模式中） */
export function isDesktopWindow(): boolean {
  return typeof window !== 'undefined' && !!window.pywebview?.api
}

/**
 * pywebview 注入 API 是异步的：页面加载完成时 window.pywebview 可能尚未就绪。
 * 这里轮询等待一小段时间，避免首屏误判为「非独立窗口」。
 */
export function waitForBridge(timeoutMs = 3000, intervalMs = 100): Promise<boolean> {
  if (isDesktopWindow()) return Promise.resolve(true)

  return new Promise((resolve) => {
    const deadline = Date.now() + timeoutMs
    const timer = window.setInterval(() => {
      if (isDesktopWindow()) {
        window.clearInterval(timer)
        resolve(true)
      } else if (Date.now() >= deadline) {
        window.clearInterval(timer)
        resolve(false)
      }
    }, intervalMs)
  })
}

/** 读取窗口当前状态（透明度 / 置顶 / 捕获排除等） */
export async function getWindowState(): Promise<WindowStateResult | null> {
  if (!isDesktopWindow()) return null
  try {
    return await window.pywebview!.api.get_state()
  } catch {
    return null
  }
}

/** 设置窗口透明度，value 取 0.2 ~ 1.0 */
export async function setWindowOpacity(value: number): Promise<OpacityResult> {
  if (!isDesktopWindow()) {
    return { ok: false, opacity: null, error: '当前不在独立窗口模式中' }
  }
  try {
    return await window.pywebview!.api.set_opacity(value)
  } catch (err) {
    return { ok: false, opacity: null, error: (err as Error).message || '设置失败' }
  }
}

/** 设置窗口置顶 */
export async function setWindowTopmost(enabled: boolean): Promise<TopmostResult> {
  if (!isDesktopWindow()) {
    return { ok: false, topmost: enabled, error: '当前不在独立窗口模式中' }
  }
  try {
    return await window.pywebview!.api.set_topmost(enabled)
  } catch (err) {
    return { ok: false, topmost: enabled, error: (err as Error).message || '设置失败' }
  }
}

/** 隐藏/显示任务栏图标 */
export async function setTaskbarHidden(hidden: boolean): Promise<TaskbarResult> {
  if (!isDesktopWindow()) {
    return { ok: false, hide_taskbar: hidden, error: '当前不在独立窗口模式中' }
  }
  try {
    return await window.pywebview!.api.set_taskbar_hidden(hidden)
  } catch (err) {
    return { ok: false, hide_taskbar: hidden, error: (err as Error).message || '设置失败' }
  }
}

/** 从屏幕捕获（截屏 / 录屏）中排除或恢复窗口 */
export async function setCaptureExclude(exclude: boolean): Promise<CaptureResult> {
  if (!isDesktopWindow()) {
    return { ok: false, capture_exclude: exclude, error: '当前不在独立窗口模式中' }
  }
  try {
    return await window.pywebview!.api.set_capture_exclude(exclude)
  } catch (err) {
    return { ok: false, capture_exclude: exclude, error: (err as Error).message || '设置失败' }
  }
}

/**
 * 注册全局 F8 热键（窗口失焦也能触发）。
 *
 * 这是网页 JS 做不到的事：keydown 只在窗口聚焦时才有事件，
 * 而截图时焦点往往在题目所在的窗口上。全局热键由 Python 侧
 * 用 Win32 RegisterHotKey 向系统注册，焦点在哪都能触发。
 */
export async function registerScreenshotHotkey(): Promise<HotkeyResult> {
  if (!isDesktopWindow()) {
    return { ok: false, hotkey: 'F8', error: '当前不在独立窗口模式中' }
  }
  try {
    return await window.pywebview!.api.register_screenshot_hotkey()
  } catch (err) {
    return { ok: false, hotkey: 'F8', error: (err as Error).message || '注册全局热键失败' }
  }
}

/** 注销全局 F8 热键（释放给其它程序使用） */
export async function unregisterScreenshotHotkey(): Promise<HotkeyResult> {
  if (!isDesktopWindow()) {
    return { ok: false, hotkey: 'F8', error: '当前不在独立窗口模式中' }
  }
  try {
    return await window.pywebview!.api.unregister_screenshot_hotkey()
  } catch (err) {
    return { ok: false, hotkey: 'F8', error: (err as Error).message || '注销全局热键失败' }
  }
}

/** 查询全局热键的注册状态 */
export async function getHotkeyState(): Promise<HotkeyStateResult | null> {
  if (!isDesktopWindow()) return null
  try {
    return await window.pywebview!.api.get_hotkey_state()
  } catch {
    return null
  }
}

/**
 * 登记按下全局热键时要调用的前端函数名。
 *
 * 后端是「主动」通知前端的：它会在热键触发时执行
 * window[jsFunctionName]()，所以前端必须先在 window 上挂一个函数。
 */
export async function setHotkeyHandler(jsFunctionName: string): Promise<HotkeyCallbackResult> {
  if (!isDesktopWindow()) {
    return { ok: false, error: '当前不在独立窗口模式中' }
  }
  try {
    return await window.pywebview!.api.on_hotkey(jsFunctionName)
  } catch (err) {
    return { ok: false, error: (err as Error).message || '登记热键回调失败' }
  }
}