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
  Modal,
  Select,
  Tag,
  Tooltip,
} from 'antd'
import {
  SendOutlined,
  StopOutlined,
  ClearOutlined,
  SettingOutlined,
  SearchOutlined,
  KeyOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined,
  PauseCircleOutlined,
} from '@ant-design/icons'
import { useChatStore } from '@/stores/chatStore'
import { useAppStore } from '@/stores/appStore'
import { useSSE } from '@/hooks/useSSE'
import ChatMessage from '@/components/ChatMessage'
import ModelSelector from '@/components/ModelSelector'
import PositionSelect from '@/components/PositionSelect'
import PromptEditor from '@/components/PromptEditor'
import { getInterviewPlan } from '@/api/interview'
import type { ChatMode, InterviewPlanResponse } from '@/types'

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
  const { highlightCode, toggleHighlightCode, apiKey, setApiKey, interviewDuration, setInterviewDuration } = useAppStore()
  const { sendMessage, abort } = useSSE()

  const [inputValue, setInputValue] = useState('')
  const [promptEditorOpen, setPromptEditorOpen] = useState(false)
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState(apiKey)
  const [interviewPlan, setInterviewPlan] = useState<InterviewPlanResponse | null>(null)
  const [practiceActive, setPracticeActive] = useState(false)
  const [questionIndex, setQuestionIndex] = useState(0)
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
    setPracticeActive(false)
    setQuestionIndex(0)
    setInterviewPlan(null)
    message.success('对话已清空')
  }

  // API Key 配置
  const handleApiKeySave = () => {
    setApiKey(apiKeyInput.trim())
    setApiKeyModalOpen(false)
    if (apiKeyInput.trim()) {
      message.success('API Key 已保存')
    } else {
      message.info('API Key 已清除，将使用服务端默认配置')
    }
  }

  // 获取面试计划
  const handleGetPlan = async () => {
    try {
      const plan = await getInterviewPlan({
        mode: selectedMode,
        duration_minutes: interviewDuration,
      })
      setInterviewPlan(plan)
      message.success(plan.description)
    } catch {
      message.error('获取面试计划失败')
    }
  }

  // 开始模拟练习
  const handleStartPractice = async () => {
    if (!interviewPlan) {
      await handleGetPlan()
    }
    setPracticeActive(true)
    setQuestionIndex(0)
    // 发送开始练习的系统消息
    const startMsg = `我准备好了，请开始面试。面试时长 ${interviewDuration} 分钟，预计 ${interviewPlan?.question_count || '若干'} 道题目。`
    await sendMessage(startMsg)
  }

  // 结束练习并跳转报告
  const handleEndPractice = () => {
    setPracticeActive(false)
    setQuestionIndex(0)
    setInterviewPlan(null)
    message.success('练习结束，可前往报告页面生成评价')
  }

  // 跟踪问题数量（检测 AI 消息中的问题标记）
  useEffect(() => {
    if (!practiceActive || !interviewPlan) return
    const assistantMsgs = messages.filter((m) => m.role === 'assistant')
    // 简单估算：每个 assistant 消息代表一个问题
    const count = Math.min(assistantMsgs.length, interviewPlan.question_count)
    setQuestionIndex(count)
    // 达到问题数量时自动提示
    if (count >= interviewPlan.question_count && assistantMsgs.length > 0) {
      message.info(`已完成 ${interviewPlan.question_count} 道题目，可以结束练习并生成报告`)
    }
  }, [messages, practiceActive, interviewPlan])

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
          onChange={(val) => {
            setMode(val as ChatMode)
            setPracticeActive(false)
            setInterviewPlan(null)
          }}
          options={[
            { value: 'interviewer', label: '🎯 你是面试官' },
            { value: 'candidate', label: '🧑 你是求职者' },
          ]}
        />
        <div style={{ width: 1, height: 24, background: '#d9d9d9' }} />
        <ModelSelector />
        <div style={{ width: 1, height: 24, background: '#d9d9d9' }} />
        <PositionSelect />

        {/* 你是求职者模式：面试时长选择器（AI 提问，你回答） */}
        {selectedMode === 'candidate' && (
          <>
            <div style={{ width: 1, height: 24, background: '#d9d9d9' }} />
            <Space size={4}>
              <ClockCircleOutlined style={{ color: '#1677ff' }} />
              <Select
                size="small"
                value={interviewDuration}
                onChange={(val) => {
                  setInterviewDuration(val)
                  setInterviewPlan(null)
                }}
                style={{ width: 100 }}
                options={[
                  { value: 15, label: '15 分钟' },
                  { value: 30, label: '30 分钟' },
                  { value: 45, label: '45 分钟' },
                  { value: 60, label: '60 分钟' },
                ]}
              />
              {interviewPlan && (
                <Tag color="blue">{interviewPlan.question_count} 题</Tag>
              )}
            </Space>
            <Tooltip title="根据时长推算问题数量">
              <Button
                size="small"
                type="link"
                onClick={handleGetPlan}
                style={{ padding: '0 4px', fontSize: 12 }}
              >
                推算
              </Button>
            </Tooltip>
          </>
        )}

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

        {/* API Key 配置按钮 */}
        <Tooltip title={apiKey ? 'DeepSeek API Key 已配置' : '配置 DeepSeek API Key'}>
          <Button
            size="small"
            icon={<KeyOutlined />}
            type={apiKey ? 'primary' : 'default'}
            ghost={!!apiKey}
            onClick={() => {
              setApiKeyInput(apiKey)
              setApiKeyModalOpen(true)
            }}
          >
            {apiKey ? '已配置' : 'API Key'}
          </Button>
        </Tooltip>

        <Button
          size="small"
          icon={<SettingOutlined />}
          onClick={() => setPromptEditorOpen(true)}
        >
          Prompt
        </Button>
        <Popconfirm
          title="确定清空所有对话记录？"
          onConfirm={handleClear}
          okText="确定"
          cancelText="取消"
        >
          <Button size="small" danger icon={<ClearOutlined />}>
            清空
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
            <div style={{ fontSize: 13, marginBottom: 24 }}>
              选择面试模式和岗位，开始 AI 模拟面试对话
            </div>
            {/* 你是求职者模式：开始练习按钮 */}
            {selectedMode === 'candidate' && !practiceActive && (
              <Button
                type="primary"
                size="large"
                icon={<PlayCircleOutlined />}
                onClick={handleStartPractice}
                disabled={!interviewPlan}
              >
                开始模拟练习
              </Button>
            )}
          </div>
        )}

        {/* 练习进度条（求职者模式） */}
        {practiceActive && interviewPlan && (
          <div
            style={{
              background: '#e6f4ff',
              borderRadius: 8,
              padding: '8px 16px',
              marginBottom: 12,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <Space>
              <PlayCircleOutlined style={{ color: '#1677ff' }} />
              <Text strong>
                模拟练习中 · 第 {questionIndex}/{interviewPlan.question_count} 题
              </Text>
              <Tag color="processing">{interviewDuration} 分钟</Tag>
            </Space>
            <Button
              size="small"
              danger
              icon={<PauseCircleOutlined />}
              onClick={handleEndPractice}
            >
              结束练习
            </Button>
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
              ? '你是面试官，输入你的提问... (Enter 发送, Shift+Enter 换行)'
              : '你是求职者，输入你的回答... (Enter 发送, Shift+Enter 换行)'
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

      {/* API Key 配置弹窗 */}
      <Modal
        title="配置 DeepSeek API Key"
        open={apiKeyModalOpen}
        onOk={handleApiKeySave}
        onCancel={() => setApiKeyModalOpen(false)}
        okText="保存"
        cancelText="取消"
        width={480}
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="secondary">
            输入你的 DeepSeek API Key，将优先使用此密钥进行对话。
            留空则使用服务端默认配置。
          </Text>
        </div>
        <Input.Password
          value={apiKeyInput}
          onChange={(e) => setApiKeyInput(e.target.value)}
          placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
          autoFocus
        />
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            密钥仅保存在本地浏览器中，不会上传到服务器。
            你可以从{' '}
            <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noopener noreferrer">
              DeepSeek 开放平台
            </a>{' '}
            获取 API Key。
          </Text>
        </div>
      </Modal>
    </div>
  )
}

export default ChatPage
