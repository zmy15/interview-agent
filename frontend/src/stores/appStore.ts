import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UploadRecord } from '@/types'

export type UploadType = 'resume' | 'code' | 'project'

interface AppState {
  highlightCode: boolean
  apiKey: string
  interviewDuration: number  // 面试时长（分钟）
  resumeText: string         // 当前激活的简历文本
  codeText: string           // 当前激活的代码/项目文本
  activeUploadId: string | null  // 当前选中的上传记录 ID
  uploads: UploadRecord[]    // 本地缓存的已上传文件列表
  projectStructure: Record<string, string[]> | null  // 当前项目的文件结构
  projectTechStack: string[]  // 当前项目的技术栈

  toggleHighlightCode: () => void
  setApiKey: (key: string) => void
  setInterviewDuration: (duration: number) => void
  setResumeText: (text: string) => void
  setCodeText: (text: string) => void
  setActiveUpload: (record: UploadRecord | null) => void
  setUploads: (uploads: UploadRecord[]) => void
  addUpload: (record: UploadRecord) => void
  removeUpload: (id: string) => void
  setProjectMeta: (structure: Record<string, string[]> | null, techStack: string[]) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      highlightCode: true,
      apiKey: '',
      interviewDuration: 30,
      resumeText: '',
      codeText: '',
      activeUploadId: null,
      uploads: [],
      projectStructure: null,
      projectTechStack: [],

      toggleHighlightCode: () =>
        set((state) => ({ highlightCode: !state.highlightCode })),
      setApiKey: (key: string) => set({ apiKey: key }),
      setInterviewDuration: (duration: number) => set({ interviewDuration: duration }),
      setResumeText: (text: string) => set({ resumeText: text }),
      setCodeText: (text: string) => set({ codeText: text }),

      setActiveUpload: (record) => {
        if (!record) {
          set({ activeUploadId: null })
          return
        }
        set({
          activeUploadId: record.id,
          ...(record.type === 'resume'
            ? { resumeText: record.text }
            : { codeText: record.text }),
        })
      },

      setUploads: (uploads) => set({ uploads }),

      addUpload: (record) =>
        set((state) => ({
          uploads: [record, ...state.uploads.filter((u) => u.id !== record.id)],
        })),

      removeUpload: (id) =>
        set((state) => {
          const removed = state.uploads.find((u) => u.id === id)
          return {
            uploads: state.uploads.filter((u) => u.id !== id),
            activeUploadId: state.activeUploadId === id ? null : state.activeUploadId,
            ...(removed?.type === 'resume' && state.activeUploadId === id
              ? { resumeText: '' }
              : {}),
            ...(removed?.type !== 'resume' && state.activeUploadId === id
              ? { codeText: '', projectStructure: null, projectTechStack: [] }
              : {}),
          }
        }),

      setProjectMeta: (structure, techStack) =>
        set({ projectStructure: structure, projectTechStack: techStack }),
    }),
    {
      name: 'interview-agent-app-prefs',
      partialize: (state) => ({
        highlightCode: state.highlightCode,
        apiKey: state.apiKey,
        interviewDuration: state.interviewDuration,
        resumeText: state.resumeText,
        codeText: state.codeText,
        activeUploadId: state.activeUploadId,
        uploads: state.uploads.slice(0, 20),  // 最多缓存 20 条
        projectStructure: state.projectStructure,
        projectTechStack: state.projectTechStack,
      }),
    },
  ),
)
