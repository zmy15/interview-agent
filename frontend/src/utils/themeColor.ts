/**
 * 主题颜色工具 — 解析 / 对比度 / 派生 antd token
 *
 * 目标：用户只需选「背景色」和「文字色」，其余容器色、边框色、次级文字色
 * 自动按背景明暗派生，避免出现深底黑字或浅底白字这类不可读的组合。
 */

export interface Rgb {
  r: number
  g: number
  b: number
}

/** 解析 #rgb / #rrggbb / rgb() 形式的颜色为 RGB */
export function parseColor(input: string): Rgb | null {
  if (!input) return null
  const value = input.trim()

  const hex = value.match(/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i)
  if (hex) {
    let h = hex[1]
    if (h.length === 3) h = h.split('').map((c) => c + c).join('')
    return {
      r: parseInt(h.slice(0, 2), 16),
      g: parseInt(h.slice(2, 4), 16),
      b: parseInt(h.slice(4, 6), 16),
    }
  }

  const rgb = value.match(/^rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/i)
  if (rgb) {
    return { r: +rgb[1], g: +rgb[2], b: +rgb[3] }
  }

  return null
}

/** RGB → #rrggbb */
export function toHex({ r, g, b }: Rgb): string {
  const h = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0')
  return `#${h(r)}${h(g)}${h(b)}`
}

/** 相对亮度（WCAG），范围 0-1 */
export function luminance(color: string): number {
  const rgb = parseColor(color)
  if (!rgb) return 1
  const channel = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  }
  return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b)
}

/** 判断是否属于「深色」（亮度低于阈值） */
export function isDark(color: string): boolean {
  return luminance(color) < 0.5
}

/** WCAG 对比度（1-21） */
export function contrastRatio(a: string, b: string): number {
  const l1 = luminance(a)
  const l2 = luminance(b)
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1]
  return (hi + 0.05) / (lo + 0.05)
}

/** 在给定背景上挑一个可读的文字色（黑或白） */
export function readableTextColor(background: string): string {
  const light = luminance(background)
  // 以亮度直接判断，比对比度更直观
  return light > 0.5 ? '#1f1f1f' : '#ffffff'
}

/** 按比例把颜色向白（amount>0）或向黑（amount<0）混合 */
export function mix(color: string, amount: number): string {
  const rgb = parseColor(color)
  if (!rgb) return color
  const target = amount >= 0 ? 255 : 0
  const ratio = Math.abs(amount)
  return toHex({
    r: rgb.r + (target - rgb.r) * ratio,
    g: rgb.g + (target - rgb.g) * ratio,
    b: rgb.b + (target - rgb.b) * ratio,
  })
}

/** 带透明度的 rgba() */
export function withAlpha(color: string, alpha: number): string {
  const rgb = parseColor(color)
  if (!rgb) return color
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${alpha})`
}

export interface ThemeTokens {
  colorBgLayout: string
  colorBgContainer: string
  colorBgElevated: string
  colorText: string
  colorTextSecondary: string
  colorTextTertiary: string
  colorBorder: string
  colorBorderSecondary: string
  colorFillSecondary: string
}

/**
 * 根据背景色与文字色派生一组 antd token。
 * 深色背景下让容器色比底色略亮，浅色背景下比底色略暗，形成层次。
 */
export function deriveTokens(background: string, textColor: string): ThemeTokens {
  const dark = isDark(background)
  const secondary = mix(textColor, dark ? 0.35 : 0.45)
  const tertiary = mix(textColor, dark ? 0.5 : 0.6)
  const border = dark ? mix(background, 0.18) : mix(background, -0.12)

  return {
    colorBgLayout: background,
    colorBgContainer: dark ? mix(background, 0.06) : mix(background, 0.7),
    colorBgElevated: dark ? mix(background, 0.1) : '#ffffff',
    colorText: textColor,
    colorTextSecondary: secondary,
    colorTextTertiary: tertiary,
    colorBorder: border,
    colorBorderSecondary: border,
    colorFillSecondary: dark ? withAlpha(textColor, 0.12) : withAlpha(textColor, 0.06),
  }
}

export interface ThemePreset {
  key: string
  name: string
  background: string
  text: string
}

/** 预设配色方案（深色方案自动带浅色文字） */
export const THEME_PRESETS: ThemePreset[] = [
  { key: 'light', name: '默认浅色', background: '#ffffff', text: '#1f1f1f' },
  { key: 'soft', name: '护眼米色', background: '#f5f0e6', text: '#3b3226' },
  { key: 'green', name: '护眼绿', background: '#e8f3e8', text: '#1f3a1f' },
  { key: 'blue', name: '淡雅蓝', background: '#eaf2fb', text: '#1a3a5c' },
  { key: 'dark', name: '深色', background: '#1e1e1e', text: '#e8e8e8' },
  { key: 'midnight', name: '午夜蓝', background: '#141c2b', text: '#cfe0f5' },
  { key: 'sepia', name: '暗褐', background: '#2b2620', text: '#e6dccb' },
]