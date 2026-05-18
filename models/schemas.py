"""数据模型定义"""

from pydantic import BaseModel, Field
from typing import Optional


# ============ 候选人与面试配置常量 ============

CANDIDATE_LEVELS = ("intern", "new_grad", "experienced")
INTERVIEW_ROUNDS = ("first", "second", "hr")


# ============ 对话相关 ============

class Message(BaseModel):
    role: str  # system / user / assistant
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    mode: Optional[str] = None  # "interviewer" / "candidate"
    position_name: Optional[str] = None  # 关联岗位，触发 RAG 检索
    jd_id: Optional[str] = None  # 指定使用某份 JD（为空则使用全部 JD）
    use_search: bool = False
    coding_enabled: bool = False  # 是否启用编程题（仅求职者模式+技术岗生效）
    model: Optional[str] = None  # 覆盖默认模型
    thinking_enabled: Optional[bool] = None  # 覆盖默认思考开关
    reasoning_effort: Optional[str] = None  # "high" / "max"
    api_key: Optional[str] = None  # 前端传入的 API Key，覆盖 .env 配置
    resume_text: Optional[str] = None  # 上传的简历文本
    code_context: Optional[str] = None  # 上传的代码文本（仅面试官模式使用）
    candidate_level: Optional[str] = None  # "intern" / "new_grad" / "experienced"
    interview_round: Optional[str] = None  # "first" / "second" / "hr"
    # 面试计划参数（用于时间预算感知）
    interview_duration_minutes: int = 30  # 面试总时长
    interview_question_count: int = 0  # 计划题目数量
    interview_coding_min: int = 0  # 编程题预留时间


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
    jd_id: Optional[str] = None  # 指定使用某份 JD（为空则使用全部 JD）
    resume_text: Optional[str] = None
    code_context: Optional[str] = None
    model: Optional[str] = None
    candidate_level: Optional[str] = None  # "intern" / "new_grad" / "experienced"
    interview_round: Optional[str] = None  # "first" / "second" / "hr"


class InterviewStopRequest(BaseModel):
    pass


class InterviewStopResponse(BaseModel):
    message: str


class QARecord(BaseModel):
    """单条问答记录"""
    question: str        # AI 面试官的提问
    answer: str          # 候选人的回答
    answer_chars: int = 0  # 回答字数


class ReportRequest(BaseModel):
    messages: list[Message]
    mode: str
    api_key: Optional[str] = None  # 前端传入的 API Key
    candidate_level: Optional[str] = None
    interview_round: Optional[str] = None
    qa_records: list[QARecord] = []  # 结构化问答记录


class ReportResponse(BaseModel):
    report: str


class InterviewPlanRequest(BaseModel):
    mode: str
    duration_minutes: int = Field(30, ge=5, le=120, description="面试时长（分钟），默认30分钟")
    answer_length: str = Field("medium", pattern="^(short|medium|long)$", description="回答长度：short(简短)/medium(适中)/long(详细)")
    candidate_level: Optional[str] = None  # "intern" / "new_grad" / "experienced"
    interview_round: Optional[str] = None  # "first" / "second" / "hr"
    coding_enabled: bool = False  # 是否启用编程题
    elapsed_minutes: float = 0.0  # 已用时间（用于动态重新规划）
    answered_questions: int = 0   # 已答题数（用于动态重新规划）


class InterviewPlanResponse(BaseModel):
    question_count: int
    duration_minutes: int
    avg_time_per_question: float
    description: str
    breakdown: dict  # {"自我介绍": 3, "技术问答": 24, "编程题": 0, "反问环节": 3}
    coding_reserved_min: int = 0  # 为编程题保留的时间（分钟）
    current_phase: str = ""  # 当前应处于的阶段：intro/tech_qa/coding/reverse
    remaining_questions: int = 0  # 剩余应答题数


# ============ 上传相关 ============

class UploadResponse(BaseModel):
    filename: str
    text: str
    type: str


class ProjectUploadResponse(BaseModel):
    filename: str
    file_count: int
    structure: dict  # {"source": [...], "config": [...], "document": [...], "build": [...], "test": [...], "other": [...]}
    total_text: str
    tech_stack: list[str]
    type: str = "project"


class UploadRecord(BaseModel):
    id: str
    filename: str
    type: str  # "resume" / "code" / "project"
    text: str
    preview: str
    file_count: int = 1
    tech_stack: list[str] = []
    created_at: str


class UploadListResponse(BaseModel):
    uploads: list[UploadRecord]


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
    position_type: str = "未知"  # "技术岗" / "非技术岗" / "未知"
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
