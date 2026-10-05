/**
 * 界面主题状态 — 背景色 / 文字色，本地持久化
 *
 * 仅存「背景色 + 文字色」两个原始选择，其余 token 由 deriveTokens 派生，
 * 避免把大量派生值写进 localStorage 后在升级时失效。
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { THEME_PRESETS, readableTextColor } from '@/utils/themeColor'

export interface ThemeState {
  /** 背景色（#rrggbb） */
  background: string
  /** 文字色（#rrggbb） */
  textColor: string
  /** 选择背景色时是否自动调整文字色以保证可读性 */
  autoContrast: boolean

  setBackground: (color: string, autoAdjustText?: boolean) => void
  setTextColor: (color: string) => void
  applyPreset: (key: string) => void
  setAutoContrast: (enabled: boolean) => void
  reset: () => void
}

const DEFAULT_BACKGROUND = '#ffffff'
const DEFAULT_TEXT = '#1f1f1f'

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      background: DEFAULT_BACKGROUND,
      textColor: DEFAULT_TEXT,
      autoContrast: true,

      setBackground: (color, autoAdjustText = true) => {
        const shouldAdjust = autoAdjustText && get().autoContrast
        set({
          background: color,
          // 深色背景自动切浅色文字，避免深底黑字看不清
          ...(shouldAdjust ? { textColor: readableTextColor(color) } : {}),
        })
      },

      setTextColor: (color) => set({ textColor: color }),

      applyPreset: (key) => {
        const preset = THEME_PRESETS.find((p) => p.key === key)
        if (!preset) return
        // 预设已自带配好的文字色，直接采用（不再自动覆盖）
        set({ background: preset.background, textColor: preset.text })
      },

      setAutoContrast: (enabled) => {
        set({ autoContrast: enabled })
        if (enabled) {
          set({ textColor: readableTextColor(get().background) })
        }
      },

      reset: () => set({ background: DEFAULT_BACKGROUND, textColor: DEFAULT_TEXT }),
    }),
    {
      name: 'interview-agent-theme',
      partialize: (s) => ({
        background: s.background,
        textColor: s.textColor,
        autoContrast: s.autoContrast,
      }),
    },
  ),
)

export { DEFAULT_BACKGROUND, DEFAULT_TEXT }