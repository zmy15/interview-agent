import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, App as AntApp } from 'antd'
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

function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
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
