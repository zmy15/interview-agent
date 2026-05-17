import React, { useState } from 'react'
import { Button, Typography, Spin, App } from 'antd'
import { FileTextOutlined, CopyOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore } from '@/stores/chatStore'
import { useAppStore } from '@/stores/appStore'
import * as interviewApi from '@/api/interview'

const { Title, Text, Paragraph } = Typography

const ReportPage: React.FC = () => {
  const { messages, selectedMode } = useChatStore()
  const { apiKey } = useAppStore()
  const [report, setReport] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const { message } = App.useApp()
  const [generated, setGenerated] = useState(false)

  const handleGenerate = async () => {
    setLoading(true)
    try {
      const res = await interviewApi.generateReport(messages, selectedMode, apiKey)
      setReport(res.report)
      setGenerated(true)
      message.success('报告生成成功')
    } catch (err) {
      message.error((err as Error).message || '报告生成失败')
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = () => {
    navigator.clipboard.writeText(report).then(
      () => message.success('已复制到剪贴板'),
      () => message.error('复制失败'),
    )
  }

  if (!generated) {
    return (
      <div style={{ textAlign: 'center', paddingTop: '10%' }}>
        <FileTextOutlined style={{ fontSize: 48, color: '#bbb', marginBottom: 16 }} />
        <Title level={4}>面试报告</Title>
        {messages.length === 0 ? (
          <Paragraph type="secondary">
            暂无对话记录，请先完成面试对话后再生成报告
          </Paragraph>
        ) : (
          <>
            <Paragraph type="secondary">
              当前共 {messages.length} 条对话消息，点击下方按钮生成面试评价报告
            </Paragraph>
            <Button
              type="primary"
              size="large"
              onClick={handleGenerate}
              loading={loading}
            >
              生成报告
            </Button>
          </>
        )}
      </div>
    )
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Title level={4} style={{ margin: 0 }}>
          面试评价报告
        </Title>
        <Button icon={<CopyOutlined />} onClick={handleCopy}>
          复制报告
        </Button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin size="large" />
          <p style={{ marginTop: 16, color: '#888' }}>正在生成报告...</p>
        </div>
      ) : (
        <div
          style={{
            background: '#fff',
            padding: 24,
            borderRadius: 8,
            border: '1px solid #f0f0f0',
          }}
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{report}</ReactMarkdown>
        </div>
      )}

      <div style={{ marginTop: 16, textAlign: 'center' }}>
        <Button onClick={() => setGenerated(false)}>重新生成</Button>
      </div>
    </div>
  )
}

export default ReportPage
