/**
 * 截图识别 API — 整屏截图 + DeepSeek 视觉提取题目并作答
 */

import { apiClient } from './axiosClient'

export interface MonitorItem {
  id: string
  name: string
  x: number
  y: number
  width: number
  height: number
}

export interface ScreenshotInfoResponse {
  available: boolean
  error?: string | null
  monitors: MonitorItem[]
  vision_model?: string | null
}

export interface CaptureRequest {
  /** 是否把鼠标光标画进截图 */
  include_cursor?: boolean
  /** 自定义提问，为空则使用后端 prompts/screenshot.txt */
  prompt?: string
  model?: string
  api_key?: string
  save?: boolean
}

export interface CaptureResponse {
  answer: string
  model: string
  /** 截取目标（固定主显示器） */
  monitor: string
  width: number
  height: number
  image_bytes: number
  image_path?: string | null
  elapsed_ms: number
  captured_at: string
}

export const screenshotApi = {
  info: async (): Promise<ScreenshotInfoResponse> => {
    const res = await apiClient.get<ScreenshotInfoResponse>('/screenshot/info')
    return res.data
  },

  capture: async (data: CaptureRequest): Promise<CaptureResponse> => {
    const res = await apiClient.post<CaptureResponse>('/screenshot/capture', data)
    return res.data
  },
}