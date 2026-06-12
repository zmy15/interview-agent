/**
 * 认证状态管理 — Zustand + localStorage 持久化
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { UserProfile } from '@/api/auth'

interface AuthState {
  // 令牌
  accessToken: string | null
  refreshToken: string | null

  // 用户信息
  user: UserProfile | null
  isAuthenticated: boolean

  // 加载状态
  isInitialized: boolean

  // Actions
  setTokens: (accessToken: string, refreshToken: string) => void
  setUser: (user: UserProfile) => void
  login: (accessToken: string, refreshToken: string, user: UserProfile) => void
  logout: () => void
  setInitialized: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      isInitialized: false,

      setTokens: (accessToken, refreshToken) =>
        set({ accessToken, refreshToken }),

      setUser: (user) =>
        set({ user, isAuthenticated: true }),

      login: (accessToken, refreshToken, user) =>
        set({
          accessToken,
          refreshToken,
          user,
          isAuthenticated: true,
        }),

      logout: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          isAuthenticated: false,
        }),

      setInitialized: () =>
        set({ isInitialized: true }),
    }),
    {
      name: 'interview-agent-auth',
      // 仅持久化令牌和用户信息
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
)
