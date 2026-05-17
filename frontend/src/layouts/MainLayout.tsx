import React from 'react'
import { Layout, Menu } from 'antd'
import {
  MessageOutlined,
  ProfileOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'

const { Sider, Content, Header } = Layout

const menuItems = [
  { key: '/chat', icon: <MessageOutlined />, label: 'AI 对话' },
  { key: '/positions', icon: <ProfileOutlined />, label: '岗位管理' },
  { key: '/knowledge', icon: <DatabaseOutlined />, label: '知识库' },
  { key: '/report', icon: <FileTextOutlined />, label: '面试报告' },
  { key: '/upload', icon: <UploadOutlined />, label: '文件上传' },
]

const MainLayout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()

  const selectedKey = menuItems.find((item) =>
    location.pathname.startsWith(item.key),
  )?.key || '/chat'

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        breakpoint="lg"
        collapsedWidth="64"
        theme="light"
        style={{ borderRight: '1px solid #f0f0f0' }}
      >
        <div
          style={{
            height: 48,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 700,
            fontSize: 16,
            borderBottom: '1px solid #f0f0f0',
          }}
        >
          🎯 面试 Agent
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
          style={{ borderRight: 0, marginTop: 8 }}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            borderBottom: '1px solid #f0f0f0',
            display: 'flex',
            alignItems: 'center',
            height: 48,
          }}
        >
          <span style={{ fontSize: 14, color: '#888' }}>
            DeepSeek 驱动 · RAG 增强面试助手
          </span>
        </Header>
        <Content
          style={{
            padding: 24,
            background: '#fafafa',
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
