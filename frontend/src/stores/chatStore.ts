import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Message, ChatMode, PromptTemplates } from '@/types'

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
  useSearch: boolean
  codingEnabled: boolean

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
  setUseSearch: (use: boolean) => void
  setCodingEnabled: (enabled: boolean) => void

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
      useSearch: false,
      codingEnabled: false,

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

      setPosition: (name) => set({ selectedPosition: name }),
      setUseSearch: (use) => set({ useSearch: use }),
      setCodingEnabled: (enabled) => set({ codingEnabled: enabled }),

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
        interviewerMessages: state.interviewerMessages,
        candidateMessages: state.candidateMessages,
        selectedModel: state.selectedModel,
        thinkingEnabled: state.thinkingEnabled,
        reasoningEffort: state.reasoningEffort,
        selectedMode: state.selectedMode,
        selectedPosition: state.selectedPosition,
        useSearch: state.useSearch,
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
