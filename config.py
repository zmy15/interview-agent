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

    # CORS 允许的前端来源（逗号分隔），生产环境应指定具体域名
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173")

    # FAISS 索引完整性校验（生产环境必须开启）
    FAISS_VERIFY_INTEGRITY: bool = os.getenv("FAISS_VERIFY_INTEGRITY", "true").lower() == "true"

    # 上下文窗口管理（DeepSeek V4 支持 1M tokens，默认 800K 留安全余量）
    MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "800000"))
    SYSTEM_RESERVED_TOKENS: int = int(os.getenv("SYSTEM_RESERVED_TOKENS", "8000"))

    # 日志等级: DEBUG / INFO / WARNING / ERROR
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # RAG 检索增强开关（关闭后对话不再注入知识库上下文）
    RAG_ENABLED: bool = os.getenv("RAG_ENABLED", "true").lower() == "true"


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
