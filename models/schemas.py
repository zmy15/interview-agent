"""数据模型定义"""

from pydantic import BaseModel, Field
from typing import Optional


# ============ 对话相关 ============

class Message(BaseModel):
    role: str  # system / user / assistant
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    mode: Optional[str] = None  # "interviewer" / "candidate"
    position_name: Optional[str] = None  # 关联岗位，触发 RAG 检索
    use_search: bool = False
    model: Optional[str] = None  # 覆盖默认模型
    thinking_enabled: Optional[bool] = None  # 覆盖默认思考开关
    reasoning_effort: Optional[str] = None  # "high" / "max"
    api_key: Optional[str] = None  # 前端传入的 API Key，覆盖 .env 配置
    resume_text: Optional[str] = None  # 上传的简历文本
    code_context: Optional[str] = None  # 上传的代码文本（仅面试官模式使用）


class ChatResponse(BaseModel):
    content: str


# ============ 模型相关 ============

class ModelInfo(BaseModel):
    id: str
    name: str
    description: str
    supports_thinking: bool


class ModelsResponse(BaseModel):
    models: list[ModelInfo]


# ============ 面试相关 ============

class InterviewStartRequest(BaseModel):
    mode: str
    position_name: Optional[str] = None
    resume_text: Optional[str] = None
    code_context: Optional[str] = None
    model: Optional[str] = None


class InterviewStopRequest(BaseModel):
    pass


class InterviewStopResponse(BaseModel):
    message: str


class ReportRequest(BaseModel):
    messages: list[Message]
    mode: str
    api_key: Optional[str] = None  # 前端传入的 API Key


class ReportResponse(BaseModel):
    report: str


class InterviewPlanRequest(BaseModel):
    mode: str
    duration_minutes: int = Field(30, ge=5, le=120, description="面试时长（分钟），默认30分钟")
    answer_length: str = Field("medium", pattern="^(short|medium|long)$", description="回答长度：short(简短)/medium(适中)/long(详细)")


class InterviewPlanResponse(BaseModel):
    question_count: int
    duration_minutes: int
    avg_time_per_question: float
    description: str
    breakdown: dict  # {"自我介绍": 3, "技术问答": 24, "反问环节": 3}


# ============ 上传相关 ============

class UploadResponse(BaseModel):
    filename: str
    text: str
    type: str


# ============ 岗位管理 ============

class PositionCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    description: str = ""


class PositionUpdate(BaseModel):
    description: str


class JDCreate(BaseModel):
    content: str


class JDResponse(BaseModel):
    id: str
    content: str
    created_at: str


class PositionResponse(BaseModel):
    name: str
    description: str
    jds: list[JDResponse] = []
    created_at: str
    updated_at: str


class PositionListResponse(BaseModel):
    positions: list[PositionResponse]


# ============ 知识库相关 ============

class KnowledgeUploadResponse(BaseModel):
    position_name: str
    chunks_count: int
    message: str


class KnowledgeChunk(BaseModel):
    content: str
    score: float
    metadata: dict = {}


class KnowledgeSearchRequest(BaseModel):
    query: str
    position_name: str
    top_k: int = 3


class KnowledgeSearchResponse(BaseModel):
    results: list[KnowledgeChunk]


class KnowledgeDeleteRequest(BaseModel):
    position_name: str
