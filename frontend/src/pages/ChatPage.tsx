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
  Progress,
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
import type { ChatMode, InterviewPlanResponse, CandidateLevel, InterviewRound, AnswerLength } from '@/types'
import { CodeOutlined } from '@ant-design/icons'

const { TextArea } = Input
const { Text } = Typography

/** 中文语速：约250字/分钟（保留用于兼容旧逻辑，主要使用 wall-clock 时间） */
const CHARS_PER_MINUTE = 250

/** 面试阶段标签 */
const PHASE_LABELS: Record<string, { label: string; color: string }> = {
  intro: { label: '自我介绍', color: 'blue' },
  tech_qa: { label: '技术问答', color: 'processing' },
  coding: { label: '编程题', color: 'orange' },
  reverse: { label: '反问环节', color: 'purple' },
}

const ChatPage: React.FC = () => {
  const {
    messages,
    isStreaming,
    currentReasoning,
    currentContent,
    selectedMode,
    thinkingEnabled,
    useSearch,
    codingEnabled,
    candidateLevel,
    interviewRound,
    answerLength,
    practiceActive,
    practiceStartTime,
    interviewPlan,
    qaRecords,
    totalUserChars,
    clearChat,
    clearAllChats,
    setMode,
    setUseSearch,
    setCodingEnabled,
    setCandidateLevel,
    setInterviewRound,
    setAnswerLength,
    setPracticeActive,
    setInterviewPlan,
    resetPractice,
    addQARecord,
  } = useChatStore()

  const { message } = App.useApp()
  const { highlightCode, toggleHighlightCode, apiKey, setApiKey, interviewDuration, setInterviewDuration } = useAppStore()
  const { sendMessage, abort } = useSSE()

  const [inputValue, setInputValue] = useState('')
  const [promptEditorOpen, setPromptEditorOpen] = useState(false)
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false)
  const [apiKeyInput, setApiKeyInput] = useState(apiKey)

  // 用于追踪上一轮 AI 的提问内容（配对 QA 记录）
  const lastAIQuestionRef = useRef<string>('')

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

    // 记录 QA：如果上一轮 AI 有提问，则将当前用户回答与之配对
    if (selectedMode === 'candidate' && practiceActive && lastAIQuestionRef.current) {
      addQARecord({
        question: lastAIQuestionRef.current,
        answer: text,
        answer_chars: text.length,
      })
    }
    lastAIQuestionRef.current = ''

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
    resetPractice()
    lastAIQuestionRef.current = ''
    message.success(`已清空「${selectedMode === 'interviewer' ? '面试官' : '求职者'}」对话`)
  }

  const handleClearAll = () => {
    clearAllChats()
    resetPractice()
    lastAIQuestionRef.current = ''
    message.success('已清空全部对话记录')
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
        answer_length: answerLength,
        candidate_level: candidateLevel || undefined,
        interview_round: interviewRound || undefined,
        coding_enabled: codingEnabled,
      })
      setInterviewPlan(plan)
      message.success(plan.description)
    } catch {
      message.error('获取面试计划失败')
    }
  }

  // 开始模拟练习
  const handleStartPractice = async () => {
    let plan = interviewPlan
    if (!plan) {
      try {
        plan = await getInterviewPlan({
          mode: selectedMode,
          duration_minutes: interviewDuration,
          answer_length: answerLength,
          candidate_level: candidateLevel || undefined,
          interview_round: interviewRound || undefined,
          coding_enabled: codingEnabled,
        })
        setInterviewPlan(plan)
      } catch {
        message.error('获取面试计划失败')
        return
      }
    }
    setPracticeActive(true)
    lastAIQuestionRef.current = ''
    const startMsg = `我准备好了，请开始面试。`
    await sendMessage(startMsg)
  }

  // 结束练习并跳转报告
  const handleEndPractice = () => {
    resetPractice()
    lastAIQuestionRef.current = ''
    message.success('练习结束，可前往报告页面生成评价')
  }

  // 当 AI 完成消息时，如果处于练习模式，记录为潜在提问
  useEffect(() => {
    if (!isStreaming && practiceActive && selectedMode === 'candidate') {
      // 获取最新的 assistant 消息作为问题
      const assistantMsgs = messages.filter((m) => m.role === 'assistant')
      if (assistantMsgs.length > 0) {
        const lastMsg = assistantMsgs[assistantMsgs.length - 1]
        // 只记录包含问号或明显是提问的消息
        if (lastMsg.content.includes('？') || lastMsg.content.includes('?')) {
          lastAIQuestionRef.current = lastMsg.content.slice(0, 500) // 截取前500字
        }
      }
    }
  }, [isStreaming, practiceActive, selectedMode, messages])

  // 推算已用时间和剩余时间 — 使用 wall-clock 时间（精确计时）
  const [elapsedSec, setElapsedSec] = useState(0)

  // 每秒更新一次已用时间
  useEffect(() => {
    if (!practiceActive || !practiceStartTime) {
      setElapsedSec(0)
      return
    }
    const timer = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - practiceStartTime) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [practiceActive, practiceStartTime])

  const elapsedMin = Math.floor(elapsedSec / 60)
  const remainingMin = Math.max(0, interviewDuration - Math.ceil(elapsedSec / 60))

  // 根据时间和已答题数推断当前阶段
  const estimatedPhase = (): string => {
    if (!interviewPlan) return 'intro'
    if (elapsedMin <= 2) return 'intro'

    const plan = interviewPlan
    const introEnd = plan.breakdown?.['自我介绍'] || 3
    const codingMin = plan.coding_reserved_min || 0
    const reverseMin = plan.breakdown?.['反问环节'] || 3
    const techQaMin = (plan.breakdown?.['技术问答'] || 0)

    // 反问检测：AI 消息中包含反问关键词
    const lastAssistantMsgs = messages.filter(m => m.role === 'assistant').slice(-3)
    const hasReverseSignal = lastAssistantMsgs.some(m =>
      m.content.includes('有什么问题想问') ||
      m.content.includes('还有什么问题') ||
      m.content.includes('反问')
    )

    if (hasReverseSignal || remainingMin <= reverseMin + 1) return 'reverse'
    if (codingEnabled && codingMin > 0 && elapsedMin >= introEnd + techQaMin * 0.6) return 'coding'
    if (elapsedMin >= introEnd) return 'tech_qa'
    return 'intro'
  }

  const currentPhase = estimatedPhase()
  const phaseInfo = PHASE_LABELS[currentPhase] || { label: '未知', color: 'default' }

  // 进度百分比
  const progressPercent = interviewDuration > 0 ? Math.min(100, Math.round((elapsedSec / 60) / interviewDuration * 100)) : 0

  // 动态调整面试计划（每 5 题或时间过半时重新计算）
  const [lastPlanRefresh, setLastPlanRefresh] = useState(0)
  useEffect(() => {
    if (!practiceActive || !interviewPlan) return

    const shouldRefresh =
      (qaRecords.length > 0 && qaRecords.length % 5 === 0 && qaRecords.length > lastPlanRefresh) ||
      (elapsedMin > 0 && elapsedMin % 8 === 0 && elapsedMin > lastPlanRefresh)

    if (shouldRefresh) {
      setLastPlanRefresh(qaRecords.length > lastPlanRefresh ? qaRecords.length : elapsedMin)
      getInterviewPlan({
        mode: selectedMode,
        duration_minutes: interviewDuration,
        answer_length: answerLength,
        candidate_level: candidateLevel || undefined,
        interview_round: interviewRound || undefined,
        coding_enabled: codingEnabled,
        elapsed_minutes: elapsedMin,
        answered_questions: qaRecords.length,
      }).then((plan) => {
        setInterviewPlan(plan)
      }).catch(() => {
        // 静默失败，不影响面试流程
      })
    }
  }, [qaRecords.length, elapsedMin, practiceActive])

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

        {/* 你是求职者模式：候选人级别 + 面试轮次 + 编程题 + 时长 */}
        {selectedMode === 'candidate' && (
          <>
            <div style={{ width: 1, height: 24, background: '#d9d9d9' }} />            <Space size={4}>
              <Text type="secondary" style={{ fontSize: 12 }}>👤</Text>
              <Select
                size="small"
                value={candidateLevel || undefined}
                onChange={(val) => {
                  setCandidateLevel(val || null)
                  setInterviewPlan(null)
                }}
                placeholder="经验级别"
                allowClear
                style={{ width: 90 }}
                options={[
                  { value: 'intern', label: '🎓 实习' },
                  { value: 'new_grad', label: '🎯 校招' },
                  { value: 'experienced', label: '💼 社招' },
                ]}
              />
            </Space>
            <Space size={4}>
              <Text type="secondary" style={{ fontSize: 12 }}>🔄</Text>
              <Select
                size="small"
                value={interviewRound || undefined}
                onChange={(val) => {
                  setInterviewRound(val || null)
                  setInterviewPlan(null)
                }}
                placeholder="面试轮次"
                allowClear
                style={{ width: 90 }}
                options={[
                  { value: 'first', label: '📋 一面' },
                  { value: 'second', label: '🔍 二面' },
                  { value: 'hr', label: '🤝 HR面' },
                ]}
              />
            </Space>            <Tooltip title="让AI面试官从LeetCode Hot100/面试经典150中出编程题，难度根据岗位和你的回答表现自动调整">
              <Space size={4}>
                <Switch
                  size="small"
                  checked={codingEnabled}
                  onChange={setCodingEnabled}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  <CodeOutlined /> 编程题
                </Text>
              </Space>
            </Tooltip>
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
            <Select
              size="small"
              value={answerLength}
              onChange={(val) => {
                setAnswerLength(val)
                setInterviewPlan(null)
              }}
              style={{ width: 90 }}
              options={[
                { value: 'short', label: '📝 简短' },
                { value: 'medium', label: '📄 适中' },
                { value: 'long', label: '📚 详细' },
              ]}
            />
            <Tooltip title="根据时长、级别、轮次和回答风格推算问题数量">
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
          title="确定清空当前模式对话记录？"
          onConfirm={handleClear}
          okText="清空当前"
          cancelText="取消"
        >
          <Button size="small" danger icon={<ClearOutlined />}>
            清空
          </Button>
        </Popconfirm>
        <Popconfirm
          title="确定清空全部（面试官+求职者）对话记录？"
          onConfirm={handleClearAll}
          okText="全部清空"
          cancelText="取消"
        >
          <Button size="small" danger type="text" style={{ fontSize: 12 }}>
            全部
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
              >
                开始模拟练习
              </Button>
            )}
          </div>
        )}

        {/* 练习进度条（求职者模式，跨页面持久化） */}
        {practiceActive && (
          <div
            style={{
              background: '#e6f4ff',
              borderRadius: 8,
              padding: '8px 16px',
              marginBottom: 12,
              display: 'flex',
              flexDirection: 'column',
              gap: 6,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <Space size={8} wrap>
                <PlayCircleOutlined style={{ color: '#1677ff' }} />
                <Text strong>模拟练习中</Text>
                <Tag color="processing">{interviewDuration} 分钟</Tag>

                {/* 当前阶段标签 */}
                <Tag color={phaseInfo.color}>{phaseInfo.label}</Tag>

                {/* 已用时间（wall-clock） */}
                <Text type="secondary" style={{ fontSize: 12 }}>
                  已过 {elapsedMin} 分 {elapsedSec % 60} 秒
                </Text>

                {/* 剩余时间 */}
                <Text type="secondary" style={{ fontSize: 12 }}>
                  · 剩余约 {remainingMin} 分钟
                </Text>

                {/* 已答题数 / 计划题数 */}
                {interviewPlan && (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    · 已答 {qaRecords.length}/{interviewPlan.question_count} 题
                    {interviewPlan.remaining_questions < interviewPlan.question_count &&
                      <span style={{ color: '#fa8c16' }}>
                        {' '}(剩余约{interviewPlan.remaining_questions}题)
                      </span>
                    }
                  </Text>
                )}

                {/* 编程题时间提示 */}
                {codingEnabled && interviewPlan && interviewPlan.coding_reserved_min > 0 && (
                  <Tag color="orange" style={{ fontSize: 11 }}>
                    编程题 ~{interviewPlan.coding_reserved_min}min
                  </Tag>
                )}
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

            {/* 时间进度条 */}
            <Progress
              percent={progressPercent}
              size="small"
              status={remainingMin <= 5 ? 'exception' : 'active'}
              showInfo={false}
              strokeColor={remainingMin <= 5 ? '#ff4d4f' : remainingMin <= 10 ? '#faad14' : '#1677ff'}
            />

            {/* 动态提示 */}
            {remainingMin <= 5 && currentPhase !== 'reverse' && (
              <Text type="danger" style={{ fontSize: 11 }}>
                ⚠️ 时间即将用完，建议面试官尽快收尾进入反问环节
              </Text>
            )}
            {currentPhase === 'reverse' && remainingMin > 5 && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                💡 已进入反问环节，可向面试官提问团队、技术栈、发展空间等
              </Text>
            )}
            {currentPhase === 'coding' && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                💻 编程题进行中，请认真思考后作答
              </Text>
            )}
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
