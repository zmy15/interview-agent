import React from 'react'
import { Layout, Menu, Button, Space, Dropdown, theme } from 'antd'
import {
  MessageOutlined,
  ProfileOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  UploadOutlined,
  UserOutlined,
  LogoutOutlined,
  CodeOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useAppStore } from '@/stores/appStore'
import WindowSettings from '@/components/WindowSettings'

const { Sider, Content, Header } = Layout

const menuItems = [
  { key: '/chat', icon: <MessageOutlined />, label: 'AI 对话' },
  { key: '/positions', icon: <ProfileOutlined />, label: '岗位管理' },
  { key: '/knowledge', icon: <DatabaseOutlined />, label: '知识库' },
  { key: '/question-bank', icon: <CodeOutlined />, label: '题库' },
  { key: '/report', icon: <FileTextOutlined />, label: '面试报告' },
  { key: '/upload', icon: <UploadOutlined />, label: '文件上传' },
]

const MainLayout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, logout } = useAuthStore()
  // 系统音频监听状态由 ChatPage 写入，这里只负责展示
  const systemAudioListening = useAppStore((s) => s.systemAudioListening)
  const systemAudioSttConnected = useAppStore((s) => s.systemAudioSttConnected)
  const systemAudioError = useAppStore((s) => s.systemAudioError)
  // 取当前主题 token，使写死的底色/边框跟随用户选择
  const { token } = theme.useToken()

  const selectedKey = menuItems.find((item) =>
    location.pathname.startsWith(item.key),
  )?.key || '/chat'

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const userMenuItems = [
    {
      key: 'email',
      label: user?.email || '',
      disabled: true,
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: '退出登录',
      danger: true,
      onClick: handleLogout,
    },
  ]

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        breakpoint="lg"
        collapsedWidth="64"
        theme="light"
        style={{
          borderRight: `1px solid ${token.colorBorderSecondary}`,
          background: token.colorBgContainer,
        }}
      >
        <div
          style={{
            height: 48,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: 16,
            color: token.colorText,
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          🎯 面试 Agent
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0, marginTop: 8, background: 'transparent' }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            padding: '0 24px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            height: 48,
          }}
        >
          <span style={{ fontSize: 14, color: token.colorTextSecondary }}>
            DeepSeek 驱动 · RAG 增强面试助手
          </span>
          <Space size={4}>
            {/* 设置（配色 / 窗口 / 系统音频监听）；窗口项在浏览器中自动隐藏 */}
            <WindowSettings
              systemAudioListening={systemAudioListening}
              systemAudioSttConnected={systemAudioSttConnected}
              systemAudioError={systemAudioError}
            />
            <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
              <Button type="text" icon={<UserOutlined />}>
                {user?.display_name || user?.email || '用户'}
              </Button>
            </Dropdown>
          </Space>
        </Header>
        <Content
          style={{
            padding: 24,
            // 跟随用户选择的背景色（由 ConfigProvider 注入）
            background: token.colorBgLayout,
            color: token.colorText,
            overflow: 'auto',
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}

export default MainLayout
