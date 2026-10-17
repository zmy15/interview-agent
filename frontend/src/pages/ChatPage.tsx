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
  theme,
  Divider,
  Dropdown,
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
  CameraOutlined,
  LoadingOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
  UserOutlined,
  SyncOutlined,
  CodeOutlined,
  BookOutlined,
  MoreOutlined,
} from '@ant-design/icons'
import { useChatStore } from '@/stores/chatStore'
import { useAppStore } from '@/stores/appStore'
import { useSSE } from '@/hooks/useSSE'
import { useModels } from '@/hooks/useModels'
import { useApiKeyStatus } from '@/hooks/useApiKeyStatus'
import { settingsApi } from '@/api/settings'
import ChatMessage from '@/components/ChatMessage'
import ModelSelector from '@/components/ModelSelector'
import PositionSelect from '@/components/PositionSelect'
import PromptEditor from '@/components/PromptEditor'
import { getInterviewPlan } from '@/api/interview'
import type { ChatMode, InterviewPlanResponse, CandidateLevel, InterviewRound, AnswerLength } from '@/types'
import { questionBankApi, type QuestionItem } from '@/api/questionBank'
import VoiceInputPanel from '@/components/VoiceInputPanel'
import { useVoiceAvailability } from '@/hooks/useVoiceAvailability'
import { useSystemAudioListener } from '@/hooks/useSystemAudioListener'
import { screenshotApi } from '@/api/screenshot'
import {
  isDesktopWindow,
  getWindowState,
  setCaptureExclude,
  registerScreenshotHotkey,
  unregisterScreenshotHotkey,
  setHotkeyHandler,
} from '@/api/windowControl'

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

const DIFFICULTY_COLORS: Record<string, string> = { easy: 'green', medium: 'orange', hard: 'red' }
const DIFFICULTY_LABELS: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }

