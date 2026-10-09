import React from 'react'
import { Layout, Menu, Button, Space, Dropdown, Tooltip, theme } from 'antd'
import {
  MessageOutlined,
  ProfileOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  UploadOutlined,
  UserOutlined,
  LogoutOutlined,
  CodeOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  CloseOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useAppStore, type SiderMode } from '@/stores/appStore'
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
  // 侧边栏显示模式（持久化在 appStore，刷新后保持）
  const siderMode = useAppStore((s) => s.siderMode)
  const toggleSiderCollapsed = useAppStore((s) => s.toggleSiderCollapsed)
  const toggleSiderHidden = useAppStore((s) => s.toggleSiderHidden)
  // 取当前主题 token，使写死的底色/边框跟随用户选择
  const { token } = theme.useToken()

  // 兜底：localStorage 里若存了非法值（例如手改过或旧版本遗留），
  // 一律按 expanded 处理，避免 Sider 收到未知值后渲染异常
  const mode: SiderMode =
    siderMode === 'collapsed' || siderMode === 'hidden' ? siderMode : 'expanded'
  const hidden = mode === 'hidden'

  const selectedKey = menuItems.find((item) =>
    location.pathname.startsWith(item.key),
  )?.key || '/chat'

  // Ctrl/Cmd + B：通用的「收起侧边栏」快捷键
  React.useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault()
        toggleSiderCollapsed()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [toggleSiderCollapsed])

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
      {/* 隐藏模式直接不渲染 Sider：用 collapsedWidth=0 会留下零宽占位，
          且 antd 的零宽触发器会在左侧留下一个悬浮条 */}
      {!hidden && (
        <Sider
          breakpoint="lg"
          collapsedWidth="64"
          collapsed={mode === 'collapsed'}
          collapsible
          trigger={null}
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
              whiteSpace: 'nowrap',
              overflow: 'hidden',
            }}
          >
            {/* 折叠时只留图标，避免文字被挤成换行 */}
            {mode === 'collapsed' ? '🎯' : '🎯 面试 Agent'}
          </div>
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
            style={{ borderRight: 0, marginTop: 8, background: 'transparent' }}
          />
        </Sider>
      )}
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            padding: '0 16px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            height: 48,
          }}
        >
          <Space size={8}>
            {/* 侧边栏开关：隐藏后这里是唯一的入口，所以必须常驻 Header */}
            <Tooltip
              title={
                hidden
                  ? '显示侧边栏（Ctrl+B）'
                  : mode === 'collapsed'
                    ? '展开侧边栏（Ctrl+B）'
                    : '收起侧边栏（Ctrl+B）'
              }
            >
              <Button
                type="text"
                aria-label={hidden ? '显示侧边栏' : '收起侧边栏'}
                icon={hidden ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={toggleSiderCollapsed}
              />
            </Tooltip>
            {/* 完全隐藏：彻底腾出横向空间（做题/演示时有用）。
                用不同的图标与第一个按钮区分，避免两个「折叠」图标混淆 */}
            {!hidden && (
              <Tooltip title="完全隐藏侧边栏（腾出整屏横向空间）">
                <Button
                  type="text"
                  aria-label="完全隐藏侧边栏"
                  icon={<CloseOutlined />}
                  onClick={toggleSiderHidden}
                />
              </Tooltip>
            )}
            <span style={{ fontSize: 14, color: token.colorTextSecondary }}>
              DeepSeek 驱动 · RAG 增强面试助手
            </span>
          </Space>
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
