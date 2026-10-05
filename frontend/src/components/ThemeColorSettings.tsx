/**
 * 界面配色设置 — 背景色 / 文字色 + 预设方案
 *
 * 颜色保存在 themeStore（localStorage 持久化），由 App.tsx 的 ConfigProvider
 * 应用到全局；本组件只负责选择交互。
 */

import { useCallback } from 'react'
import { ColorPicker, Space, Typography, Switch, Tooltip, Button, Divider, theme } from 'antd'
import { BgColorsOutlined, FontColorsOutlined } from '@ant-design/icons'
import { useThemeStore } from '@/stores/themeStore'
import { THEME_PRESETS, contrastRatio, readableTextColor } from '@/utils/themeColor'

const { Text } = Typography

/** 对比度是否达到可读标准（WCAG AA 正文为 4.5） */
const AA_THRESHOLD = 4.5

const ThemeColorSettings: React.FC = () => {
  const { token } = theme.useToken()
  const background = useThemeStore((s) => s.background)
  const textColor = useThemeStore((s) => s.textColor)
  const autoContrast = useThemeStore((s) => s.autoContrast)
  const setBackground = useThemeStore((s) => s.setBackground)
  const setTextColor = useThemeStore((s) => s.setTextColor)
  const applyPreset = useThemeStore((s) => s.applyPreset)
  const setAutoContrast = useThemeStore((s) => s.setAutoContrast)
  const reset = useThemeStore((s) => s.reset)

  const ratio = contrastRatio(background, textColor)
  const lowContrast = ratio < AA_THRESHOLD

  /** 手动改文字色时关闭自动对比，否则会被立刻覆盖 */
  const handleTextColorChange = useCallback(
    (value: string) => {
      if (autoContrast) setAutoContrast(false)
      setTextColor(value)
    },
    [autoContrast, setAutoContrast, setTextColor],
  )

  const fixContrast = useCallback(() => {
    setTextColor(readableTextColor(background))
  }, [background, setTextColor])

  return (
    <Space direction="vertical" size={6} style={{ width: '100%' }}>
      <Text strong style={{ fontSize: 13 }}>
        界面配色
      </Text>

      {/* ── 预设方案 ── */}
      <Space wrap size={4}>
        {THEME_PRESETS.map((preset) => {
          const active = preset.background.toLowerCase() === background.toLowerCase()
          return (
            <Tooltip key={preset.key} title={preset.name}>
              <button
                type="button"
                onClick={() => applyPreset(preset.key)}
                aria-label={preset.name}
                style={{
                  width: 26,
                  height: 26,
                  borderRadius: 6,
                  cursor: 'pointer',
                  padding: 0,
                  background: preset.background,
                  // 边框用预设自身文字色，直观展示该方案的配色
                  border: active
                    ? `2px solid ${token.colorPrimary}`
                    : `1px solid ${token.colorBorderSecondary}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: preset.text,
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                A
              </button>
            </Tooltip>
          )
        })}
      </Space>

      {/* ── 背景色 / 文字色 ── */}
      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <Space size={4}>
          <BgColorsOutlined style={{ fontSize: 13, color: token.colorTextSecondary }} />
          <Text style={{ fontSize: 13 }}>背景色</Text>
        </Space>
        <ColorPicker
          size="small"
          value={background}
          onChange={(c) => setBackground(c.toHexString())}
          disabledAlpha
          showText
        />
      </Space>

      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <Space size={4}>
          <FontColorsOutlined style={{ fontSize: 13, color: token.colorTextSecondary }} />
          <Text style={{ fontSize: 13 }}>文字色</Text>
        </Space>
        <ColorPicker
          size="small"
          value={textColor}
          onChange={(c) => handleTextColorChange(c.toHexString())}
          disabledAlpha
          showText
        />
      </Space>

      {/* ── 自动对比 ── */}
      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
        <Tooltip title="选择背景色时自动把文字色调整为可读的颜色（深底配浅字）">
          <Text style={{ fontSize: 13 }}>自动调整文字色</Text>
        </Tooltip>
        <Switch size="small" checked={autoContrast} onChange={setAutoContrast} />
      </Space>

      {/* ── 对比度提示 ── */}
      <Space size={6} style={{ width: '100%', justifyContent: 'space-between' }}>
        <Text type={lowContrast ? 'warning' : 'secondary'} style={{ fontSize: 12 }}>
          对比度 {ratio.toFixed(1)}:1{lowContrast ? '（偏低，可能看不清）' : ''}
        </Text>
        {lowContrast && (
          <Button size="small" type="link" style={{ padding: 0, fontSize: 12 }} onClick={fixContrast}>
            自动修正
          </Button>
        )}
      </Space>

      <Divider style={{ margin: '4px 0' }} />

      <Button size="small" type="link" style={{ padding: 0, fontSize: 12, alignSelf: 'flex-start' }} onClick={reset}>
        恢复默认配色
      </Button>
    </Space>
  )
}

export default ThemeColorSettings