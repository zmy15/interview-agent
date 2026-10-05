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
  close_window: () => Promise<{ ok: boolean; error: string | null }>
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