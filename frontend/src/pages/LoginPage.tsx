/**
 * 登录/注册页面
 */

import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Form,
  Input,
  Button,
  Card,
  Typography,
  App,
  Tabs,
  Space,
} from 'antd'
import { MailOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { useAuthStore } from '@/stores/authStore'
import { authApi } from '@/api/auth'
import type { LoginRequest, RegisterRequest } from '@/api/auth'

const { Title, Text } = Typography

const LoginPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login')
  const [loading, setLoading] = useState(false)
  const { login: authLogin } = useAuthStore()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const location = useLocation()

  // 登录后重定向到来源页或首页
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/'

  const handleLogin = async (values: LoginRequest) => {
    setLoading(true)
    try {
      const res = await authApi.login(values)
      authLogin(res.access_token, res.refresh_token, {
        id: res.user.id,
        email: res.user.email,
        display_name: res.user.display_name,
        role: res.user.role,
        avatar_url: undefined,
        created_at: '',
      })
      message.success('登录成功')
      navigate(from, { replace: true })
    } catch (err) {
      message.error((err as Error).message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  const handleRegister = async (values: RegisterRequest) => {
    setLoading(true)
    try {
      const res = await authApi.register({
        email: values.email,
        password: values.password,
        display_name: values.display_name || values.email.split('@')[0],
      })
      authLogin(res.access_token, res.refresh_token, {
        id: res.user.id,
        email: res.user.email,
        display_name: res.user.display_name,
        role: res.user.role,
        avatar_url: undefined,
        created_at: '',
      })
      message.success('注册成功！')
      navigate(from, { replace: true })
    } catch (err) {
      message.error((err as Error).message || '注册失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        padding: 20,
      }}
    >
      <Card
        style={{
          width: 420,
          maxWidth: '90vw',
          borderRadius: 16,
          boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
        }}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div style={{ textAlign: 'center', marginBottom: 8 }}>
            <Title level={2} style={{ marginBottom: 4 }}>
              🎯 Interview Agent
            </Title>
            <Text type="secondary">AI 模拟面试平台</Text>
          </div>

          <Tabs
            activeKey={activeTab}
            onChange={(key) => setActiveTab(key as 'login' | 'register')}
            centered
            items={[
              {
                key: 'login',
                label: '登录',
                children: (
                  <Form onFinish={handleLogin} layout="vertical" size="large">
                    <Form.Item
                      name="email"
                      rules={[
                        { required: true, message: '请输入邮箱' },
                        { type: 'email', message: '请输入有效的邮箱地址' },
                      ]}
                    >
                      <Input prefix={<MailOutlined />} placeholder="邮箱地址" />
                    </Form.Item>
                    <Form.Item
                      name="password"
                      rules={[{ required: true, message: '请输入密码' }]}
                    >
                      <Input.Password prefix={<LockOutlined />} placeholder="密码" />
                    </Form.Item>
                    <Form.Item>
                      <Button type="primary" htmlType="submit" loading={loading} block>
                        登录
                      </Button>
                    </Form.Item>
                  </Form>
                ),
              },
              {
                key: 'register',
                label: '注册',
                children: (
                  <Form onFinish={handleRegister} layout="vertical" size="large">
                    <Form.Item
                      name="display_name"
                      rules={[{ required: false, message: '请输入昵称' }]}
                    >
                      <Input prefix={<UserOutlined />} placeholder="昵称（选填）" />
                    </Form.Item>
                    <Form.Item
                      name="email"
                      rules={[
                        { required: true, message: '请输入邮箱' },
                        { type: 'email', message: '请输入有效的邮箱地址' },
                      ]}
                    >
                      <Input prefix={<MailOutlined />} placeholder="邮箱地址" />
                    </Form.Item>
                    <Form.Item
                      name="password"
                      rules={[
                        { required: true, message: '请输入密码' },
                        { min: 6, message: '密码至少 6 位' },
                      ]}
                    >
                      <Input.Password prefix={<LockOutlined />} placeholder="密码（至少6位）" />
                    </Form.Item>
                    <Form.Item>
                      <Button type="primary" htmlType="submit" loading={loading} block>
                        注册
                      </Button>
                    </Form.Item>
                  </Form>
                ),
              },
            ]}
          />
        </Space>
      </Card>
    </div>
  )
}

export default LoginPage
