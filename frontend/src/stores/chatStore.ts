import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Message, ChatMode, PromptTemplates, CandidateLevel, InterviewRound, QARecord, InterviewPlanResponse, AnswerLength } from '@/types'

interface ChatState {
  // 按模式分别存储的消息历史
  interviewerMessages: Message[]
  candidateMessages: Message[]

  // 当前激活的消息列表（派生自 selectedMode）
  messages: Message[]
  isStreaming: boolean
  currentReasoning: string
  currentContent: string

  // 设置
  selectedModel: string
  thinkingEnabled: boolean
  reasoningEffort: 'high' | 'max'
  selectedMode: ChatMode
  selectedPosition: string | null
  selectedJdId: string | null
  useSearch: boolean
  codingEnabled: boolean

  // 面试配置（新增）
  candidateLevel: CandidateLevel | null
  interviewRound: InterviewRound | null
  answerLength: AnswerLength

  // 练习状态（持久化，跨页面保持）
  practiceActive: boolean
  practiceStartTime: number | null  // 练习开始时间戳（毫秒），用于精确计时
  interviewPlan: InterviewPlanResponse | null

  // QA 记录（用于报告生成）
  qaRecords: QARecord[]
  totalUserChars: number  // 候选人累计回答字数（保留兼容，但主要用 wall-clock 计时）

  // Prompt 微调
  promptOverrides: PromptTemplates

  // 持久化状态
  _hydrated: boolean

  // Actions — 消息
  addMessage: (msg: Message) => void
  appendReasoning: (chunk: string) => void
  appendContent: (chunk: string) => void
  finishMessage: () => void
  clearChat: () => void
  clearAllChats: () => void

  // Actions — 设置
  setModel: (model: string) => void
  setThinking: (enabled: boolean) => void
  setReasoningEffort: (effort: 'high' | 'max') => void
  setMode: (mode: ChatMode) => void
  setPosition: (name: string | null) => void
  setJdId: (jdId: string | null) => void
  setUseSearch: (use: boolean) => void
  setCodingEnabled: (enabled: boolean) => void

  // Actions — 面试配置
  setCandidateLevel: (level: CandidateLevel | null) => void
  setInterviewRound: (round: InterviewRound | null) => void
  setAnswerLength: (length: AnswerLength) => void

  // Actions — 练习状态
  setPracticeActive: (active: boolean) => void
  setInterviewPlan: (plan: InterviewPlanResponse | null) => void
  resetPractice: () => void

  // Actions — QA 记录
  addQARecord: (record: QARecord) => void
  clearQARecords: () => void
  addUserChars: (chars: number) => void

  // Actions — Prompt
  setPromptOverride: (mode: 'interviewer' | 'candidate', template: string) => void
  resetPromptOverride: (mode: 'interviewer' | 'candidate') => void
  getEffectivePrompt: (mode: 'interviewer' | 'candidate') => string

  // Actions — 持久化
  setHydrated: () => void
}

