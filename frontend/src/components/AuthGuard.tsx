/**
 * 路由守卫 — 未登录时重定向到登录页
 */

import React, { useEffect } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuthStore } from '@/stores/authStore'

interface AuthGuardProps {
  children: React.ReactNode
}

const AuthGuard: React.FC<AuthGuardProps> = ({ children }) => {
  const { isAuthenticated, isInitialized, setInitialized } = useAuthStore()
  const location = useLocation()

  useEffect(() => {
    // 标记初始化完成（从 localStorage 恢复状态后）
    const timer = setTimeout(() => {
      if (!isInitialized) {
        setInitialized()
      }
    }, 100)
    return () => clearTimeout(timer)
  }, [isInitialized, setInitialized])

  // 初始化中，显示加载
  if (!isInitialized) {
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
