import { request } from './client'
import type { Message, ReportResponse } from '@/types'

export async function startInterview(body: {
  mode: string
  position_name?: string
  resume_text?: string
  code_context?: string
  model?: string
}): Promise<Message> {
  return request<Message>('/interview/start', {
    method: 'POST',
    body,
  })
}

export async function stopInterview(): Promise<{ message: string }> {
  return request<{ message: string }>('/interview/stop', {
    method: 'POST',
  })
}

export async function generateReport(messages: Message[], mode: string): Promise<ReportResponse> {
  return request<ReportResponse>('/interview/report', {
    method: 'POST',
    body: { messages, mode },
  })
}
