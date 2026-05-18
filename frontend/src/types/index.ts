// ============ 对话相关 ============

export interface Message {
  role: 'system' | 'user' | 'assistant'
  content: string
  reasoning?: string  // 思维链内容（前端用）
}

export interface ChatRequest {
  messages: Message[]
  mode?: 'interviewer' | 'candidate'
  position_name?: string
  jd_id?: string  // 指定使用某份 JD（为空则使用全部 JD）
  use_search?: boolean
  coding_enabled?: boolean
  model?: string
  thinking_enabled?: boolean
  reasoning_effort?: 'high' | 'max'
  prompt_override?: string
  api_key?: string
  resume_text?: string
  code_context?: string
}

export type ChatMode = 'interviewer' | 'candidate'

export interface PromptTemplates {
  interviewer?: string
  candidate?: string
}

// ============ 模型相关 ============

export interface ModelInfo {
  id: string
  name: string
  description: string
  supports_thinking: boolean
}

export interface ModelsResponse {
  models: ModelInfo[]
}

// ============ 面试相关 ============

export interface ReportRequest {
  messages: Message[]
  mode: string
  api_key?: string
}

export interface ReportResponse {
  report: string
}

// ============ 面试计划相关 ============

export interface InterviewPlanRequest {
  mode: string
  duration_minutes: number
  answer_length: 'short' | 'medium' | 'long'
}

export interface InterviewPlanResponse {
  question_count: number
  duration_minutes: number
  avg_time_per_question: number
  description: string
  breakdown: Record<string, number>
}

// ============ 上传相关 ============

export interface UploadResponse {
  filename: string
  text: string
  type: 'resume' | 'code'
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
