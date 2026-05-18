import { request } from './client'
import type { ModelsResponse } from '@/types'

export async function getModels(): Promise<ModelsResponse> {
  return request<ModelsResponse>('/chat/models')
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
    prompt_override?: string
    api_key?: string
    resume_text?: string
    code_context?: string
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
