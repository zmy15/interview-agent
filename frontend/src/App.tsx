import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, App as AntApp, theme as antdTheme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import MainLayout from '@/layouts/MainLayout'
import ChatPage from '@/pages/ChatPage'
import PositionPage from '@/pages/PositionPage'
import KnowledgePage from '@/pages/KnowledgePage'
import ReportPage from '@/pages/ReportPage'
import UploadPage from '@/pages/UploadPage'
import LoginPage from '@/pages/LoginPage'
import QuestionBankPage from '@/pages/QuestionBankPage'
import AuthGuard from '@/components/AuthGuard'
import { useThemeStore } from '@/stores/themeStore'
import { deriveTokens, isDark } from '@/utils/themeColor'

function App() {
  const background = useThemeStore((s) => s.background)
  const textColor = useThemeStore((s) => s.textColor)

  const dark = isDark(background)
  const tokens = deriveTokens(background, textColor)

  // html/body 默认是白色，滚动到边缘或 overscroll 时会露出白边，
  // 因此同步设置到 document 上
  useEffect(() => {
    document.documentElement.style.background = background
    document.body.style.background = background
    document.body.style.color = textColor
  }, [background, textColor])

  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        // 深色背景下启用 antd 的暗色算法，否则组件内部仍按亮色计算，
        // 会出现白底组件配浅色文字的问题
        algorithm: dark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
          // 背景与文字（用户可调）
          colorBgLayout: tokens.colorBgLayout,
          colorBgContainer: tokens.colorBgContainer,
          colorBgElevated: tokens.colorBgElevated,
          colorText: tokens.colorText,
          colorTextSecondary: tokens.colorTextSecondary,
          colorTextTertiary: tokens.colorTextTertiary,
          colorBorder: tokens.colorBorder,
          colorBorderSecondary: tokens.colorBorderSecondary,
          colorFillSecondary: tokens.colorFillSecondary,
        },
        components: {
          // 布局组件默认带自己的底色，必须显式跟随，否则侧边栏/顶栏不变色
          Layout: {
            bodyBg: tokens.colorBgLayout,
            headerBg: tokens.colorBgContainer,
            siderBg: tokens.colorBgContainer,
          },
          Menu: {
            itemBg: 'transparent',
            subMenuItemBg: 'transparent',
          },
        },
      }}
    >
      <AntApp>
        <BrowserRouter>
          <Routes>
            {/* 公开路由：无需登录 */}
            <Route path="/login" element={<LoginPage />} />

            {/* 受保护路由：需要登录 */}
            <Route
              element={
                <AuthGuard>
                  <MainLayout />
                </AuthGuard>
              }
            >
              <Route path="/" element={<Navigate to="/chat" replace />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/positions" element={<PositionPage />} />
              <Route path="/knowledge" element={<KnowledgePage />} />
              <Route path="/report" element={<ReportPage />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/question-bank" element={<QuestionBankPage />} />
            </Route>

            {/* 未匹配路由重定向 */}
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </BrowserRouter>
      </AntApp>
    </ConfigProvider>
  )
}

export default App
