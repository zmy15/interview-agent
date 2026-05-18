import { request } from './client'
import type { Message, ReportResponse, InterviewPlanRequest, InterviewPlanResponse, CandidateLevel, InterviewRound, QARecord } from '@/types'

export async function startInterview(body: {
  mode: string
  position_name?: string
  resume_text?: string
  code_context?: string
  model?: string
  candidate_level?: CandidateLevel
  interview_round?: InterviewRound
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

export async function generateReport(
  messages: Message[],
  mode: string,
  apiKey?: string,
  candidateLevel?: CandidateLevel,
  interviewRound?: InterviewRound,
  qaRecords?: QARecord[],
): Promise<ReportResponse> {
  return request<ReportResponse>('/interview/report', {
    method: 'POST',
    body: {
      messages,
      mode,
      api_key: apiKey || undefined,
      candidate_level: candidateLevel || undefined,
      interview_round: interviewRound || undefined,
      qa_records: qaRecords || [],
    },
  })
}

export async function getInterviewPlan(
  req: InterviewPlanRequest,
): Promise<InterviewPlanResponse> {
  return request<InterviewPlanResponse>('/interview/plan', {
    method: 'POST',
    body: req,
  })
}
