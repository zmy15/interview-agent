/**
 * 系统音频捕获 API — 抓取「电脑正在播放的声音」并实时转成文字
 *
 * 与截图答题对称：截图抓「屏幕上看到的」，这个抓「扬声器里放的」。
 * 面试时对方的提问多来自会议软件/视频/网页播放，麦克风录不到。
 */

import { apiClient } from './axiosClient'

export interface SystemAudioDevice {
  id: string
  name: string
  is_default: boolean
}

export interface SystemAudioInfoResponse {
  available: boolean
  error?: string | null
  devices: SystemAudioDevice[]
  configured_device?: string | null
  running: boolean
  block_ms?: number | null
  sample_rate?: number | null
}

export interface SystemAudioStartRequest {
  /** 留空则用系统默认播放设备 */
  device_id?: string
}

export interface SystemAudioStartResponse {
  running: boolean
  device: string
  device_id?: string | null
  stt_connected: boolean
  stt_error?: string | null
  sample_rate: number
  block_ms: number
}

export interface SystemAudioStatusResponse {
  available: boolean
  error?: string | null
  running: boolean
  device?: string | null
  seconds: number
  /** 近期峰值（0-1），用于音量可视化 */
  peak: number
  /** 近期 RMS（0-1） */
  rms: number
  /** 近期是否检测到声音 */
  voiced: boolean
  stt_connected: boolean
  stt_error?: string | null
  audio_error?: string | null
  transcript_count: number
}

export interface SystemAudioTranscriptLine {
  seq: number
  text: string
  /** partial=正在说，final=已断句 */
  kind: 'partial' | 'final'
  ts: number
}

export interface SystemAudioTranscriptResponse {
  lines: SystemAudioTranscriptLine[]
  latest_seq: number
  running: boolean
  stt_connected: boolean
  stt_error?: string | null
}

export const systemAudioApi = {
  info: async (): Promise<SystemAudioInfoResponse> => {
    const res = await apiClient.get<SystemAudioInfoResponse>('/system-audio/info')
    return res.data
  },

  devices: async (): Promise<SystemAudioDevice[]> => {
    const res = await apiClient.get<SystemAudioDevice[]>('/system-audio/devices')
    return res.data
  },

  status: async (): Promise<SystemAudioStatusResponse> => {
    const res = await apiClient.get<SystemAudioStatusResponse>('/system-audio/status')
    return res.data
  },

  start: async (data: SystemAudioStartRequest = {}): Promise<SystemAudioStartResponse> => {
    const res = await apiClient.post<SystemAudioStartResponse>('/system-audio/start', data)
    return res.data
  },

  stop: async (): Promise<SystemAudioStatusResponse> => {
    const res = await apiClient.post<SystemAudioStatusResponse>('/system-audio/stop')
    return res.data
  },

  /** 增量拉取：since 传上次拿到的最大 seq */
  transcript: async (since = 0): Promise<SystemAudioTranscriptResponse> => {
    const res = await apiClient.get<SystemAudioTranscriptResponse>('/system-audio/transcript', {
      params: { since },
    })
    return res.data
  },

  clear: async (): Promise<{ cleared: boolean; message: string }> => {
    const res = await apiClient.post<{ cleared: boolean; message: string }>('/system-audio/clear')
    return res.data
  },
}