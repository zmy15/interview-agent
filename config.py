"""应用配置管理，使用 python-dotenv 加载 .env 文件"""

import os
from dotenv import load_dotenv

load_dotenv()


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

    # 上下文窗口管理（DeepSeek V4 支持 1M tokens，默认 800K 留安全余量）
    MAX_CONTEXT_TOKENS: int = int(os.getenv("MAX_CONTEXT_TOKENS", "800000"))
    SYSTEM_RESERVED_TOKENS: int = int(os.getenv("SYSTEM_RESERVED_TOKENS", "8000"))


settings = Settings()
