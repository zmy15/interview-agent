// ============ 对话相关 ============

export interface Message {
  role: 'system' | 'user' | 'assistant'
  content: string
  reasoning?: string  // 思维链内容（前端用）
  /**
   * 界面附加信息（例如「📷 屏幕截图 · 尺寸 · 耗时 · 模型」）。
   * 只用于本地渲染与展示，**绝不进入模型上下文**：
   * 构建请求时一律只读 content，不读 meta。
   */
  meta?: string
}

export type CandidateLevel = 'intern' | 'new_grad' | 'experienced'
export type InterviewRound = 'first' | 'second' | 'hr'
export type AnswerLength = 'short' | 'medium' | 'long'
/**
 * 思考强度（reasoning_effort）。
 *
 * 官方接受 low / high / max 三档；minimal→low、medium→high、
 * xhigh→high、ultra→max 会被服务端映射，这里只暴露三个规范档位。
 */
export type ReasoningEffort = 'low' | 'high' | 'max'

export interface ChatRequest {
  messages: Message[]
  mode?: 'interviewer' | 'candidate'
  position_name?: string
  jd_id?: string
  use_search?: boolean
  coding_enabled?: boolean
  model?: string
  thinking_enabled?: boolean
  reasoning_effort?: ReasoningEffort
  prompt_override?: string
  api_key?: string
  resume_text?: string
  code_context?: string
  candidate_level?: CandidateLevel
  interview_round?: InterviewRound
  // 面试计划参数（用于时间预算感知）
  interview_duration_minutes?: number
  interview_question_count?: number
  interview_coding_min?: number
  prompt_notes?: string
  /** 随提示词附带的背景文档，后端插在 system 与对话之间 */
  prompt_documents?: { name: string; text: string }[]
  question_bank_ids?: string[]
  question_bank_mode?: 'strict' | 'mixed' | 'adaptive'
}

export type ChatMode = 'interviewer' | 'candidate'

export type PromptTemplates = Partial<Record<ChatMode, string>>

/**
 * 随提示词附带的背景文档（界面「资料」里上传的 txt/md 等）。
 *
 * 它不是对话内容：后端会把它拼成一条独立消息，位置在系统提示词之后、
 * 对话之前（见 routers/chat.py 的 Phase 1.5）。整场对话里内容不变，
 * 因此仍属于稳定前缀，服务端前缀缓存照样命中。
 */
export interface PromptDocument {
  id: string
  name: string
  text: string
  /** 是否随请求发送（关掉可临时摘掉某份文档，而不必删除） */
  enabled: boolean
  /** 上传时间戳（毫秒），仅用于列表排序 */
  addedAt: number
}

// ============ 语音相关 ============

export interface STTResult {
  text: string
  isFinal: boolean
  confidence?: number
}

export interface VADEvent {
  status: 'speech_start' | 'speech_end' | 'silence'
  timestamp: number
}

export interface TTSChunk {
  audioData: ArrayBuffer
  sentenceIndex: number
  totalSentences: number
}

export type VoiceMode = 'vad' | 'manual'

// ============ 模型相关 ============

export interface ModelInfo {
  id: string
  name: string
  description: string
  supports_thinking: boolean
  /** 是否支持图片输入（来自官方 /models 的 input_modalities），截图识别依赖它 */
  supports_vision?: boolean
}

export interface ModelsResponse {
  models: ModelInfo[]
  /** 模型列表来源：remote（官方 /models 接口）/ fallback（本地 AVAILABLE_MODELS 配置） */
  source?: 'remote' | 'fallback'
}

// ============ 面试相关 ============

export interface QARecord {
  question: string
  answer: string
  answer_chars: number
}

export interface ReportRequest {
  messages: Message[]
  mode: string
  api_key?: string
  candidate_level?: CandidateLevel
  interview_round?: InterviewRound
  qa_records?: QARecord[]
}

export interface ReportResponse {
  report: string
}

// ============ 面试计划相关 ============

export interface InterviewPlanRequest {
  mode: string
  duration_minutes: number
  answer_length: AnswerLength
  candidate_level?: CandidateLevel
  interview_round?: InterviewRound
  coding_enabled?: boolean
  elapsed_minutes?: number
  answered_questions?: number
}

export interface InterviewPlanResponse {
  question_count: number
  duration_minutes: number
  avg_time_per_question: number
  description: string
  breakdown: Record<string, number>
  coding_reserved_min: number
  current_phase: string
  remaining_questions: number
}

// ============ 上传相关 ============

export interface UploadResponse {
  filename: string
  text: string
  /** document 为「附加到提示词的背景文档」，不落库、不建索引 */
  type: 'resume' | 'code' | 'document'
}

export interface ProjectStructure {
  source: string[]
  config: string[]
  document: string[]
  build: string[]
  test: string[]
  other: string[]
}

export interface ProjectUploadResponse {
  filename: string
  file_count: number
  structure: ProjectStructure
  total_text: string
  tech_stack: string[]
  type: 'project'
}

export interface UploadRecord {
  id: string
  filename: string
  type: 'resume' | 'code' | 'project'
  text: string
  preview: string
  file_count: number
  tech_stack: string[]
  created_at: string
}

export interface UploadListResponse {
  uploads: UploadRecord[]
}

// ============ 岗位管理 ============

export interface PositionCreate {
  name: string
  description: string
}

export interface PositionUpdate {
  description: string
}

export interface JDCreate {
  content: string
}

export interface JDResponse {
  id: string
  content: string
  created_at: string
}

export interface PositionResponse {
  name: string
  description: string
  position_type: string  // "技术岗" / "非技术岗" / "未知"
  jds: JDResponse[]
  created_at: string
  updated_at: string
}

export interface PositionListResponse {
  positions: PositionResponse[]
}

// ============ 知识库相关 ============

export interface KnowledgeUploadResponse {
  position_name: string
  chunks_count: number
  message: string
}

export interface KnowledgeChunk {
  content: string
  score: number
  metadata: Record<string, string>
}

export interface KnowledgeSearchRequest {
  query: string
  position_name: string
  top_k: number
}

export interface KnowledgeSearchResponse {
  results: KnowledgeChunk[]
}

// ============ SSE 事件 ============

export type SSEEventType = 'reasoning' | 'content' | 'done' | 'error'

export interface SSEEvent {
  type: SSEEventType
  content: string
}

// ============ App 偏好 ============

export interface AppPreferences {
  highlightCode: boolean
  apiKey: string
  interviewDuration: number
}
