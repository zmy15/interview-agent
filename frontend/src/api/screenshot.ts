/**
 * 截图识别 API — 整屏截图 + 交给界面选中的模型识别题目并作答
 *
 * 模型与思考模式都跟随界面「模型选择器」：
 * 后端会用官方 /models 的 input_modalities 校验该模型能否看图，
 * 不支持时直接返回「不支持图片输入」。
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
  /** 当前生效的视觉模型（未选模型时由后端挑选，可能为空） */
  vision_model?: string | null
  /** 界面当前选中的模型 */
  selected_model?: string | null
  /** 选中的模型是否支持图片输入 */
  vision_supported?: boolean
  /** 账号下支持图片输入的模型，用于提示 */
  vision_models?: string[]
}

export interface CaptureRequest {
  /** 是否把鼠标光标画进截图 */
  include_cursor?: boolean
  /** 自定义提问，为空则使用后端 prompts/screenshot.txt */
  prompt?: string
  /** 界面选中的模型；不支持图片输入时后端会明确返回「不支持」 */
  model?: string
  api_key?: string
  save?: boolean
  /** 界面上的思考模式开关 */
  thinking_enabled?: boolean
  /** 思考模式下的推理强度 */
  reasoning_effort?: string
}

export interface CaptureResponse {
  answer: string
  model: string
  /** 本次实际使用的思考模式 */
  thinking_enabled?: boolean
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
  info: async (model?: string): Promise<ScreenshotInfoResponse> => {
    const res = await apiClient.get<ScreenshotInfoResponse>(
      '/screenshot/info',
      model ? { params: { model } } : undefined,
    )
    return res.data
  },

  capture: async (data: CaptureRequest): Promise<CaptureResponse> => {
    const res = await apiClient.post<CaptureResponse>('/screenshot/capture', data)
    return res.data
  },
}