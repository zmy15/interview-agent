"""应用配置管理，使用 python-dotenv 加载 .env 文件"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── 关键：在导入任何 HF 相关库之前，将镜像端点注入 os.environ ──
# huggingface_hub / sentence-transformers 在首次 import 时读取 HF_ENDPOINT，
# 必须在此之前设置，否则会直连 huggingface.co（国内超时）。
_hf_endpoint = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
os.environ["HF_ENDPOINT"] = _hf_endpoint

_hf_home = os.getenv("HF_HOME", os.path.join(os.path.dirname(__file__), "hf_cache"))
os.environ["HF_HOME"] = _hf_home
os.makedirs(_hf_home, exist_ok=True)


class Settings:
    """配置单例"""

    # DeepSeek
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    DEEPSEEK_THINKING_ENABLED: bool = os.getenv("DEEPSEEK_THINKING_ENABLED", "true").lower() == "true"
    # 思考强度：low（更快更省）/ high（官方默认）/ max（最充分）
    # 界面上的思考强度选择优先于本配置。
    DEEPSEEK_REASONING_EFFORT: str = os.getenv("DEEPSEEK_REASONING_EFFORT", "high")

    # 可用模型
    AVAILABLE_MODELS: str = os.getenv("AVAILABLE_MODELS", "deepseek-v4-pro,deepseek-v4-flash")

    # Embedding
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    # HuggingFace 镜像（国内用户设置此变量可解决无法访问 huggingface.co 的问题）
    # 推荐镜像: https://hf-mirror.com
    HF_ENDPOINT: str = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
    # 本地缓存目录，避免重复下载
    HF_HOME: str = os.getenv("HF_HOME", os.path.join(os.path.dirname(__file__), "hf_cache"))

    # FAISS 向量存储（兼容旧 CHROMA_PERSIST_PATH 配置名）
    CHROMA_PERSIST_PATH: str = os.getenv("CHROMA_PERSIST_PATH", "./chroma_data")
    VECTOR_SEARCH_TOP_K: int = int(os.getenv("VECTOR_SEARCH_TOP_K", "3"))

    # ── 独立窗口 / 服务监听配置 ──
    # 独立窗口模式（desktop.py）默认绑定的地址与端口
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    # 是否以独立窗口模式启动（由 desktop.py 设置，也可在 .env 中固定开启）
    DESKTOP_MODE: bool = os.getenv("DESKTOP_MODE", "false").lower() == "true"
    # 独立窗口默认尺寸
    DESKTOP_WIDTH: int = int(os.getenv("DESKTOP_WIDTH", "1280"))
    DESKTOP_HEIGHT: int = int(os.getenv("DESKTOP_HEIGHT", "800"))
    # 窗口置顶
    DESKTOP_TOPMOST: bool = os.getenv("DESKTOP_TOPMOST", "true").lower() == "true"
    # 尝试从屏幕捕获中排除窗口（截屏/录屏不可见）
    DESKTOP_CAPTURE_EXCLUDE: bool = os.getenv("DESKTOP_CAPTURE_EXCLUDE", "true").lower() == "true"
    # 隐藏任务栏图标
    DESKTOP_HIDE_TASKBAR: bool = os.getenv("DESKTOP_HIDE_TASKBAR", "false").lower() == "true"
    # 指定浏览器可执行文件路径（留空则自动查找 Edge / Chrome）
    DESKTOP_BROWSER: str = os.getenv("DESKTOP_BROWSER", "")

    # CORS 允许的前端来源（逗号分隔），生产环境应指定具体域名
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173")

    # FAISS 索引完整性校验（生产环境必须开启）
    FAISS_VERIFY_INTEGRITY: bool = os.getenv("FAISS_VERIFY_INTEGRITY", "true").lower() == "true"

    # 上下文窗口管理（DeepSeek V4 支持 1M tokens）
    MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "1000000"))
    SYSTEM_RESERVED_TOKENS: int = int(os.getenv("SYSTEM_RESERVED_TOKENS", "16000"))

    # 日志等级: DEBUG / INFO / WARNING / ERROR
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # RAG 检索增强开关（关闭后对话不再注入知识库上下文）
    RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "true").lower() == "true"

    # ── 数据库配置（平台化） ──
    # DB_TYPE: sqlite（开发） / postgresql（生产）
    DB_TYPE: str = os.getenv("DB_TYPE", "sqlite")
    # 直接提供完整的 DATABASE_URL 可覆盖以下所有 DB_* 配置
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
    DB_USER: str = os.getenv("DB_USER", "interview")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "interview_platform")
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    # ── JWT 认证配置 ──
    JWT_SECRET: str = os.getenv("JWT_SECRET", "change-me-in-production-use-a-random-64-char-string")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30"))

    # ── 平台功能开关 ──
    # 是否要求认证（关闭时为单用户模式，兼容原有体验）
    AUTH_REQUIRED: bool = os.getenv("AUTH_REQUIRED", "true").lower() == "true"
    # 免费用户每日面试次数限制
    FREE_DAILY_INTERVIEW_LIMIT: int = int(os.getenv("FREE_DAILY_INTERVIEW_LIMIT", "10"))

    # ── 截图识别（services/screen_capture.py） ──
    # 视觉模型不再写死：截图默认使用界面「模型选择器」里选中的模型，
    # 后端通过官方 GET /models 的 input_modalities 判断其是否支持图片，
    # 不支持则直接返回「不支持图片输入」，不会把图片发给纯文本模型。
    #
    # SCREENSHOT_VISION_MODEL 仅作为「界面未选择任何模型」时的兜底偏好。
    # 留空则自动挑选账号下第一个支持图片输入的模型。
    SCREENSHOT_VISION_MODEL: str = os.getenv("SCREENSHOT_VISION_MODEL", "")
    SCREENSHOT_DIR: str = os.getenv("SCREENSHOT_DIR", "screenshots")
    # 上传给模型前图片的最长边（官方会把图片缩放到约 1300×1300 再计费，
    # 单图 token 上限 1024，因此本地先缩小可显著减少上传耗时）
    SCREENSHOT_MAX_IMAGE_EDGE: int = int(os.getenv("SCREENSHOT_MAX_IMAGE_EDGE", "1280"))
    # 单次回答的最大 token 数。注意：DeepSeek 思考模式默认开启，
    # 思维链与正文共享该预算，2048 容易被推理吃光导致正文被截断。
    SCREENSHOT_MAX_TOKENS: int = int(os.getenv("SCREENSHOT_MAX_TOKENS", "8192"))
    # 截图问答在界面未传思考开关时的默认值。
    # 截图答题是「照抄题干 + 给答案」，不需要长链推理；
    # 开启只会占用输出预算并拖慢响应，故默认关闭。
    # （界面上的思考开关优先于本配置）
    SCREENSHOT_THINKING_ENABLED: bool = (
        os.getenv("SCREENSHOT_THINKING_ENABLED", "false").lower() == "true"
    )
    # 是否保存每次截图到磁盘
    SCREENSHOT_SAVE: bool = os.getenv("SCREENSHOT_SAVE", "true").lower() == "true"
    # 截图接口总开关（关闭后前端页面提示功能未启用）
    SCREENSHOT_ENABLED: bool = os.getenv("SCREENSHOT_ENABLED", "true").lower() == "true"

    # ── 语音功能开关（默认全部关闭，需主动启用） ──
    # 语音总开关
    VOICE_ENABLED: bool = os.getenv("VOICE_ENABLED", "false").lower() == "true"
    # STT 语音识别独立开关
    STT_ENABLED: bool = os.getenv("STT_ENABLED", "false").lower() == "true"
    # TTS 语音合成独立开关
    TTS_ENABLED: bool = os.getenv("TTS_ENABLED", "false").lower() == "true"

    # ── STT 语音识别配置 ──
    # whisper 模型大小: tiny / base / small / medium
    STT_MODEL: str = os.getenv("STT_MODEL", "base")
    # 推理设备: cpu / cuda
    STT_DEVICE: str = os.getenv("STT_DEVICE", "cpu")
    # 量化类型: int8 / float16 / int8_float16
    STT_COMPUTE_TYPE: str = os.getenv("STT_COMPUTE_TYPE", "int8")
    # STT 微服务地址（Docker 内部网络）
    STT_SERVICE_URL: str = os.getenv("STT_SERVICE_URL", "http://stt:8000")
    # STT WebSocket 地址
    STT_WS_URL: str = os.getenv("STT_WS_URL", "ws://stt:8000/stream")
    # Dockerfile 选择: Dockerfile (CPU) / Dockerfile.gpu (GPU)
    STT_DOCKERFILE: str = os.getenv("STT_DOCKERFILE", "Dockerfile")
    # VAD 静默超时（秒）
    VAD_SILENCE_TIMEOUT: float = float(os.getenv("VAD_SILENCE_TIMEOUT", "1.0"))

    # ── TTS 语音合成配置 ──
    # Piper 中文语音模型名
    TTS_VOICE: str = os.getenv("TTS_VOICE", "zh_CN-huayan-medium")
    # 语速: 0.5-2.0（1.0 正常）
    TTS_SPEED: float = float(os.getenv("TTS_SPEED", "1.0"))
    # TTS 微服务地址（Docker 内部网络）
    TTS_SERVICE_URL: str = os.getenv("TTS_SERVICE_URL", "http://tts:8000")
    # TTS WebSocket 地址
    TTS_WS_URL: str = os.getenv("TTS_WS_URL", "ws://tts:8000/stream")


settings = Settings()

# ── 启动时日志：RAG 依赖状态 ──
import logging
_logger = logging.getLogger(__name__)

# 延迟检查向量存储依赖（避免在导入阶段触发重依赖加载）
_rag_deps_available = False
try:
    import torch  # noqa: F401
    import faiss  # noqa: F401
    from sentence_transformers import SentenceTransformer  # noqa: F401
    _rag_deps_available = True
except (ImportError, OSError):
    pass

if settings.RAG_ENABLED and not _rag_deps_available:
    _logger.warning(
        "⚠ RAG_ENABLED=true 但向量知识库依赖未安装（torch / sentence-transformers / faiss）。"
        " 请安装 requirements-rag.txt 或在 .env 中设置 RAG_ENABLED=false。"
        " 应用将继续运行，但知识库上传和检索功能不可用。"
    )
elif settings.RAG_ENABLED and _rag_deps_available:
    _logger.info("✅ RAG 检索增强已开启，向量知识库可用")
elif not settings.RAG_ENABLED:
    _logger.info("ℹ RAG 检索增强已关闭（RAG_ENABLED=false），对话将不注入知识库上下文")