const ChatPage: React.FC = () => {
  const {
    messages,
    isStreaming,
    currentReasoning,
    currentContent,
    selectedMode,
    selectedModel,
    thinkingEnabled,
    reasoningEffort,
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
    questionBankIds,
    questionBankMode,
    setQuestionBankIds,
    setQuestionBankMode,
    addMessage,
  } = useChatStore()

  // modal 用于下拉菜单里的清空确认（Dropdown 菜单项不能再套 Popconfirm）
  const { message, modal } = App.useApp()
  const { token } = theme.useToken()
  const {
    highlightCode,
    toggleHighlightCode,
    apiKeyHint,
    setApiKeyHint,
    interviewDuration,
    setInterviewDuration,
    setSystemAudioStatus,
    focusMode,
    toggleFocusMode,
  } = useAppStore()
  const { sendMessage, abort } = useSSE()
  const { sttAvailable, ttsAvailable } = useVoiceAvailability()
  // 启动时从服务端拉取 API Key 状态（顺便迁移旧版遗留在 localStorage 的明文密钥）。
  // 必须排在 useModels 之前：模型列表是按 Key 所属账号返回的，
  // apiKeyHint 变化会触发 useModels 重新拉取。
  useApiKeyStatus()
  // 模型列表来自后端调用的官方 /models 接口，用于判断选中模型能否看图
  const { models } = useModels()

  const [inputValue, setInputValue] = useState('')
  const [promptEditorOpen, setPromptEditorOpen] = useState(false)
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false)
  // 输入框里用户**新键入**的密钥。服务端只回传掩码、回不到明文，
  // 因此打开弹窗时不预填内容，只在弹窗上方展示当前掩码。
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [apiKeySaving, setApiKeySaving] = useState(false)

  // 截图答题：截图期间禁用按钮，并显示已用秒数
  const [capturing, setCapturing] = useState(false)
  const [captureElapsed, setCaptureElapsed] = useState(0)

  // F8 快捷键要用「最新」的 handleScreenshot，但全局监听只在挂载时绑定一次。
  // handleScreenshot 每次渲染都会重建，直接绑定会拿到过期的 capturing/isStreaming
  // 闭包（按一次后 F8 就永久失效）。这里用 ref 持有最新实现，监听只读 ref。
  const screenshotRef = useRef<() => void>(() => {})

  // 用于追踪上一轮 AI 的提问内容（配对 QA 记录）
  const lastAIQuestionRef = useRef<string>('')

  // 题库选题
  const [qbModalOpen, setQbModalOpen] = useState(false)
  const [qbList, setQbList] = useState<QuestionItem[]>([])
  const [qbLoading, setQbLoading] = useState(false)
  const [qbSearch, setQbSearch] = useState('')
  const [selectedQbIds, setSelectedQbIds] = useState<string[]>(questionBankIds)
  const [qbMode, setQbMode] = useState<'strict' | 'mixed' | 'adaptive'>(questionBankMode)

  const openQbModal = async () => {
    setQbModalOpen(true)
    setQbLoading(true)
    try {
      const res = await questionBankApi.list({ page: 1, page_size: 100 })
      setQbList(res.questions)
    } catch { /* ignore */ }
    setQbLoading(false)
  }

  const confirmQbSelection = () => {
    setQuestionBankIds(selectedQbIds)
    setQuestionBankMode(qbMode)
    setQbModalOpen(false)
    message.success(`已选择 ${selectedQbIds.length} 道题目 · ${qbMode === 'strict' ? '严格模式' : qbMode === 'mixed' ? '混合模式' : '灵活改编'}`)
  }

  const toggleQbItem = (id: string) => {
    setSelectedQbIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const filteredQbList = qbSearch
    ? qbList.filter((q) => q.title.includes(qbSearch) || q.content.includes(qbSearch))
    : qbList

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)
  /** 视口是否停在底部（自动滚动的唯一依据） */
  const [autoScroll, setAutoScroll] = useState(true)
  /** 同一帧内的多个滚动源只吸附一次，避免重复 scrollIntoView 造成抖动 */
  const rafRef = useRef<number | null>(null)
  /** 区分「用户手动滚动」与「程序自动滚动」：后者不应把 autoScroll 关掉 */
  const programmaticScrollRef = useRef(false)

  /**
   * 自动滚动到底部。
   *
   * 规则：**只有视口本来就在底部时才跟随新内容**。用户手动上滚查看历史后，
   * 发送新消息、流式输出都不会把视口拽回底部；等用户自己滚回底部，跟随自动恢复。
   */
  useEffect(() => {
    if (!autoScroll) return
    const el = chatContainerRef.current
    if (!el) return

    // 合并同一帧内的多次触发（messages / currentContent / currentReasoning 会各自引起一次渲染）
    if (rafRef.current !== null) return
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null
      const node = chatContainerRef.current
      if (!node) return
      programmaticScrollRef.current = true
      // 流式输出用瞬时滚动，避免 smooth 动画与新内容竞争导致界面抖动
      if (isStreaming) {
        node.scrollTop = node.scrollHeight
      } else {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
      }
      // 滚动事件是异步派发的，下一帧再解除标记（期间用户手动滚动仍能生效）
      requestAnimationFrame(() => {
        programmaticScrollRef.current = false
      })
    })
  }, [messages, currentContent, currentReasoning, autoScroll, isStreaming])

  // 卸载时取消未执行的滚动帧
  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [])

  /** 检测视口是否停在底部（程序触发的滚动不改变该状态） */
  const handleScroll = useCallback(() => {
    const el = chatContainerRef.current
    if (!el) return
    if (programmaticScrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = el
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 100)
  }, [])

  /**
   * 发送新消息前，按当时的视口位置决定是否跟随。
   *
   * 之前这里无条件 setAutoScroll(true)，导致用户上滚看历史时一发消息就被拉到底部；
   * 现在改为「在底部才跟随」——但滚动容差收紧到 4px：若原本已在底部，
   * 新消息把内容顶下去后 100px 的判定会立刻变成 false 而误判为「用户上滚」，
   * 用视口当前是否贴底来判定更准确。
   */
  const syncAutoScrollBeforeSend = useCallback(() => {
    const el = chatContainerRef.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    setAutoScroll(distance < 4)
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
    syncAutoScrollBeforeSend()
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

  /**
   * 系统音频转写出的问题 → 自动发给 AI 回答。
   *
   * 与截图答题的区别：截图是一次性动作，而音频转写是**持续**的，
   * 可能在 AI 还在回答上一题时就断句出新问题。因此这里不直接丢弃，
   * 而是排队，等当前流式输出结束后再依次发送。
   */
  const askQueueRef = useRef<string[]>([])
  const askingRef = useRef(false)
  // 用 ref 持有最新的 drain 函数：handleTranscriptQuestion 会作为 prop
  // 传给面板并被其闭包捕获，直接依赖函数标识容易拿到过期版本。
  const drainRef = useRef<() => Promise<void>>(async () => {})

  const handleTranscriptQuestion = useCallback((text: string) => {
    const question = text.trim()
    if (!question) return
    askQueueRef.current.push(question)
    void drainRef.current()
  }, [])

  /** 依次把排队的转写问题发给 AI，保证同一时刻只有一路流式输出 */
  const drainAskQueue = useCallback(async () => {
    if (askingRef.current) return
    askingRef.current = true
    try {
      while (askQueueRef.current.length > 0) {
        // 等上一轮流式输出结束：sendMessage 在流式进行中会直接 return，
        // 不等待就会把问题悄悄丢掉
        while (useChatStore.getState().isStreaming) {
          await new Promise((r) => setTimeout(r, 400))
        }
        const next = askQueueRef.current.shift()
        if (!next) break

        syncAutoScrollBeforeSend()
        try {
          // 用 displayLabel 标注来源，避免用户分不清是手打还是听来的
          await sendMessage(next, { displayLabel: '🎧 系统音频' })
        } catch {
          message.error('发送失败')
        }
      }
    } finally {
      askingRef.current = false
    }
  }, [sendMessage, message, syncAutoScrollBeforeSend])

  // 每次渲染同步最新的 drain 实现
  drainRef.current = drainAskQueue

  /**
   * 系统音频监听。
   *
   * 开关在「设置」里，打开后只要停留在本页面（AI 对话界面）就自动监听；
   * 离开页面或关闭开关会自动停止（hook 内部负责清理，避免设备被长期占用）。
   *
   * 识别结果的处理取决于「自动让 AI 回答」：
   *   开 → 直接作为提问发给当前模式（面试官 / 求职者）的对话
   *   关 → 填进输入框，由用户确认后再发送
   */
  const { listening: systemAudioListening, sttConnected: systemAudioSttConnected, sttError: systemAudioSttError } =
    useSystemAudioListener({
      active: true, // ChatPage 挂载期间即为「处于 AI 对话界面」
      onText: (text) => {
        // 注意：sendMessage / addMessage 内部都通过 getState() 读取**当前**
        // 的 selectedMode，因此识别结果会落到此刻正在使用的那个模式
        // （🎯 面试官 或 🧑 求职者）的对话里，而不是固定的某一个。
        if (useAppStore.getState().systemAudioAutoAsk) {
          handleTranscriptQuestion(text)
        } else {
          // 不自动发送时，追加到输入框（保留用户已输入的内容）
          // 只填输入框、不产生新消息，因此不动视口：用户上滚看历史时不该被拽回底部
          setInputValue((prev) => (prev.trim() ? `${prev} ${text}` : text))
        }
      },
      onError: (err) => message.error(`系统音频：${err}`),
    })

  // 把监听状态同步到 store，供「设置」面板展示
  useEffect(() => {
    setSystemAudioStatus({
      listening: systemAudioListening,
      sttConnected: systemAudioSttConnected,
      error: systemAudioSttError,
    })
  }, [systemAudioListening, systemAudioSttConnected, systemAudioSttError, setSystemAudioStatus])

  // 卸载时清空队列，避免页面切走后还在发请求
  useEffect(() => {
    return () => {
      askQueueRef.current = []
    }
  }, [])

  /**
   * 截图答题：抓取整个屏幕，交给视觉模型识别题目并作答，
   * 结果作为一条普通 assistant 消息插入当前对话（与 AI 回复同样渲染）。
   */
  const handleScreenshot = async () => {
    if (capturing || isStreaming) return

    // 前置拦截：选中的模型明确不支持图片时，直接告知用户，省掉一次截屏开销
    const captureModel = models.find((m) => m.id === selectedModel)
    if (captureModel && captureModel.supports_vision === false) {
      const detail =
        `当前模型「${captureModel.name}」不支持图片输入，无法识别截图。` +
        '请在模型选择器中改用带 🖼 标记的模型。'
      addMessage({
        role: 'user',
        content: `📷 截图答题${inputValue.trim() ? `：${inputValue.trim()}` : ''}`,
      })
      addMessage({ role: 'assistant', content: `> ⚠️ 截图识别失败\n\n${detail}` })
      message.error(detail)
      return
    }

    setCapturing(true)
    setCaptureElapsed(0)
    const startedAt = Date.now()
    const timer = setInterval(() => {
      setCaptureElapsed(Math.floor((Date.now() - startedAt) / 1000))
    }, 200)

    // 记录用户触发的动作，让对话上下文更清晰
    addMessage({
      role: 'user',
      content: `📷 截图答题${inputValue.trim() ? `：${inputValue.trim()}` : ''}`,
    })

    try {
      // 截图前把自己从屏幕捕获中排除：本应用也是屏幕上的一个窗口，
      // 否则整屏截图会把自己拍进去（画面里只有本应用，毫无意义）。
      //
      // 独立窗口模式（desktop.py）下窗口由本进程创建，
      // SetWindowDisplayAffinity 能真正生效；浏览器里则退化为无操作。
      const state = isDesktopWindow() ? await getWindowState() : null
      const wasExcluded = state?.capture_exclude ?? true
      if (state?.ok && !wasExcluded) {
        await setCaptureExclude(true)
      }
      // 等一帧，让窗口管理器完成重绘后再抓屏
      await new Promise((r) => setTimeout(r, 260))

      let res
      try {
        res = await screenshotApi.capture({
          // 把输入框内容作为附加要求；为空则用后端内置提示词
          prompt: inputValue.trim() || undefined,
          // 不传 api_key：后端会用该用户在数据库里加密保存的密钥
          // 模型与思考配置跟随界面选择：
          // 后端会用官方 /models 的 input_modalities 校验该模型能否看图，
          // 不支持时直接返回「不支持图片输入」，不会静默换成别的模型。
          model: selectedModel || undefined,
          thinking_enabled: thinkingEnabled,
          reasoning_effort: thinkingEnabled ? reasoningEffort : undefined,
        })
      } finally {
        // 恢复用户原本的捕获排除设置，不改变他的窗口行为
        if (state?.ok && !wasExcluded) {
          await setCaptureExclude(false)
        }
      }

      const meta =
        `> 📷 屏幕截图 · ${res.width}×${res.height} · ` +
        `${(res.elapsed_ms / 1000).toFixed(1)}s · 模型 \`${res.model}\`` +
        `${res.thinking_enabled ? ' · 🧠 思考' : ''}`

      addMessage({ role: 'assistant', content: `${meta}\n\n${res.answer}` })
      setInputValue('')
      syncAutoScrollBeforeSend()
      message.success(`识别完成（${(res.elapsed_ms / 1000).toFixed(1)}s）`)
    } catch (err) {
      const detail = (err as Error).message || '截图识别失败'
      // 失败也写进对话，避免用户以为按钮没反应
      addMessage({
        role: 'assistant',
        content: `> ⚠️ 截图识别失败\n\n${detail}`,
      })
      message.error(detail)
    } finally {
      clearInterval(timer)
      setCapturing(false)
      setCaptureElapsed(0)
    }
  }

  // 始终指向最新一次渲染的 handleScreenshot（见 screenshotRef 的声明说明）
  useEffect(() => {
    screenshotRef.current = handleScreenshot
  })

  /**
   * 全局 F8 快捷键：等价于点击「截图」按钮。
   *
   * 分两层，优先用第一层：
   *
   * 1) **独立窗口模式（desktop.py）**：调用后端注册 Win32 全局热键
   *    （RegisterHotKey）。热键由系统投递，**窗口失焦时同样能触发** ——
   *    这正是截图场景的关键：按 F8 时焦点通常在题目所在的窗口上，
   *    本应用并不聚焦，网页的 keydown 根本收不到按键。
   *    后端的 js_api 是单向的（前端调后端），所以这里还要在 window 上
   *    挂一个回调函数，并把它登记给后端，由后端 evaluate_js 调用。
   *
   * 2) **浏览器模式**：拿不到全局热键（浏览器安全边界所限），
   *    退化为窗口内的 keydown 监听 —— 只在窗口聚焦时生效。
   */
  useEffect(() => {
    const invoke = () => screenshotRef.current()

    // 窗口内监听：浏览器模式下是唯一手段；独立窗口模式下作为
    // 全局热键注册失败（例如 F8 被别的程序占用）时的兜底。
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'F8') return
      // 按住不放会连续触发 keydown，截图是重操作，只认首次按下
      if (e.repeat) return
      e.preventDefault()
      invoke()
    }
    const addWindowListener = () => window.addEventListener('keydown', onKeyDown)

    // 后端热键触发时会执行 window.__onScreenshotHotkey()
    const HOTKEY_CALLBACK = '__onScreenshotHotkey'
    const w = window as unknown as Record<string, unknown>

    if (isDesktopWindow()) {
      w[HOTKEY_CALLBACK] = invoke
      // 全局热键注册成功前先挂上窗口内监听，保证 F8「至少能用」；
      // 注册成功后再摘掉，避免同一次按键触发两次截图。
      addWindowListener()
      let cancelled = false
      void (async () => {
        // 先登记回调再注册热键，避免热键已生效但回调还没挂上
        const bound = await setHotkeyHandler(HOTKEY_CALLBACK)
        if (cancelled) return
        if (!bound.ok) {
          console.warn('登记全局热键回调失败，仅窗口内快捷键可用:', bound.error)
          return
        }
        const res = await registerScreenshotHotkey()
        if (cancelled) return
        if (res.ok) {
          // 全局热键已生效，摘掉窗口内监听防止重复触发
          window.removeEventListener('keydown', onKeyDown)
          console.info(`已注册全局热键 ${res.hotkey}（窗口失焦也能触发）`)
        } else {
          console.warn('注册全局热键失败，仅窗口内快捷键可用:', res.error)
        }
      })()
      return () => {
        cancelled = true
        delete w[HOTKEY_CALLBACK]
        window.removeEventListener('keydown', onKeyDown)
        // 注销热键，把 F8 还给其它程序；否则会一直占用到进程退出
        void unregisterScreenshotHotkey()
      }
    }

    // 浏览器模式：仅在窗口聚焦时有效
    addWindowListener()
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

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
  //
  // 密钥存在服务端数据库里（Fernet 加密），本地只有掩码提示。
  // 打开弹窗时不预填输入框：服务端不会回传明文，用户若要更换只能重新键入。
  const openApiKeyModal = () => {
    setApiKeyInput('')
    setApiKeyModalOpen(true)
  }

  const handleApiKeySave = async () => {
    const next = apiKeyInput.trim()
    if (!next) {
      // 什么都没输入就点保存：不做任何改动（清除请走「清除」按钮，
      // 因为这里已无从判断用户是想清空还是只是没填）
      setApiKeyModalOpen(false)
      return
    }
    setApiKeySaving(true)
    try {
      const res = await settingsApi.saveApiKey(next)
      setApiKeyHint(res.hint)
      setApiKeyInput('')
      setApiKeyModalOpen(false)
      message.success('API Key 已保存')
    } catch (err) {
      message.error((err as Error).message || 'API Key 保存失败')
    } finally {
      setApiKeySaving(false)
    }
  }

  // 显式清除：清掉服务端保存的 Key，之后回退到 .env 配置
  const handleApiKeyClear = async () => {
    setApiKeySaving(true)
    try {
      await settingsApi.clearApiKey()
      setApiKeyHint('')
      setApiKeyInput('')
      setApiKeyModalOpen(false)
      message.info('API Key 已清除，将使用服务端默认配置')
    } catch (err) {
      message.error((err as Error).message || 'API Key 清除失败')
    } finally {
      setApiKeySaving(false)
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

  // 根据时间、面试计划和 AI 消息推断当前阶段
  const estimatedPhase = (): string => {
    if (!interviewPlan) return 'intro'
    if (elapsedMin <= 2) return 'intro'

    const plan = interviewPlan
    const introEnd = plan.breakdown?.['自我介绍'] || 3
    const codingMin = plan.coding_reserved_min || 0
    const reverseMin = plan.breakdown?.['反问环节'] || 3
    // 兼容「技术问答」和「综合素质问答」两种 key
    const techQaMin = (plan.breakdown?.['技术问答'] || plan.breakdown?.['综合素质问答'] || 0)

    // 优先使用后端计划推算的 current_phase
    const backendPhase = plan.current_phase

    // 反问检测：仅匹配面试官明确发出的反问邀请句式，避免误判
    // 「你有什么问题想问我的吗？」— 来自 interviewer prompt 的固定话术
    const lastAssistantMsgs = messages.filter(m => m.role === 'assistant').slice(-3)
    const hasReverseSignal = lastAssistantMsgs.some(m =>
      m.content.includes('你有什么问题想问我的吗') ||
      m.content.includes('你还有什么问题想问') ||
      m.content.includes('还有其他问题吗')
    )

    // 进入反问阶段的条件（满足任一）：
    // 1. AI 明确发出了反问邀请
    // 2. 剩余时间已进入反问窗口（reverseMin + 2分钟内）
    // 3. 后端计划已判定为反问阶段
    if (hasReverseSignal || remainingMin <= reverseMin + 2 || backendPhase === 'reverse') return 'reverse'
    if (codingEnabled && codingMin > 0 && elapsedMin >= introEnd + techQaMin * 0.6) return 'coding'
    if (elapsedMin >= introEnd) return 'tech_qa'
    return 'intro'
  }

  const currentPhase = estimatedPhase()
  const phaseInfo = (() => {
    const base = PHASE_LABELS[currentPhase]
    if (!base) return { label: '未知', color: 'default' as const }
    // HR面时「技术问答」→「综合素质问答」
    if (currentPhase === 'tech_qa' && interviewRound === 'hr') {
      return { label: '综合素质问答', color: 'green' }
    }
    return base
  })()

  // 进度百分比
  const progressPercent = interviewDuration > 0 ? Math.min(100, Math.round((elapsedSec / 60) / interviewDuration * 100)) : 0

  // 自动检测面试结束 / 清理持久化残留 → 自动关闭练习状态
  useEffect(() => {
    if (!practiceActive) return

    // 清理持久化残留：practiceStartTime 未持久化，刷新后为 null，
    // 若 practiceActive 被 localStorage 恢复但计时器无法启动，则自动重置
    if (!practiceStartTime) {
      resetPractice()
      return
    }

    // 流式输出进行中不检测，等 AI 说完再判断
    if (isStreaming) return

    // 条件1：时间已耗尽（已过时间 ≥ 设定时长 + 1分钟缓冲）
    const timeExpired = elapsedMin > 0 && remainingMin <= 0 && elapsedMin >= interviewDuration + 1

    // 条件2：AI 最近的消息中包含面试结束语
    const lastAssistantMsgs = messages.filter(m => m.role === 'assistant').slice(-2)
    const farewellKeywords = [
      '面试到此结束', '面试结束', '感谢参加', '感谢你参加',
      '我们会尽快反馈', '面试结果', '祝你好运', '期待与你',
      '今天的面试就到这里', '本次面试', '再见', '保持联系',
    ]
    const hasFarewell = lastAssistantMsgs.some(m =>
      farewellKeywords.some(kw => m.content.includes(kw))
    )

    if (timeExpired || hasFarewell) {
      resetPractice()
      lastAIQuestionRef.current = ''
    }
  }, [messages, elapsedMin, remainingMin, practiceActive, interviewDuration, isStreaming])

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
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        // 高度按「视口 - 顶栏 - 内容区留白」精确计算。
        // 顶栏固定 48px；MainLayout 的 Content 在普通模式是 24px 上、8px 下，
        // 共 80px。原来是写死的 140px，比实际多留 60px，
        // 表现为输入框下方空出一大块 —— 这里改成与实际留白一致的精确值。
        // 全屏会话模式没有顶栏、留白各 8px，且外层已是 column flex，
        // 所以直接用 flex:1 吃满剩余空间，不依赖 vh（缩放后会算错）。
        ...(focusMode
          ? { flex: 1, minHeight: 0 }
          : { height: 'calc(100vh - 80px)' }),
      }}
    >
      {/* 顶部工具栏：全屏会话模式整个隐藏，只留一个悬浮的退出按钮。
          按职责分两行，避免一行塞十几个控件后 flex-wrap 在随机位置断行：
            第一行「怎么面」—— 模式 / 模型 / 岗位，决定这次对话的基本形态
            第二行「面试参数 + 操作」—— 级别 / 轮次 /（求职者参数）/ 开关 / 按钮
          两行都用 Divider 分组，不再手写竖线 div：wrap 断行时手写竖线
          会跑到行首或行尾变成悬空的一条，Divider 的行为是正确的。 */}
      {!focusMode && (
      <div
        style={{
          padding: '8px 0',
          borderBottom: '1px solid #f0f0f0',
          marginBottom: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
        }}
      >
        {/* ── 第一行：对话形态 ── */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <Segmented
            value={selectedMode}
            onChange={(val) => {
              // 切换模式前先中止正在进行的流式输出，防止内容串到新模式界面
              if (isStreaming) {
                abort()
              }
              setMode(val as ChatMode)
            }}
            options={[
              { value: 'interviewer', label: '面试官' },
              { value: 'candidate', label: '求职者' },
            ]}
          />
          <Divider type="vertical" style={{ margin: 0, height: 18 }} />
          <ModelSelector />
          <Divider type="vertical" style={{ margin: 0, height: 18 }} />
          <PositionSelect />
        </div>

        {/* ── 第二行：面试参数 + 操作 ── */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          {/* 候选人经验级别（影响 AI 的答题/提问策略） */}
          <Space size={4}>
            <UserOutlined style={{ color: '#8c8c8c' }} />
            <Select
              size="small"
              value={candidateLevel || undefined}
              onChange={(val) => {
                setCandidateLevel(val || null)
                setInterviewPlan(null)
              }}
              placeholder="经验级别"
              allowClear
              style={{ width: 100 }}
              options={[
                { value: 'intern', label: '实习' },
                { value: 'new_grad', label: '校招' },
                { value: 'experienced', label: '社招' },
              ]}
            />
          </Space>

          {/* 面试轮次（决定一面广筛 / 二面深挖 / HR 综合素质） */}
          <Space size={4}>
            <SyncOutlined style={{ color: '#8c8c8c' }} />
            <Select
              size="small"
              value={interviewRound || undefined}
              onChange={(val) => {
                setInterviewRound(val || null)
                setInterviewPlan(null)
              }}
              placeholder="面试轮次"
              allowClear
              style={{ width: 100 }}
              options={[
                { value: 'first', label: '一面' },
                { value: 'second', label: '二面' },
                { value: 'hr', label: 'HR 面' },
              ]}
            />
          </Space>

          {/* 仅求职者模式：时长 + 回答风格 + 推算 + 编程题 */}
          {selectedMode === 'candidate' && (
            <>
              <Space size={4}>
                <ClockCircleOutlined style={{ color: '#8c8c8c' }} />
                <Select
                  size="small"
                  value={interviewDuration}
                  onChange={(val) => {
                    setInterviewDuration(val)
                    setInterviewPlan(null)
                  }}
                  style={{ width: 96 }}
                  options={[
                    { value: 15, label: '15 分钟' },
                    { value: 30, label: '30 分钟' },
                    { value: 45, label: '45 分钟' },
                    { value: 60, label: '60 分钟' },
                  ]}
                />
                {interviewPlan && <Tag color="blue">{interviewPlan.question_count} 题</Tag>}
              </Space>
              <Select
                size="small"
                value={answerLength}
                onChange={(val) => {
                  setAnswerLength(val)
                  setInterviewPlan(null)
                }}
                style={{ width: 96 }}
                options={[
                  { value: 'short', label: '简短' },
                  { value: 'medium', label: '适中' },
                  { value: 'long', label: '详细' },
                ]}
              />
              <Tooltip title="根据时长、级别、轮次和回答风格推算问题数量">
                <Button size="small" type="link" onClick={handleGetPlan} style={{ padding: '0 4px' }}>
                  推算
                </Button>
              </Tooltip>
              <Tooltip title="让 AI 面试官从 LeetCode Hot100 / 面试经典 150 中出编程题，难度根据岗位和回答表现自动调整">
                <Space size={4}>
                  <Switch size="small" checked={codingEnabled} onChange={setCodingEnabled} />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    <CodeOutlined /> 编程题
                  </Text>
                </Space>
              </Tooltip>
            </>
          )}

          <Divider type="vertical" style={{ margin: 0, height: 18 }} />

          <Space size={4}>
            <Switch size="small" checked={useSearch} onChange={setUseSearch} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              <SearchOutlined /> 联网搜索
            </Text>
          </Space>
          <Space size={4}>
            <Switch size="small" checked={highlightCode} onChange={toggleHighlightCode} />
            <Text type="secondary" style={{ fontSize: 12 }}>
              代码高亮
            </Text>
          </Space>

          {/* 右侧操作区：用独立的 flex 容器 + marginLeft:auto 贴右，
              而不是在会换行的父容器里塞一个 flex:1 撑杆 —— 撑杆只占第一行，
              一旦换行，操作按钮会被甩到第二行**左对齐**，正是原来「杂乱」的成因。
              这样分组后，即使换行也是一整块右对齐地掉下去，视觉上仍然成组。 */}
          <Space size={8} style={{ marginLeft: 'auto' }} wrap>
            <Tooltip
              title={
                apiKeyHint
                  ? `DeepSeek API Key 已配置（${apiKeyHint}）`
                  : '配置 DeepSeek API Key'
              }
            >
              <Button
                size="small"
                icon={<KeyOutlined />}
                type={apiKeyHint ? 'primary' : 'default'}
                ghost={!!apiKeyHint}
                onClick={openApiKeyModal}
              >
                {apiKeyHint ? '已配置' : 'API Key'}
              </Button>
            </Tooltip>

            <Button
              size="small"
              icon={<SettingOutlined />}
              onClick={() => setPromptEditorOpen(true)}
            >
              Prompt
            </Button>

            <Tooltip
              title={
                questionBankIds.length > 0
                  ? `已选 ${questionBankIds.length} 题 · ${questionBankMode}`
                  : '从题库选题'
              }
            >
              <Button
                size="small"
                icon={<BookOutlined />}
                type={questionBankIds.length > 0 ? 'primary' : 'default'}
                ghost={questionBankIds.length > 0}
                onClick={openQbModal}
              >
                选题{questionBankIds.length > 0 ? `(${questionBankIds.length})` : ''}
              </Button>
            </Tooltip>

            {/* 全屏会话：只留对话与输入，隐藏侧边栏 / 顶栏 / 本工具栏（Esc 也可退出） */}
            <Tooltip title="全屏会话：只显示对话内容，隐藏其它界面元素（Esc 退出）">
              <Button
                size="small"
                icon={<FullscreenOutlined />}
                onClick={toggleFocusMode}
                aria-label="进入全屏会话"
              >
                全屏
              </Button>
            </Tooltip>

            {/* 破坏性操作收进溢出菜单：不常用、且点了会丢数据，
                不该和「选题」「Prompt」并排抢点击。 */}
            <Dropdown
              trigger={['click']}
              menu={{
                items: [
                  {
                    key: 'clear-current',
                    danger: true,
                    icon: <ClearOutlined />,
                    label: `清空当前对话（${selectedMode === 'candidate' ? '求职者' : '面试官'}）`,
                  },
                  {
                    key: 'clear-all',
                    danger: true,
                    icon: <ClearOutlined />,
                    label: '清空全部对话（两种模式）',
                  },
                ],
                onClick: ({ key }) => {
                  // 用 modal.confirm 做二次确认：Dropdown 菜单项本身不能再套 Popconfirm
                  if (key === 'clear-current') {
                    modal.confirm({
                      title: '确定清空当前模式对话记录？',
                      okText: '清空当前',
                      cancelText: '取消',
                      okButtonProps: { danger: true },
                      onOk: handleClear,
                    })
                  } else {
                    modal.confirm({
                      title: '确定清空全部（面试官 + 求职者）对话记录？',
                      okText: '全部清空',
                      cancelText: '取消',
                      okButtonProps: { danger: true },
                      onOk: handleClearAll,
                    })
                  }
                },
              }}
            >
              <Button size="small" icon={<MoreOutlined />} aria-label="更多操作" />
            </Dropdown>
          </Space>
        </div>
      </div>
      )}

      {/* 全屏会话模式：工具栏被隐藏，这里补一个悬浮的退出按钮，
          免得用户不知道该怎么回去（Esc 是另一条退路，但不够显眼）。
          平时半透明，指上去才实心，尽量不打扰对话内容 */}
      {focusMode && (
        <Tooltip title="退出全屏会话（Esc）">
          <Button
            size="small"
            icon={<FullscreenExitOutlined />}
            onClick={toggleFocusMode}
            aria-label="退出全屏会话"
            style={{
              position: 'fixed',
              top: 8,
              right: 8,
              zIndex: 100,
              opacity: 0.3,
              transition: 'opacity 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.opacity = '1'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.opacity = '0.3'
            }}
          >
            退出全屏
          </Button>
        </Tooltip>
      )}

      {/* 练习进度条（悬浮置顶，对话滚动时始终可见） */}
      {practiceActive && (
        <div
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 10,
            flexShrink: 0,
            background: token.colorPrimaryBg,
            borderRadius: 8,
            padding: '8px 16px',
            marginBottom: 12,
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
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

      {/* 消息列表 */}
      <div
        ref={chatContainerRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          // minHeight:0：flex 子项默认 min-height:auto 会被内容撑高，
          // 那样滚动条会落到整页上，底部输入框被挤出视口
          minHeight: 0,
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

        {messages.map((msg, idx) => (
          <ChatMessage key={idx} message={msg} highlightCode={highlightCode} ttsAvailable={ttsAvailable} />
        ))}
        {streamingMessage && (
          <ChatMessage message={streamingMessage} highlightCode={highlightCode} isStreaming ttsAvailable={ttsAvailable} />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* 语音输入面板（flexShrink:0：高度优先让给消息列表，面板本身不被压扁） */}
      {sttAvailable && (
        <div style={{ padding: '8px 0 0', flexShrink: 0 }}>
          <VoiceInputPanel
            onResult={(text) => {
              setInputValue(text)
            }}
            disabled={isStreaming}
          />
        </div>
      )}

      {/* 底部输入区（flexShrink:0：任何情况下都要完整可见，不被上方内容挤出视口） */}
      <div
        style={{
          padding: '12px 0 0',
          borderTop: '1px solid #f0f0f0',
          display: 'flex',
          gap: 8,
          alignItems: 'flex-end',
          flexShrink: 0,
        }}
      >
        <TextArea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            selectedMode === 'interviewer'
              ? '你是面试官，输入你的提问... (Enter 发送, Shift+Enter 换行)｜点「截图」或按 F8 可识别屏幕上的题目'
              : '你是求职者，输入你的回答... (Enter 发送, Shift+Enter 换行)｜点「截图」或按 F8 可识别屏幕上的题目'
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

        {/* 截图答题：抓取整个屏幕，交给视觉模型识别题目并作答（也可按 F8） */}
        <Tooltip
          title={
            capturing
              ? '正在截图并识别…'
              : '截取主显示器画面，AI 提取题目并作答（结果直接显示在对话中）｜快捷键 F8'
          }
        >
          <Button
            icon={capturing ? <LoadingOutlined /> : <CameraOutlined />}
            onClick={handleScreenshot}
            disabled={capturing || isStreaming}
            style={{ height: 40 }}
          >
            {capturing ? `${captureElapsed}s` : '截图'}
          </Button>
        </Tooltip>
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
        footer={(_, { OkBtn, CancelBtn }) => (
          <Space>
            {!!apiKeyHint && (
              <Popconfirm
                title="确认清除 API Key？"
                description="清除后将改用服务端 .env 中配置的默认密钥。"
                okText="清除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
                onConfirm={handleApiKeyClear}
              >
                <Button danger loading={apiKeySaving}>清除</Button>
              </Popconfirm>
            )}
            <CancelBtn />
            <OkBtn />
          </Space>
        )}
      >
        <div style={{ marginBottom: 16 }}>
          {apiKeyHint ? (
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              <Text>
                当前已配置：<Text code>{apiKeyHint}</Text>
              </Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                输入新密钥并保存可覆盖；要取消配置请点左下角「清除」。
              </Text>
            </Space>
          ) : (
            <Text type="secondary">
              输入你的 DeepSeek API Key，将优先使用此密钥进行对话。
              留空则使用服务端默认配置。
            </Text>
          )}
        </div>
        <Input.Password
          value={apiKeyInput}
          onChange={(e) => setApiKeyInput(e.target.value)}
          placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
          autoFocus
        />
        <div style={{ marginTop: 12 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            密钥会加密保存在服务端数据库中，重启应用不会丢失，也不会写进浏览器。
            你可以从{' '}
            <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noopener noreferrer">
              DeepSeek 开放平台
            </a>{' '}
            获取 API Key。
          </Text>
        </div>
      </Modal>

      {/* 题库选题弹窗 */}
      <Modal
        title="从题库选题"
        open={qbModalOpen}
        onOk={confirmQbSelection}
        onCancel={() => setQbModalOpen(false)}
        okText={`确认选择 (${selectedQbIds.length})`}
        cancelText="取消"
        width={700}
      >
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {/* 模式选择 */}
          <Space>
            <Text strong>出题模式：</Text>
            <Select
              value={qbMode}
              onChange={(v) => setQbMode(v)}
              style={{ width: 180 }}
              options={[
                { value: 'strict', label: '🔒 严格 — 完全按题库原文出题' },
                { value: 'mixed', label: '🔗 混合 — 必考题+少量自补题' },
                { value: 'adaptive', label: '🎨 灵活改编 — AI可调整措辞难度' },
              ]}
            />
          </Space>

          {/* 搜索 */}
          <Input
            placeholder="搜索题目..."
            prefix={<SearchOutlined />}
            value={qbSearch}
            onChange={(e) => setQbSearch(e.target.value)}
            allowClear
          />

          {/* 题目列表 */}
          <div style={{ maxHeight: 400, overflow: 'auto', border: '1px solid #f0f0f0', borderRadius: 8, padding: 8 }}>
            {qbLoading ? (
              <Text type="secondary">加载中...</Text>
            ) : filteredQbList.length === 0 ? (
              <Text type="secondary">无匹配题目</Text>
            ) : (
              filteredQbList.map((q) => {
                const checked = selectedQbIds.includes(q.id)
                return (
                  <div
                    key={q.id}
                    onClick={() => toggleQbItem(q.id)}
                    style={{
                      padding: '8px 12px',
                      cursor: 'pointer',
                      borderRadius: 6,
                      marginBottom: 4,
                      background: checked ? token.colorPrimaryBg : token.colorBgContainer,
                      border: checked
                        ? `1px solid ${token.colorPrimary}`
                        : `1px solid ${token.colorBorderSecondary}`,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    <input type="checkbox" checked={checked} readOnly />
                    <Tag color={DIFFICULTY_COLORS[q.difficulty] || 'default'}>
                      {DIFFICULTY_LABELS[q.difficulty] || q.difficulty}
                    </Tag>
                    <Text ellipsis style={{ flex: 1 }}>{q.title}</Text>
                    <Tag>{q.category}</Tag>
                  </div>
                )
              })
            )}
          </div>
        </Space>
      </Modal>
    </div>
  )
}

export default ChatPage
