/**
 * 路由守卫 — 未登录时重定向到登录页
 *
 * 单用户模式（桌面版，AUTH_REQUIRED=false）：
 *   后端 /auth/mode 返回 auth_required=false 和本机账号信息，
 *   这里直接把它写进 authStore，**不显示登录页**。
 *   桌面版本就是「一个人的本机应用」，每次启动都要求登录没有意义。
 *
 * 注意：探测失败时按「需要登录」处理（fail-safe），
 * 避免后端异常时前端误以为已登录、进去后满屏 401。
 */

import React, { useEffect, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '@/stores/authStore'
import { authApi } from '@/api/auth'

interface AuthGuardProps {
  children: React.ReactNode
}

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const { isAuthenticated, isInitialized, setInitialized, setUser } = useAuthStore()
  const location = useLocation()
  // 是否已确认过认证模式（避免每次渲染都请求）
  const [modeChecked, setModeChecked] = useState(false)

  useEffect(() => {
    let cancelled = false

    const init = async () => {
      // 已经有登录态（localStorage 恢复或刚登录过）：无需再探测
      if (isAuthenticated) {
        if (!cancelled) {
          setModeChecked(true)
          if (!isInitialized) setInitialized()
        }
        return
      }

      try {
        const mode = await authApi.getMode()
        if (cancelled) return
        if (!mode.auth_required && mode.user) {
          // 单用户模式：直接建立本地会话
          setUser({
            id: mode.user.id,
            email: mode.user.email,
            display_name: mode.user.display_name,
            role: mode.user.role,
            created_at: '',
          })
        }
      } catch {
        // 探测失败：按需要登录处理（下方会跳登录页）
      } finally {
        if (!cancelled) {
          setModeChecked(true)
          if (!useAuthStore.getState().isInitialized) setInitialized()
        }
      }
    }

    void init()
    return () => { cancelled = true }
    // isAuthenticated 变化时需要重新判断（如退出登录后）
  }, [isAuthenticated, isInitialized, setInitialized, setUser])

  // 初始化中，显示加载
  if (!isInitialized || !modeChecked) {
    return (
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
      }}>
        <Spin size="large" tip="加载中..." />
      </div>
    )
  }

  // 未登录，重定向到登录页
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}

export default AuthGuard
