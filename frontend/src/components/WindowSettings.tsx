/**
 * 窗口设置面板 — 透明度滑块 / 置顶 / 窗口状态
 *
 * 仅在独立窗口模式（desktop.py 启动）下显示；
 * 普通浏览器中 isDesktopWindow() 为 false，整个入口自动隐藏。
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Popover, Slider, Switch, Space, Typography, Tooltip, Divider, message } from 'antd'
import { SettingOutlined } from '@ant-design/icons'
import ThemeColorSettings from '@/components/ThemeColorSettings'
import SystemAudioSettings from '@/components/SystemAudioSettings'
import {
  isDesktopWindow,
  waitForBridge,
  getWindowState,
  setWindowOpacity,
  setWindowTopmost,
  setTaskbarHidden,
  // 起别名，避免与本地 state setter（setCaptureExclude）重名
  setCaptureExclude as applyCaptureExclude,
} from '@/api/windowControl'

const { Text } = Typography

interface WindowSettingsProps {
  /** 系统音频监听状态（由 ChatPage 回传，仅用于显示） */
  systemAudioListening?: boolean
  systemAudioSttConnected?: boolean
  systemAudioError?: string | null
}

// 透明度范围（滑块刻度为百分数 20-100；向后端提交时再换算成 0.2-1.0）
const MIN_PERCENT = 20
const MAX_PERCENT = 100
const DEFAULT_PERCENT = 100

/** 百分数 → 后端所需的 0.2-1.0 小数 */
const percentToFraction = (percent: number) => percent / 100

/** 后端返回的小数（或百分数）→ 滑块百分数 */
const toPercent = (value: number | null | undefined): number => {
  if (typeof value !== 'number' || !isFinite(value)) return DEFAULT_PERCENT
  // 后端统一返回 0-1 的小数；兼容传入百分数的情况
  const percent = value <= 1 ? value * 100 : value
  return Math.max(MIN_PERCENT, Math.min(MAX_PERCENT, Math.round(percent)))
}

