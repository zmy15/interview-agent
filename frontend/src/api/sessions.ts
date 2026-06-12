/**
 * 会话历史 API — 面试记录列表/详情/删除
 */

import { apiClient } from './axiosClient'

export interface SessionSummary {
  id: string
  mode: string
  candidate_level: string | null
  interview_round: string | null
  model_used: string | null
  coding_enabled: boolean
  duration_minutes: number
  questions_planned: number
  questions_answered: number
  status: string
  plan_snapshot: Record<string, unknown>
  started_at: string
  ended_at: string | null
  message_count: number
  has_report: boolean
}

export interface MessageDetail {
  id: number
  role: string
  content: string
  reasoning: string | null
  token_count: number
  created_at: string
}

export interface QARecordDetail {
  id: number
  question_number: number
  question: string
  answer: string
  answer_chars: number
  answer_duration_sec: number
}

export interface SessionDetail {
  id: string
  mode: string
  candidate_level: string | null
  interview_round: string | null
  model_used: string | null
  coding_enabled: boolean
  duration_minutes: number
  questions_planned: number
  questions_answered: number
  status: string
  plan_snapshot: Record<string, unknown>
  started_at: string
  ended_at: string | null
  messages: MessageDetail[]
  qa_records: QARecordDetail[]
  report: {
    content: string
    scores: Record<string, number>
    dimensions: Array<{ name: string; score: number; comment: string }>
  } | null
}

export interface SessionListResponse {
  sessions: SessionSummary[]
  total: number
  page: number
  page_size: number
}

export const sessionsApi = {
  /** 获取会话列表 */
  list: async (params: {
    page?: number
    page_size?: number
    status?: string
    mode?: string
  }): Promise<SessionListResponse> => {
    const res = await apiClient.get<SessionListResponse>('/sessions/', {
      params,
    })
    return res.data
  },

  /** 获取会话详情（含消息、QA、报告） */
  get: async (sessionId: string): Promise<SessionDetail> => {
    const res = await apiClient.get<SessionDetail>(`/sessions/${sessionId}`)
    return res.data
  },

  /** 删除会话 */
  delete: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/sessions/${sessionId}`)
  },
}
