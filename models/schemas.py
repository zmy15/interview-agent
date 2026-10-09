"""数据模型定义"""

from pydantic import BaseModel, Field
from typing import Optional


# ============ 候选人与面试配置常量 ============

CANDIDATE_LEVELS = ("intern", "new_grad", "experienced")
INTERVIEW_ROUNDS = ("first", "second", "hr")
QUESTION_BANK_MODES = ("strict", "mixed", "adaptive")


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
    reasoning_effort: Optional[str] = None  # "low" / "high" / "max"
    api_key: Optional[str] = None  # 前端传入的 API Key，覆盖 .env 配置
    resume_text: Optional[str] = None  # 上传的简历文本
    code_context: Optional[str] = None  # 上传的代码文本（仅面试官模式使用）
    candidate_level: Optional[str] = None  # "intern" / "new_grad" / "experienced"
    interview_round: Optional[str] = None  # "first" / "second" / "hr"
    # 面试计划参数（用于时间预算感知）
    interview_duration_minutes: int = 30  # 面试总时长
    interview_question_count: int = 0  # 计划题目数量
    interview_coding_min: int = 0  # 编程题预留时间
    prompt_notes: Optional[str] = None  # 前端 PromptEditor 补充说明，追加到 system prompt 末尾
    question_bank_ids: Optional[list[str]] = None  # 从题库中选定的题目ID列表（AI将从中出题）
    question_bank_mode: Optional[str] = "mixed"  # 题库使用模式: strict(完全按题库) / mixed(部分题库) / adaptive(AI可改编)


class ChatResponse(BaseModel):
    content: str


# ============ 模型相关 ============

class ModelInfo(BaseModel):
    id: str
    name: str
    description: str
    supports_thinking: bool
    # 是否支持图片输入（来自官方 /models 的 input_modalities 含 "image"）
    supports_vision: bool = False


class ModelsResponse(BaseModel):
    models: list[ModelInfo]
    # 模型列表来源：remote（官方 /models 接口）/ fallback（本地 AVAILABLE_MODELS 配置）
    source: str = "remote"


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
    prompt_notes: Optional[str] = None  # 前端 PromptEditor 补充说明


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


# ============ 截图识别 ============

class MonitorItem(BaseModel):
    """截图目标显示器（本项目固定为主显示器）"""
    id: str            # "primary"
    name: str          # 展示名，如「主显示器（2560×1440）」
    x: int
    y: int
    width: int
    height: int


class ScreenshotInfoResponse(BaseModel):
    """截图能力与显示器信息"""
    available: bool                  # 截图功能是否可用
    error: Optional[str] = None      # 不可用时的原因
    monitors: list[MonitorItem] = []
    # 当前生效的视觉模型（没选模型时由后端按账号可用模型挑选，可能为空）
    vision_model: Optional[str] = None
    # 界面当前选中的模型；若它不支持图片，vision_supported=False
    selected_model: Optional[str] = None
    vision_supported: bool = True    # 选中的模型是否支持图片输入
    vision_models: list[str] = []    # 账号下支持图片输入的模型，供前端提示


class CaptureRequest(BaseModel):
    """主显示器截图并识别"""
    include_cursor: bool = False     # 是否把鼠标光标画进截图
    prompt: Optional[str] = None     # 自定义提问，为空则用 prompts/screenshot.txt
    model: Optional[str] = None      # 覆盖视觉模型（界面选中的模型）
    api_key: Optional[str] = None    # 前端传入的 Key，覆盖 .env
    save: Optional[bool] = None      # 是否保存到磁盘，覆盖 settings.SCREENSHOT_SAVE
    # 思考模式与推理强度：与界面上的模型/思考开关保持一致
    thinking_enabled: Optional[bool] = None
    reasoning_effort: Optional[str] = None  # "low" / "high" / "max"


class CaptureResponse(BaseModel):
    """截图识别结果"""
    answer: str                      # 模型回答（Markdown）
    model: str                       # 实际使用的模型
    thinking_enabled: bool = False   # 实际使用的思考模式
    monitor: str = "primary"         # 截取目标（固定主显示器）
    width: int                       # 捕获到的原始尺寸
    height: int
    image_bytes: int                 # 编码后大小（PNG 字节数）
    image_path: Optional[str] = None # 保存路径（未保存则为空）
    elapsed_ms: int                  # 端到端耗时
    captured_at: str                 # ISO 时间戳
