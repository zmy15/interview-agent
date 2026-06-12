import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UploadRecord, VoiceMode } from '@/types'

export type UploadType = 'resume' | 'code' | 'project'

interface AppState {
  highlightCode: boolean
  apiKey: string
  interviewDuration: number  // 面试时长（分钟）
  resumeText: string         // 当前激活的简历文本
  codeText: string           // 当前激活的代码/项目文本（多文件拼接）
  activeResumeId: string | null  // 当前激活的简历 ID（单选）
  activeCodeIds: string[]        // 当前激活的代码/项目 ID 列表（多选）
  uploads: UploadRecord[]    // 本地缓存的已上传文件列表
  projectStructure: Record<string, string[]> | null  // 当前项目的文件结构
  projectTechStack: string[]  // 当前项目的技术栈

  // 语音设置
  voiceMode: VoiceMode
  autoPlayTTS: boolean
  ttsSpeed: number

  toggleHighlightCode: () => void
  setApiKey: (key: string) => void
  setInterviewDuration: (duration: number) => void
  setResumeText: (text: string) => void
  setCodeText: (text: string) => void
  setActiveResume: (record: UploadRecord | null) => void
  toggleActiveCode: (record: UploadRecord) => void
  setUploads: (uploads: UploadRecord[]) => void
  addUpload: (record: UploadRecord) => void
  removeUpload: (id: string) => void
  setProjectMeta: (structure: Record<string, string[]> | null, techStack: string[]) => void
  /** 根据 activeCodeIds + uploads 重新计算 codeText */
  recomputeCodeText: () => void

  // 语音 actions
  setVoiceMode: (mode: VoiceMode) => void
  setAutoPlayTTS: (auto: boolean) => void
  setTTSSpeed: (speed: number) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      highlightCode: true,
      apiKey: '',
      interviewDuration: 30,
      resumeText: '',
      codeText: '',
      activeResumeId: null,
      activeCodeIds: [],
      uploads: [],
      projectStructure: null,
      projectTechStack: [],

      voiceMode: 'manual',
      autoPlayTTS: false,
      ttsSpeed: 1.0,

      toggleHighlightCode: () =>
        set((state) => ({ highlightCode: !state.highlightCode })),
      setApiKey: (key: string) => set({ apiKey: key }),
      setInterviewDuration: (duration: number) => set({ interviewDuration: duration }),
      setResumeText: (text: string) => set({ resumeText: text }),
      setCodeText: (text: string) => set({ codeText: text }),

      setActiveResume: (record) => {
        if (!record) {
          set({ activeResumeId: null, resumeText: '' })
          return
        }
        set({
          activeResumeId: record.id,
          resumeText: record.text,
        })
      },

      toggleActiveCode: (record) => {
        set((state) => {
          const isActive = state.activeCodeIds.includes(record.id)
          let newIds: string[]
          if (isActive) {
            // 移除
            newIds = state.activeCodeIds.filter((id) => id !== record.id)
          } else {
            // 添加
            newIds = [...state.activeCodeIds, record.id]
          }
          // 重新拼接 codeText
          const allRecords = [...state.uploads]
          // 如果 record 不在 uploads 中，临时加入
          if (!allRecords.find((u) => u.id === record.id)) {
            allRecords.push(record)
          }
          const newCodeText = newIds
            .map((id) => {
              const r = allRecords.find((u) => u.id === id)
              return r ? `/* === ${r.filename} === */\n${r.text}` : ''
            })
            .filter(Boolean)
            .join('\n\n')
          return {
            activeCodeIds: newIds,
            codeText: newCodeText,
          }
        })
      },

      recomputeCodeText: () => {
        set((state) => {
          const newCodeText = state.activeCodeIds
            .map((id) => {
              const r = state.uploads.find((u) => u.id === id)
              return r ? `/* === ${r.filename} === */\n${r.text}` : ''
            })
            .filter(Boolean)
            .join('\n\n')
          return { codeText: newCodeText }
        })
      },

      setUploads: (uploads) =>
        set((state) => {
          const newCodeText = state.activeCodeIds
            .map((id) => {
              const r = uploads.find((u) => u.id === id)
              return r ? `/* === ${r.filename} === */\n${r.text}` : ''
            })
            .filter(Boolean)
            .join('\n\n')
          return { uploads, codeText: newCodeText }
        }),

      addUpload: (record) =>
        set((state) => {
          const newUploads = [record, ...state.uploads.filter((u) => u.id !== record.id)]
          const newCodeText = state.activeCodeIds
            .map((id) => {
              const r = newUploads.find((u) => u.id === id)
              return r ? `/* === ${r.filename} === */\n${r.text}` : ''
            })
            .filter(Boolean)
            .join('\n\n')
          return { uploads: newUploads, codeText: newCodeText }
        }),

      removeUpload: (id) =>
        set((state) => {
          const removed = state.uploads.find((u) => u.id === id)
          const newUploads = state.uploads.filter((u) => u.id !== id)
          const newActiveResumeId = state.activeResumeId === id ? null : state.activeResumeId
          const newActiveCodeIds = state.activeCodeIds.filter((cid) => cid !== id)
          // 重新计算 codeText
          const newCodeText = newActiveCodeIds
            .map((cid) => {
              const r = newUploads.find((u) => u.id === cid)
              return r ? `/* === ${r.filename} === */\n${r.text}` : ''
            })
            .filter(Boolean)
            .join('\n\n')
          return {
            uploads: newUploads,
            activeResumeId: newActiveResumeId,
            activeCodeIds: newActiveCodeIds,
            codeText: newCodeText,
            ...(removed?.type === 'resume' && state.activeResumeId === id
              ? { resumeText: '' }
              : {}),
            ...(removed?.type !== 'resume' && state.activeResumeId === id
              ? { projectStructure: null, projectTechStack: [] }
              : {}),
          }
        }),

      setProjectMeta: (structure, techStack) =>
        set({ projectStructure: structure, projectTechStack: techStack }),

      setVoiceMode: (mode) => set({ voiceMode: mode }),
      setAutoPlayTTS: (auto) => set({ autoPlayTTS: auto }),
      setTTSSpeed: (speed) => set({ ttsSpeed: speed }),
    }),
    {
      name: 'interview-agent-app-prefs',
      partialize: (state) => ({
        highlightCode: state.highlightCode,
        apiKey: state.apiKey,
        interviewDuration: state.interviewDuration,
        resumeText: state.resumeText,
        codeText: state.codeText,
        activeResumeId: state.activeResumeId,
        activeCodeIds: state.activeCodeIds.slice(0, 20),
        uploads: state.uploads.slice(0, 20),  // 最多缓存 20 条
        projectStructure: state.projectStructure,
        projectTechStack: state.projectTechStack,
        voiceMode: state.voiceMode,
        autoPlayTTS: state.autoPlayTTS,
        ttsSpeed: state.ttsSpeed,
      }),
    },
  ),
)
