import React, { useRef, useEffect, useState, useCallback } from 'react'
import {
  Space,
  Switch,
  Button,
  Input,
  Popconfirm,
  Segmented,
  Typography,
  App,
} from 'antd'
import {
  SendOutlined,
  StopOutlined,
  ClearOutlined,
  SettingOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { useChatStore } from '@/stores/chatStore'
import { useAppStore } from '@/stores/appStore'
import { useSSE } from '@/hooks/useSSE'
import ChatMessage from '@/components/ChatMessage'
import ModelSelector from '@/components/ModelSelector'
import PositionSelect from '@/components/PositionSelect'
import PromptEditor from '@/components/PromptEditor'
import type { ChatMode } from '@/types'

const { TextArea } = Input
const { Text } = Typography

const ChatPage: React.FC = () => {
  const {
    messages,
    isStreaming,
    currentReasoning,
    currentContent,
    selectedMode,
    thinkingEnabled,
    useSearch,
    clearChat,
    setMode,
    setUseSearch,
  } = useChatStore()

  const { message } = App.useApp()
  const { highlightCode, toggleHighlightCode } = useAppStore()
  const { sendMessage, abort } = useSSE()

  const [inputValue, setInputValue] = useState('')
  const [promptEditorOpen, setPromptEditorOpen] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  // 自动滚动到底部
  useEffect(() => {
    if (autoScroll) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, currentContent, currentReasoning, autoScroll])

  // 检测用户手动上滚
  const handleScroll = useCallback(() => {
    if (!chatContainerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 100)
  }, [])

  const handleSend = async () => {
    const text = inputValue.trim()
    if (!text || isStreaming) return
    setInputValue('')
    setAutoScroll(true)
    try {
      await sendMessage(text)
    } catch {
      message.error('发送失败')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleClear = () => {
    clearChat()
    message.success('对话已清空')
  }

  // 构建流式消息（用于显示正在生成的内容）
  const streamingMessage =
    isStreaming && (currentReasoning || currentContent)
      ? {
          role: 'assistant' as const,
          content: currentContent,
          reasoning: currentReasoning || undefined,
        }
      : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 140px)' }}>
      {/* 顶部工具栏 */}
      <div
        style={{
          padding: '8px 0',
          borderBottom: '1px solid #f0f0f0',
          marginBottom: 12,
          display: 'flex',
          flexWrap: 'wrap',
          gap: 8,
          alignItems: 'center',
        }}
      >
        <Segmented
          value={selectedMode}
          onChange={(val) => setMode(val as ChatMode)}
          options={[
            { value: 'interviewer', label: '🤖 AI 面试官' },
            { value: 'candidate', label: '🧑 我是求职者' },
          ]}
        />
        <div style={{ width: 1, height: 24, background: '#d9d9d9' }} />
        <ModelSelector />
        <div style={{ width: 1, height: 24, background: '#d9d9d9' }} />
        <PositionSelect />
        <Space size={4}>
          <Switch
            size="small"
            checked={useSearch}
            onChange={setUseSearch}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            <SearchOutlined /> 联网搜索
          </Text>
        </Space>
        <Space size={4}>
          <Switch
            size="small"
            checked={highlightCode}
            onChange={toggleHighlightCode}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            代码高亮
          </Text>
        </Space>
        <div style={{ flex: 1 }} />
        <Button
          size="small"
          icon={<SettingOutlined />}
          onClick={() => setPromptEditorOpen(true)}
        >
          Prompt 设置
        </Button>
        <Popconfirm
          title="确定清空所有对话记录？"
          onConfirm={handleClear}
          okText="确定"
          cancelText="取消"
        >
          <Button size="small" danger icon={<ClearOutlined />}>
            清空对话
          </Button>
        </Popconfirm>
      </div>

      {/* 消息列表 */}
      <div
        ref={chatContainerRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '0 4px',
        }}
      >
        {messages.length === 0 && !streamingMessage && (
          <div
            style={{
              textAlign: 'center',
              paddingTop: '15%',
              color: '#bbb',
            }}
          >
            <div style={{ fontSize: 48, marginBottom: 16 }}>🎯</div>
            <div style={{ fontSize: 18, marginBottom: 8 }}>欢迎使用面试 Agent</div>
            <div style={{ fontSize: 13 }}>
              选择面试模式和岗位，开始 AI 模拟面试对话
            </div>
          </div>
        )}

        {messages.map((msg, idx) => (
          <ChatMessage key={idx} message={msg} highlightCode={highlightCode} />
        ))}

        {streamingMessage && (
          <ChatMessage
            message={streamingMessage}
            highlightCode={highlightCode}
            isStreaming
          />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 底部输入区 */}
      <div
        style={{
          padding: '12px 0 0',
          borderTop: '1px solid #f0f0f0',
          display: 'flex',
          gap: 8,
          alignItems: 'flex-end',
        }}
      >
        <TextArea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            selectedMode === 'interviewer'
              ? '输入你的回答... (Enter 发送, Shift+Enter 换行)'
              : '描述你的求职意向... (Enter 发送, Shift+Enter 换行)'
          }
          autoSize={{ minRows: 1, maxRows: 5 }}
          disabled={isStreaming}
          style={{ flex: 1 }}
        />
        {isStreaming ? (
          <Button
            danger
            icon={<StopOutlined />}
            onClick={abort}
            style={{ height: 40 }}
          >
            停止
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!inputValue.trim()}
            style={{ height: 40 }}
          >
            发送
          </Button>
        )}
      </div>

      {/* Prompt 编辑器弹窗 */}
      <PromptEditor
        open={promptEditorOpen}
        onClose={() => setPromptEditorOpen(false)}
      />
    </div>
  )
}

export default ChatPage
