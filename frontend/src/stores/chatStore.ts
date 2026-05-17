import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Message, ChatMode, PromptTemplates } from '@/types'

interface ChatState {
  // 消息列表
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

  // Actions — 设置
  setModel: (model: string) => void
  setThinking: (enabled: boolean) => void
  setReasoningEffort: (effort: 'high' | 'max') => void
  setMode: (mode: ChatMode) => void
  setPosition: (name: string | null) => void
  setUseSearch: (use: boolean) => void

  // Actions — Prompt
  setPromptOverride: (mode: 'interviewer' | 'candidate', template: string) => void
  resetPromptOverride: (mode: 'interviewer' | 'candidate') => void
  getEffectivePrompt: (mode: 'interviewer' | 'candidate') => string

  // Actions — 持久化
  setHydrated: () => void
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
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

      promptOverrides: {},

      _hydrated: false,

      // 消息 actions
      addMessage: (msg) =>
        set((state) => ({
          messages: [...state.messages, msg],
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
            currentReasoning: '',
            currentContent: '',
            isStreaming: false,
          }))
        } else {
          set({ isStreaming: false })
        }
      },

      clearChat: () =>
        set({
          messages: [],
          currentReasoning: '',
          currentContent: '',
          isStreaming: false,
        }),

      // 设置 actions
      setModel: (model) => set({ selectedModel: model }),
      setThinking: (enabled) => set({ thinkingEnabled: enabled }),
      setReasoningEffort: (effort) => set({ reasoningEffort: effort }),
      setMode: (mode) => set({ selectedMode: mode }),
      setPosition: (name) => set({ selectedPosition: name }),
      setUseSearch: (use) => set({ useSearch: use }),

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
        messages: state.messages,
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
          state.setHydrated()
        }
      },
    },
  ),
)
