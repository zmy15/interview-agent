/**
 * 认证 API — 注册/登录/刷新令牌/个人信息
 */

import { apiClient } from './axiosClient'

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  display_name?: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: {
    id: string
    email: string
    display_name: string
    role: string
  }
}

export interface UserProfile {
  id: string
  email: string
  display_name: string
  avatar_url?: string
  role: string
  created_at: string
}

/** 当前认证模式（桌面版单用户模式下 auth_required 为 false） */
export interface AuthModeResponse {
  auth_required: boolean
  user?: {
    id: string
    email: string
    display_name: string
    role: string
  } | null
}

export const authApi = {
  /** 查询认证模式（无需 token，用于桌面版跳过登录页） */
  getMode: async (): Promise<AuthModeResponse> => {
    const res = await apiClient.get<AuthModeResponse>('/auth/mode')
    return res.data
  },

  /** 用户注册 */
  register: async (data: RegisterRequest): Promise<TokenResponse> => {
    const res = await apiClient.post<TokenResponse>('/auth/register', data)
    return res.data
  },

  /** 用户登录 */
  login: async (data: LoginRequest): Promise<TokenResponse> => {
    const res = await apiClient.post<TokenResponse>('/auth/login', data)
    return res.data
  },

  /** 刷新令牌 */
  refreshToken: async (refreshToken: string): Promise<TokenResponse> => {
    const res = await apiClient.post<TokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    })
    return res.data
  },

  /** 获取当前用户信息 */
  getMe: async (): Promise<UserProfile> => {
    const res = await apiClient.get<UserProfile>('/auth/me')
    return res.data
  },

  /** 更新个人信息 */
  updateProfile: async (data: {
    display_name?: string
    avatar_url?: string
  }): Promise<UserProfile> => {
    const res = await apiClient.put<UserProfile>('/auth/me', data)
    return res.data
  },
}
