import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AppState {
  highlightCode: boolean
  apiKey: string
  interviewDuration: number  // 面试时长（分钟）
  resumeText: string         // 上传的简历文本
  codeText: string           // 上传的代码文本
  toggleHighlightCode: () => void
  setApiKey: (key: string) => void
  setInterviewDuration: (duration: number) => void
  setResumeText: (text: string) => void
  setCodeText: (text: string) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      highlightCode: true,
      apiKey: '',
      interviewDuration: 30,
      resumeText: '',
      codeText: '',
      toggleHighlightCode: () =>
        set((state) => ({ highlightCode: !state.highlightCode })),
      setApiKey: (key: string) => set({ apiKey: key }),
      setInterviewDuration: (duration: number) => set({ interviewDuration: duration }),
      setResumeText: (text: string) => set({ resumeText: text }),
      setCodeText: (text: string) => set({ codeText: text }),
    }),
    {
      name: 'interview-agent-app-prefs',
    },
  ),
)
