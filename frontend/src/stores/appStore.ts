import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UploadRecord, VoiceMode } from '@/types'

export type UploadType = 'resume' | 'code' | 'project'

/**
 * 侧边栏显示模式：
 *   expanded  —— 完整显示（图标 + 文字）
 *   collapsed —— 收成窄条，只留图标（antd Sider 的默认折叠行为，hover 有提示）
 *   hidden    —— 完全隐藏，内容区占满整屏（适合做题/演示时腾出横向空间）
 */
export type SiderMode = 'expanded' | 'collapsed' | 'hidden'

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

  // 系统音频监听（捕获电脑播放的声音 → 转文字 → 发到当前对话）
  systemAudioEnabled: boolean
  /** 捕获设备 id，空 = 系统默认播放设备 */
  systemAudioDevice: string
  /** 是否把识别出的问题自动发给 AI 回答 */
  systemAudioAutoAsk: boolean
  /** 运行时状态（由 ChatPage 的监听逻辑写入，供设置面板展示） */
  systemAudioListening: boolean
  systemAudioSttConnected: boolean
  systemAudioError: string | null

  /** 侧边栏是否收起（只看图标）/ 完全隐藏 —— 由 MainLayout 读取 */
  siderMode: SiderMode

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

  // 系统音频 actions
  setSystemAudioEnabled: (enabled: boolean) => void
  setSystemAudioDevice: (deviceId: string) => void
  setSystemAudioAutoAsk: (auto: boolean) => void
  setSystemAudioStatus: (status: {
    listening: boolean
    sttConnected: boolean
    error: string | null
  }) => void

  // 侧边栏 actions
  setSiderMode: (mode: SiderMode) => void
  /** 在 expanded ↔ collapsed 之间切换；hidden 时切回 expanded */
  toggleSiderCollapsed: () => void
  toggleSiderHidden: () => void
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

      systemAudioEnabled: true,
      systemAudioDevice: '',
      systemAudioAutoAsk: true,
      systemAudioListening: false,
      systemAudioSttConnected: false,
      systemAudioError: null,

      siderMode: 'expanded',

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

      setSystemAudioEnabled: (enabled) => set({ systemAudioEnabled: enabled }),
      setSystemAudioDevice: (deviceId) => set({ systemAudioDevice: deviceId }),
      setSystemAudioAutoAsk: (auto) => set({ systemAudioAutoAsk: auto }),
      setSystemAudioStatus: ({ listening, sttConnected, error }) =>
        set({
          systemAudioListening: listening,
          systemAudioSttConnected: sttConnected,
          systemAudioError: error,
        }),

      setSiderMode: (mode) => set({ siderMode: mode }),
      toggleSiderCollapsed: () =>
        set((state) => ({
          // 隐藏状态下按折叠键，语义上更接近「先出来，且是完整显示」
          siderMode: state.siderMode === 'expanded' ? 'collapsed' : 'expanded',
        })),
      toggleSiderHidden: () =>
        set((state) => ({
          siderMode: state.siderMode === 'hidden' ? 'expanded' : 'hidden',
        })),
    }),
    {
      name: 'interview-agent-app-prefs',
      // 存储版本号。改动默认值时**必须**递增，并写对应的 migrate：
      // zustand persist 会用 localStorage 里的旧值覆盖新默认值，
      // 因此不升版本的话，老用户永远看不到「默认开启」的效果
      // （他们的存储里写着 systemAudioEnabled: false）。
      version: 2,
      migrate: (persisted: unknown, from: number) => {
        const state = (persisted ?? {}) as Record<string, unknown>
        if (from < 2) {
          // v1 → v2：系统音频监听改为默认开启。
          // 这里刻意覆盖为 true，而不是保留旧值 —— 这正是本次升级的目的；
          // 若用户不想要，在设置里关掉即可（之后会正常持久化）。
          state.systemAudioEnabled = true
        }
        return state
      },
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
        systemAudioEnabled: state.systemAudioEnabled,
        systemAudioDevice: state.systemAudioDevice,
        systemAudioAutoAsk: state.systemAudioAutoAsk,
        siderMode: state.siderMode,
      }),
    },
  ),
)
