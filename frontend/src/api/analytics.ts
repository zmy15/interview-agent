/**
 * 分析 API — 仪表盘/趋势/薄弱项/对比/统计
 */

import { apiClient } from './axiosClient'

export interface DashboardOverview {
  total_sessions: number
  total_questions_answered: number
  avg_session_duration_min: number
  sessions_this_week: number
  sessions_this_month: number
  completion_rate: number
  most_used_mode: string
  avg_report_score: number | null
  streak_days: number
}

export interface TrendPoint {
  date: string
  sessions: number
  avg_score: number | null
  questions_answered: number
}

export interface TrendData {
  points: TrendPoint[]
  period: string
}

export interface DimensionScore {
  name: string
  score: number
  comment: string
}

export interface WeaknessItem {
  dimension: string
  current_score: number
  target_score: number
  gap: number
  suggestion: string
  trend: 'improving' | 'declining' | 'stable'
}

export interface WeaknessAnalysis {
  dimensions: DimensionScore[]
  weaknesses: WeaknessItem[]
  strongest_dimension: string
  updated_at: string
}

export interface ComparisonData {
  sessions: Array<{
    index: number
    date: string
    mode: string
    questions_answered: number
    duration_minutes: number
    scores: Record<string, number>
    avg_score: number | null
  }>
  score_trend: Array<{ index: number; avg_score: number }>
  improvement_rate: number
}

export interface StatsSummary {
  total_practice_time_min: number
  total_chars_written: number
  avg_answer_length: number
  avg_thinking_time_sec: number
  top_tags: string[]
  sessions_by_mode: Record<string, number>
  sessions_by_level: Record<string, number>
  sessions_by_round: Record<string, number>
}

export const analyticsApi = {
  /** 仪表盘概览 */
  getDashboard: async (): Promise<DashboardOverview> => {
    const res = await apiClient.get<DashboardOverview>('/analytics/dashboard')
    return res.data
  },

  /** 进步趋势 */
  getProgress: async (days: number = 30): Promise<TrendData> => {
    const res = await apiClient.get<TrendData>('/analytics/progress', {
      params: { days },
    })
    return res.data
  },

  /** 薄弱项分析 */
  getWeakness: async (): Promise<WeaknessAnalysis> => {
    const res = await apiClient.get<WeaknessAnalysis>('/analytics/weakness')
    return res.data
  },

  /** 多次面试对比 */
  getComparison: async (limit: number = 10): Promise<ComparisonData> => {
    const res = await apiClient.get<ComparisonData>('/analytics/comparison', {
      params: { limit },
    })
    return res.data
  },

  /** 统计汇总 */
  getStats: async (): Promise<StatsSummary> => {
    const res = await apiClient.get<StatsSummary>('/analytics/stats')
    return res.data
  },
}