const WindowSettings: React.FC<WindowSettingsProps> = ({
  systemAudioListening,
  systemAudioSttConnected,
  systemAudioError,
}) => {
  const [available, setAvailable] = useState(false)
  // 统一以「百分数」作为内部状态单位，避免与后端小数混用
  const [opacityPercent, setOpacityPercent] = useState(DEFAULT_PERCENT)
  const [topmost, setTopmost] = useState(false)
  const [hideTaskbar, setHideTaskbar] = useState(false)
  const [captureExclude, setCaptureExclude] = useState(false)
  const [captureSupported, setCaptureSupported] = useState(true)
  const [open, setOpen] = useState(false)
  // 拖动过程中的实时值（避免频繁触发后端调用）
  const commitTimer = useRef<number | null>(null)

  // ── 初始化：等待桥接就绪并读取当前状态 ──
  // 说明：这里刻意不使用 cancelled 标志丢弃结果 —— React 18 StrictMode 下
  // 组件会「挂载 → 卸载 → 再挂载」，若用 cleanup 取消，首次请求的结果会被丢弃，
  // 而第二次请求又不一定及时返回，导致滑块一直停留在默认值（100%）。
  // 因此只要组件仍然存在（用 ref 判断），就允许写入状态。
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    const load = async () => {
      const ok = await waitForBridge()
      if (!mountedRef.current) return
      setAvailable(ok)
      if (!ok) return

      const state = await getWindowState()
      if (!mountedRef.current) return
      if (!state?.ok) return

      // 优先使用后端给出的百分数，回退到小数换算（两种单位都兼容）
      const percent =
        typeof state.opacity_percent === 'number'
          ? state.opacity_percent
          : toPercent(state.opacity)
      setOpacityPercent(Math.max(MIN_PERCENT, Math.min(MAX_PERCENT, Math.round(percent))))
      setTopmost(!!state.topmost)
      setHideTaskbar(!!state.hide_taskbar)
      setCaptureExclude(!!state.capture_exclude)
      setCaptureSupported(state.capture_supported !== false)
    }
    void load()

    return () => {
      mountedRef.current = false
      if (commitTimer.current !== null) window.clearTimeout(commitTimer.current)
    }
  }, [])

  /** 把透明度提交给 Python 端（节流：合并连续拖动产生的事件） */
  const commitOpacity = useCallback((percent: number) => {
    if (commitTimer.current !== null) window.clearTimeout(commitTimer.current)
    commitTimer.current = window.setTimeout(async () => {
      const result = await setWindowOpacity(percentToFraction(percent))
      if (!result.ok) {
        message.warning(result.error || '设置透明度失败')
      }
    }, 60)
  }, [])

  const handleOpacityChange = useCallback(
    (value: number | number[]) => {
      const next = Array.isArray(value) ? value[0] : value
      setOpacityPercent(next)
      commitOpacity(next)
    },
    [commitOpacity],
  )

  const handleTopmostChange = useCallback(async (checked: boolean) => {
    setTopmost(checked)
    const result = await setWindowTopmost(checked)
    if (!result.ok) {
      setTopmost(!checked)
      message.warning(result.error || '设置置顶失败')
    }
  }, [])

  const handleHideTaskbarChange = useCallback(async (checked: boolean) => {
    setHideTaskbar(checked)
    const result = await setTaskbarHidden(checked)
    if (!result.ok) {
      setHideTaskbar(!checked)
      message.warning(result.error || '设置任务栏图标失败')
    }
  }, [])

  const handleCaptureExcludeChange = useCallback(async (checked: boolean) => {
    setCaptureExclude(checked)
    const result = await applyCaptureExclude(checked)
    if (!result.ok) {
      setCaptureExclude(!checked)
      message.warning(result.error || '设置捕获排除失败')
    }
  }, [])

  const resetOpacity = useCallback(() => {
    setOpacityPercent(DEFAULT_PERCENT)
    commitOpacity(DEFAULT_PERCENT)
  }, [commitOpacity])

  /** 每次打开面板时重新同步一次窗口状态，避免显示与实际不一致 */
  const handleOpenChange = useCallback(async (next: boolean) => {
    setOpen(next)
    if (!next) return
    const state = await getWindowState()
    if (!state?.ok) return
    const percent =
      typeof state.opacity_percent === 'number' ? state.opacity_percent : toPercent(state.opacity)
    setOpacityPercent(Math.max(MIN_PERCENT, Math.min(MAX_PERCENT, Math.round(percent))))
    setTopmost(!!state.topmost)
    setHideTaskbar(!!state.hide_taskbar)
    setCaptureExclude(!!state.capture_exclude)
      setCaptureSupported(state.capture_supported !== false)
  }, [])

  // 配色在浏览器和独立窗口下都可用；透明度/置顶只在独立窗口模式下有意义
  const content = (
    <div style={{ width: 270 }}>
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <ThemeColorSettings />

        {/* 系统音频监听开关：浏览器与独立窗口下都可用 */}
        <SystemAudioSettings
          listening={systemAudioListening}
          sttConnected={systemAudioSttConnected}
          unavailableReason={systemAudioError}
        />

        {available && (
          <>
            <Divider style={{ margin: '8px 0' }} />

            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Text strong style={{ fontSize: 13 }}>
                窗口透明度
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {opacityPercent}%
              </Text>
            </Space>

            <Slider
              min={MIN_PERCENT}
              max={MAX_PERCENT}
              step={1}
              value={opacityPercent}
              onChange={handleOpacityChange}
              tooltip={{ formatter: (v) => `${v}%` }}
              marks={{ 20: '20', 50: '50', 100: '100' }}
              // marks 会渲染在滑块下方，需留出空间，否则会压住下一个元素
              style={{ marginBottom: 26 }}
            />

            <Button
              size="small"
              type="link"
              style={{ padding: 0, fontSize: 12, alignSelf: 'flex-start' }}
              onClick={resetOpacity}
            >
              恢复不透明
            </Button>

            <Divider style={{ margin: '8px 0' }} />

            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Text style={{ fontSize: 13 }}>窗口置顶</Text>
              <Switch size="small" checked={topmost} onChange={handleTopmostChange} />
            </Space>

            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Tooltip title="开启后任务栏与 Alt+Tab 中不显示该窗口">
                <Text style={{ fontSize: 13 }}>隐藏任务栏图标</Text>
              </Tooltip>
              <Switch size="small" checked={hideTaskbar} onChange={handleHideTaskbarChange} />
            </Space>

            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Tooltip
                title={
                  captureSupported
                    ? '开启后截屏 / 录屏中看不到该窗口内容'
                    : '当前窗口不支持该功能：浏览器 --app 模式下窗口属于浏览器进程，'
                      + 'Windows 不允许跨进程设置'
                }
              >
                <Text style={{ fontSize: 13, opacity: captureSupported ? 1 : 0.45 }}>
                  捕获排除
                </Text>
              </Tooltip>
              <Switch
                size="small"
                checked={captureExclude}
                disabled={!captureSupported}
                onChange={handleCaptureExcludeChange}
              />
            </Space>
          </>
        )}
      </Space>
    </div>
  )

  return (
    <Popover
      content={content}
      title="界面与窗口设置"
      trigger="click"
      placement="bottomRight"
      open={open}
      onOpenChange={handleOpenChange}
    >
      <Tooltip title="界面与窗口设置（配色 / 透明度 / 置顶）">
        <Button type="text" size="small" icon={<SettingOutlined />} />
      </Tooltip>
    </Popover>
  )
}

export default WindowSettings