/** 辅助：将当前 messages 保存到对应模式槽位 */
function _saveCurrentToSlot(state: ChatState): Partial<ChatState> {
  if (state.selectedMode === 'interviewer') {
    return { interviewerMessages: state.messages }
  } else {
    return { candidateMessages: state.messages }
  }
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      interviewerMessages: [],
      candidateMessages: [],
      messages: [],
      isStreaming: false,
      currentReasoning: '',
      currentContent: '',

      selectedModel: '',
      thinkingEnabled: false,
      reasoningEffort: 'high',
      selectedMode: 'interviewer',
      selectedPosition: null,
      selectedJdId: null,
      useSearch: false,
      codingEnabled: false,

      candidateLevel: null,
      interviewRound: null,
      answerLength: 'medium' as AnswerLength,

      practiceActive: false,
      practiceStartTime: null,
      interviewPlan: null,

      qaRecords: [],
      totalUserChars: 0,

      promptOverrides: {},

      _hydrated: false,

      // 消息 actions
      addMessage: (msg) =>
        set((state) => ({
          messages: [...state.messages, msg],
          ..._saveCurrentToSlot({ ...state, messages: [...state.messages, msg] }),
        })),

      appendReasoning: (chunk) =>
        set((state) => ({
          currentReasoning: state.currentReasoning + chunk,
          isStreaming: true,
        })),

      appendContent: (chunk) =>
        set((state) => ({
          currentContent: state.currentContent + chunk,
          isStreaming: true,
        })),

      finishMessage: () => {
        const { currentReasoning, currentContent } = get()
        if (currentContent || currentReasoning) {
          const msg: Message = {
            role: 'assistant',
            content: currentContent,
            reasoning: currentReasoning || undefined,
          }
          set((state) => ({
            messages: [...state.messages, msg],
            ..._saveCurrentToSlot({ ...state, messages: [...state.messages, msg] }),
            currentReasoning: '',
            currentContent: '',
            isStreaming: false,
          }))
        } else {
          set({ isStreaming: false })
        }
      },

      clearChat: () =>
        set((state) => ({
          messages: [],
          currentReasoning: '',
          currentContent: '',
          isStreaming: false,
          ..._saveCurrentToSlot({ ...state, messages: [] }),
        })),

      clearAllChats: () =>
        set({
          interviewerMessages: [],
          candidateMessages: [],
          messages: [],
          currentReasoning: '',
          currentContent: '',
          isStreaming: false,
        }),

      // 设置 actions
      setModel: (model) => set({ selectedModel: model }),
      setThinking: (enabled) => set({ thinkingEnabled: enabled }),
      setReasoningEffort: (effort) => set({ reasoningEffort: effort }),

      setMode: (mode) => {
        const state = get()
        if (state.selectedMode === mode) return  // 同一模式不切换

        // 1. 保存当前消息到旧模式槽位
        const saveOld = state.selectedMode === 'interviewer'
          ? { interviewerMessages: state.messages }
          : { candidateMessages: state.messages }

        // 2. 从新模式槽位恢复消息
        const newMessages = mode === 'interviewer'
          ? state.interviewerMessages
          : state.candidateMessages

        set({
          selectedMode: mode,
          messages: newMessages,
          currentReasoning: '',
          currentContent: '',
          isStreaming: false,
          ...saveOld,
        })
      },

      setPosition: (name) => set({ selectedPosition: name, selectedJdId: null }),
      setJdId: (jdId) => set({ selectedJdId: jdId }),
      setUseSearch: (use) => set({ useSearch: use }),
      setCodingEnabled: (enabled) => set({ codingEnabled: enabled }),

      // 面试配置 actions
      setCandidateLevel: (level) => set({ candidateLevel: level }),
      setInterviewRound: (round) => set({ interviewRound: round }),
      setAnswerLength: (length) => set({ answerLength: length }),

      // 练习状态 actions
      setPracticeActive: (active) => set({
        practiceActive: active,
        practiceStartTime: active ? Date.now() : null,
      }),
      setInterviewPlan: (plan) => set({ interviewPlan: plan }),
      resetPractice: () => set({
        practiceActive: false,
        practiceStartTime: null,
        interviewPlan: null,
        qaRecords: [],
        totalUserChars: 0,
      }),

      // QA 记录 actions
      addQARecord: (record) =>
        set((state) => ({
          qaRecords: [...state.qaRecords, record],
          totalUserChars: state.totalUserChars + record.answer_chars,
        })),
      clearQARecords: () => set({ qaRecords: [], totalUserChars: 0 }),
      addUserChars: (chars) =>
        set((state) => ({ totalUserChars: state.totalUserChars + chars })),

      // Prompt actions
      setPromptOverride: (mode, template) =>
        set((state) => ({
          promptOverrides: {
            ...state.promptOverrides,
            [mode]: template,
          },
        })),

      resetPromptOverride: (mode) =>
        set((state) => {
          const newOverrides = { ...state.promptOverrides }
          delete newOverrides[mode]
          return { promptOverrides: newOverrides }
        }),

      getEffectivePrompt: (mode) => {
        const overrides = get().promptOverrides
        return overrides[mode] || ''
      },

      setHydrated: () => set({ _hydrated: true }),
    }),
    {
      name: 'interview-agent-chat-state',
      partialize: (state) => ({
        interviewerMessages: state.interviewerMessages.slice(-100),
        candidateMessages: state.candidateMessages.slice(-100),
        selectedModel: state.selectedModel,
        thinkingEnabled: state.thinkingEnabled,
        reasoningEffort: state.reasoningEffort,
        selectedMode: state.selectedMode,
        selectedPosition: state.selectedPosition,
        selectedJdId: state.selectedJdId,
        useSearch: state.useSearch,
        codingEnabled: state.codingEnabled,
        candidateLevel: state.candidateLevel,
        interviewRound: state.interviewRound,
        answerLength: state.answerLength,
        practiceActive: state.practiceActive,
        interviewPlan: state.interviewPlan,
        qaRecords: state.qaRecords.slice(-30),
        totalUserChars: state.totalUserChars,
        promptOverrides: state.promptOverrides,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          // 从 localStorage 恢复后，根据 selectedMode 恢复对应的消息列表
          const restoredMessages = state.selectedMode === 'interviewer'
            ? state.interviewerMessages
            : state.candidateMessages
          state.messages = restoredMessages
          state.setHydrated()
        }
      },
    },
  ),
)
