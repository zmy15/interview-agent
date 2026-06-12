/**
 * 题库 API — CRUD + 导入 + 分类
 */

import { apiClient } from './axiosClient'

export interface QuestionItem {
  id: string
  title: string
  content: string
  category: string
  difficulty: 'easy' | 'medium' | 'hard'
  tags: string[]
  expected_answer: string
  is_public: boolean
  usage_count: number
  created_at: string
}

export interface QuestionListResponse {
  questions: QuestionItem[]
  total: number
  page: number
  page_size: number
}

export interface QuestionCreateRequest {
  title: string
  content: string
  category: string
  difficulty: string
  tags: string[]
  expected_answer: string
}

export interface ImportResponse {
  imported: number
  skipped: number
  message: string
}

export const questionBankApi = {
  list: async (params: {
    page?: number
    page_size?: number
    category?: string
    difficulty?: string
    search?: string
  }): Promise<QuestionListResponse> => {
    const res = await apiClient.get<QuestionListResponse>('/question-bank/', { params })
    return res.data
  },

  get: async (id: string): Promise<QuestionItem> => {
    const res = await apiClient.get<QuestionItem>(`/question-bank/${id}`)
    return res.data
  },

  create: async (data: QuestionCreateRequest): Promise<QuestionItem> => {
    const res = await apiClient.post<QuestionItem>('/question-bank/', data)
    return res.data
  },

  update: async (id: string, data: QuestionCreateRequest): Promise<QuestionItem> => {
    const res = await apiClient.put<QuestionItem>(`/question-bank/${id}`, data)
    return res.data
  },

  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/question-bank/${id}`)
  },

  importLeetcode: async (): Promise<ImportResponse> => {
    const res = await apiClient.post<ImportResponse>('/question-bank/import/leetcode')
    return res.data
  },

  categories: async (): Promise<{ categories: { name: string; count: number }[] }> => {
    const res = await apiClient.get<{ categories: { name: string; count: number }[] }>(
      '/question-bank/categories/list',
    )
    return res.data
  },
}
