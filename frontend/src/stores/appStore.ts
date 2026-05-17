import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AppState {
  highlightCode: boolean
  apiKey: string
  interviewDuration: number  // 面试时长（分钟）
  toggleHighlightCode: () => void
  setApiKey: (key: string) => void
  setInterviewDuration: (duration: number) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      highlightCode: true,
      apiKey: '',
      interviewDuration: 30,
      toggleHighlightCode: () =>
        set((state) => ({ highlightCode: !state.highlightCode })),
      setApiKey: (key: string) => set({ apiKey: key }),
      setInterviewDuration: (duration: number) => set({ interviewDuration: duration }),
    }),
    {
      name: 'interview-agent-app-prefs',
    },
  ),
)
