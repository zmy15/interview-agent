import { useCallback, useRef } from 'react'
import { useChatStore } from '@/stores/chatStore'
import { useAppStore } from '@/stores/appStore'
import { streamChat } from '@/api/chat'

/** 单次发送最大消息数（含 system 消息发送约 30 轮对话，DeepSeek 1M 窗口绰绰有余） */
const MAX_SEND_MESSAGES = 80

export interface SendMessageOptions {
  /**
   * 消息在界面上的展示前缀（如「🎧 系统音频」）。
   * 只影响本地渲染，发给模型的仍是原始文本 —— 前缀不该污染上下文。
   */
  displayLabel?: string
}

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
    async (content: string, options: SendMessageOptions = {}) => {
      if (isStreaming) return

      const store = useChatStore.getState()
      const appStore = useAppStore.getState()

      // 添加用户消息。展示前缀只影响本地渲染，
      // 真正发给模型的 content 保持干净（见下方 trimmedMessages）。
      const userMsg = {
        role: 'user' as const,
        content: options.displayLabel ? `${options.displayLabel}：${content}` : content,
      }
      addMessage(userMsg)

      // 构建请求 messages（裁剪到最近 N 条，保留 system 消息由后端自动注入）
      // 展示前缀不能进入模型上下文，因此最后一条用干净的 content 覆盖
      const allMessages = [...store.messages, { role: 'user' as const, content }]
      const trimmedMessages = allMessages.length > MAX_SEND_MESSAGES
        ? allMessages.slice(-MAX_SEND_MESSAGES)
        : allMessages

      // 获取有效的 prompt override
      const promptOverride = store.promptOverrides[store.selectedMode] || undefined

      // 使用 getState() 获取最新值，避免 useCallback 闭包过期
      const latestCandidateLevel = store.candidateLevel || undefined
      const latestInterviewRound = store.interviewRound || undefined
      const latestInterviewPlan = store.interviewPlan

      // 创建 AbortController
      abortRef.current = new AbortController()

      await streamChat(
        {
          messages: trimmedMessages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
          mode: store.selectedMode,
          position_name: store.selectedPosition || undefined,
          jd_id: store.selectedJdId || undefined,
          use_search: store.useSearch,
          coding_enabled: store.codingEnabled,
          model: store.selectedModel || undefined,
          thinking_enabled: store.thinkingEnabled || undefined,
          reasoning_effort: store.thinkingEnabled ? store.reasoningEffort : undefined,
          prompt_notes: promptOverride,
          api_key: appStore.apiKey || undefined,
          resume_text: appStore.resumeText || undefined,
          code_context: appStore.codeText || undefined,
          candidate_level: latestCandidateLevel,
          interview_round: latestInterviewRound,
          // 传递面试计划参数给后端生成时间预算感知的 prompt
          interview_duration_minutes: appStore.interviewDuration,
          interview_question_count: latestInterviewPlan?.question_count || 0,
          interview_coding_min: latestInterviewPlan?.coding_reserved_min || 0,
          question_bank_ids: store.questionBankIds.length > 0 ? store.questionBankIds : undefined,
          question_bank_mode: store.questionBankIds.length > 0 ? store.questionBankMode : undefined,
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
    // 仅保留 isStreaming 用于发送守卫；其余动态值改用 getState() 实时读取，避免闭包过期
    [isStreaming],
  )

  const abort = useCallback(() => {
    abortRef.current?.abort()
    finishMessage()
  }, [finishMessage])

  return { sendMessage, abort, isStreaming }
}
