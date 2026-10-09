import { request } from './client'
import type { ModelsResponse } from '@/types'

/**
 * 获取可用模型列表。
 *
 * 后端调用官方 GET /models 动态获取（模型名不再写死）。
 * API Key 由 client.ts 自动通过 X-DEEPSEEK-API-KEY 请求头带上，
 * 后端据此返回该账号下的模型。
 */
export async function getModels(refresh = false): Promise<ModelsResponse> {
  return request<ModelsResponse>('/chat/models', {
    params: refresh ? { refresh: 'true' } : undefined,
  })
}

export async function streamChat(
  body: {
    messages: { role: string; content: string }[]
    mode?: string
    position_name?: string
    jd_id?: string
    use_search?: boolean
    coding_enabled?: boolean
    model?: string
    thinking_enabled?: boolean
    reasoning_effort?: string
    prompt_notes?: string
    api_key?: string
    resume_text?: string
    code_context?: string
    candidate_level?: string
    interview_round?: string
    interview_duration_minutes?: number
    interview_question_count?: number
    interview_coding_min?: number
    // 题库选题（由 useSSE 传入，后端据此限制提问来源）
    question_bank_ids?: string[]
    question_bank_mode?: string
  },
  onReasoning: (chunk: string) => void,
  onContent: (chunk: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })

  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const errBody = await response.json()
      detail = errBody.detail || detail
    } catch {
      // ignore
    }
    onError(detail)
    return
  }

  const reader = response.body?.getReader()
  if (!reader) {
    onError('无法读取响应流')
    return
  }

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // 保留最后一个可能不完整的行
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6).trim()
          if (dataStr === '[DONE]') {
            onDone()
            return
          }
          try {
            const parsed = JSON.parse(dataStr)
            if (parsed.type === 'reasoning') {
              onReasoning(parsed.content)
            } else if (parsed.type === 'content') {
              onContent(parsed.content)
            } else if (parsed.type === 'error') {
              onError(parsed.content)
            }
          } catch {
            // 非 JSON 行，忽略
          }
        }
      }
    }
    onDone()
  } catch (err) {
    if ((err as Error).name === 'AbortError') {
      onDone()
    } else {
      onError((err as Error).message || '流式读取失败')
    }
  } finally {
    reader.releaseLock()
  }
}
