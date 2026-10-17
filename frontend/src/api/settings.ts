/**
 * 用户设置 API —— API Key 的加密存储
 *
 * 密钥不再只存在浏览器 localStorage 里：桌面版 native 窗口是 pywebview，
 * private_mode 默认 True，localStorage 每次重启都被清空（表现为「配置过，
 * 重启就没了」）。改为存到服务端数据库（Fernet 加密），本地只留一个掩码
 * 用于界面展示。
 */
import { request } from './client'

export interface ApiKeyStatus {
  /** 服务端是否已保存该用户的 API Key */
  configured: boolean
  /** 掩码提示，形如 sk-6680…d69d；未配置时为空串 */
  hint: string
}

export const settingsApi = {
  /** 查询是否已配置（只返回掩码，不返回明文） */
  getApiKey: () => request<ApiKeyStatus>('/settings/api-key'),

  /** 保存（覆盖）API Key */
  saveApiKey: (apiKey: string) =>
    request<ApiKeyStatus>('/settings/api-key', {
      method: 'PUT',
      body: { api_key: apiKey },
    }),

  /** 清除 API Key，之后回退到服务端 .env 配置 */
  clearApiKey: () =>
    request<ApiKeyStatus>('/settings/api-key', { method: 'DELETE' }),
}