import { useCallback, useRef } from 'react'
import { useChatStore } from '@/stores/chatStore'
import { streamChat } from '@/api/chat'

export function useSSE() {
  const abortRef = useRef<AbortController | null>(null)
  const {
    addMessage,
    appendReasoning,
    appendContent,
    finishMessage,
    isStreaming,
    selectedModel,
    thinkingEnabled,
    reasoningEffort,
    selectedMode,
    selectedPosition,
    useSearch,
    promptOverrides,
    messages,
  } = useChatStore()

  const sendMessage = useCallback(
    async (content: string) => {
      if (isStreaming) return

      const store = useChatStore.getState()

      // 添加用户消息
      const userMsg = { role: 'user' as const, content }
      addMessage(userMsg)

      // 构建请求 messages
      const allMessages = [...store.messages, userMsg]

      // 获取有效的 prompt override
      const promptOverride = store.promptOverrides[store.selectedMode] || undefined

      // 创建 AbortController
      abortRef.current = new AbortController()

      await streamChat(
        {
          messages: allMessages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
          mode: selectedMode,
          position_name: selectedPosition || undefined,
          use_search: useSearch,
          model: selectedModel || undefined,
          thinking_enabled: thinkingEnabled || undefined,
          reasoning_effort: thinkingEnabled ? reasoningEffort : undefined,
          prompt_override: promptOverride,
        },
        (chunk) => appendReasoning(chunk),
        (chunk) => appendContent(chunk),
        () => finishMessage(),
        (error) => {
          finishMessage()
          // 追加错误消息
          const store = useChatStore.getState()
          store.addMessage({
            role: 'assistant',
            content: `❌ 错误: ${error}`,
          })
        },
        abortRef.current.signal,
      )
    },
    [
      isStreaming,
      addMessage,
      appendReasoning,
      appendContent,
      finishMessage,
      selectedModel,
      thinkingEnabled,
      reasoningEffort,
      selectedMode,
      selectedPosition,
      useSearch,
      promptOverrides,
      messages.length,
    ],
  )

  const abort = useCallback(() => {
    abortRef.current?.abort()
    finishMessage()
  }, [finishMessage])

  return { sendMessage, abort, isStreaming }
}
