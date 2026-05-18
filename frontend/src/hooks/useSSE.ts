import { useCallback, useRef } from 'react'
import { useChatStore } from '@/stores/chatStore'
import { useAppStore } from '@/stores/appStore'
import { streamChat } from '@/api/chat'

/** 单次发送最大消息数（含 system 消息发送约 30 轮对话，DeepSeek 1M 窗口绰绰有余） */
const MAX_SEND_MESSAGES = 80

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
    selectedJdId,
    useSearch,
    codingEnabled,
    promptOverrides,
    messages,
    candidateLevel,
    interviewRound,
    interviewPlan,
  } = useChatStore()

  const sendMessage = useCallback(
    async (content: string) => {
      if (isStreaming) return

      const store = useChatStore.getState()
      const appStore = useAppStore.getState()

      // 添加用户消息
      const userMsg = { role: 'user' as const, content }
      addMessage(userMsg)

      // 构建请求 messages（裁剪到最近 N 条，保留 system 消息由后端自动注入）
      const allMessages = [...store.messages, userMsg]
      const trimmedMessages = allMessages.length > MAX_SEND_MESSAGES
        ? allMessages.slice(-MAX_SEND_MESSAGES)
        : allMessages

      // 获取有效的 prompt override
      const promptOverride = store.promptOverrides[store.selectedMode] || undefined

      // 创建 AbortController
      abortRef.current = new AbortController()

      await streamChat(
        {
          messages: trimmedMessages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
          mode: selectedMode,
          position_name: selectedPosition || undefined,
          jd_id: selectedJdId || undefined,
          use_search: useSearch,
          coding_enabled: codingEnabled,
          model: selectedModel || undefined,
          thinking_enabled: thinkingEnabled || undefined,
          reasoning_effort: thinkingEnabled ? reasoningEffort : undefined,
          prompt_override: promptOverride,
          api_key: appStore.apiKey || undefined,
          resume_text: appStore.resumeText || undefined,
          code_context: appStore.codeText || undefined,
          candidate_level: candidateLevel || undefined,
          interview_round: interviewRound || undefined,
          // 传递面试计划参数给后端生成时间预算感知的 prompt
          interview_duration_minutes: appStore.interviewDuration,
          interview_question_count: interviewPlan?.question_count || 0,
          interview_coding_min: interviewPlan?.coding_reserved_min || 0,
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
      selectedJdId,
      useSearch,
      codingEnabled,
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
