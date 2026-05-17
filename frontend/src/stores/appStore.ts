import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AppState {
  highlightCode: boolean
  toggleHighlightCode: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      highlightCode: true,
      toggleHighlightCode: () =>
        set((state) => ({ highlightCode: !state.highlightCode })),
    }),
    {
      name: 'interview-agent-app-prefs',
    },
  ),
)
