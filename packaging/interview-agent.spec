# -*- mode: python ; coding: utf-8 -*-
"""
Interview Agent — Windows 客户端打包配置（PyInstaller 6.x）

用法（在项目根目录执行，Python 3.11+ 的虚拟环境）：
    pyinstaller packaging/interview-agent.spec ^
        --distpath dist/client --workpath build/client

产物是 onedir 目录（InterviewAgent/），再由 packaging/installer.iss
（Inno Setup）制成安装包。

为什么用 onedir 而不是 onefile：
    应用体积 300MB+，onefile 每次启动都要全量解压到临时目录，
    启动慢且反复写 SSD。onedir 解压一次，安装包负责分发。

设计取舍（改动前务必先读）：
  1. 入口是 desktop.py（独立窗口模式）：进程内起 uvicorn 托管后端与
     前端静态产物，pywebview + WebView2 开原生窗口，启动后自动隐藏
     控制台。完整交互流程见 desktop.py 文档字符串。
  2. 语音微服务（STT/TTS）与 RAG 依赖（torch / faiss /
     sentence-transformers）**不打入包体** —— 它们默认关闭且合计数百
     MB。桌面端已在 app_paths.is_frozen() 分支做降级：
       * desktop.py 的 _MicroService.start 直接跳过并说明原因；
       * main.py 的语音路由注册有 try/except ImportError 兜底。
     需要完整功能请用源码方式运行（start.bat / start.sh）。
  3. 只读资源（frontend/dist、prompts/、data/question_bank.db）按
     __file__ 相对路径随包分发，冻结后解析到 sys._MEIPASS，无需改代码；
     可变数据（SQLite、日志、截图、模型缓存）在冻结模式下写入
     %LOCALAPPDATA%\\InterviewAgent（见 app_paths.py）。
  4. UPX 关闭：会误杀部分 C 扩展（cv2 / pythonnet 的 DLL）。
"""

import os
import shutil

SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_ROOT = os.path.dirname(SPEC_DIR)

block_cipher = None

# ── 内置默认 .env 的暂存 ──
# PyInstaller 的 datas 目标只能是「目录」、不支持改名，而内置默认配置
# 必须以 .env 为名（config.py 冻结分支按此名加载）。因此在打包开始时
# 先把 packaging/client.env 复制成 workpath 下的 .env，再作为数据文件
# 收进包内。workpath 由 PyInstaller 注入（--workpath，默认 build/<spec名>），
# 位于 .gitignore 覆盖的 build/ 下。
_STAGED_ENV = os.path.join(workpath, "staged", ".env")
os.makedirs(os.path.dirname(_STAGED_ENV), exist_ok=True)
shutil.copyfile(os.path.join(SPEC_DIR, "client.env"), _STAGED_ENV)

# ── 本地模块：静态分析看不到的函数内延迟 import ──
# 漏一个的典型症状：源码跑得好好的，打包后点到某个功能才
# ModuleNotFoundError。新增服务/路由时记得同步这里。
HIDDEN_IMPORTS = [
    # 项目根
    "app_paths",
    "config",
    "database",
    "main",
    # 数据模型
    "models.db_models",
    "models.schemas",
    # 路由（不含 routers.stt / routers.tts —— 语音未打包，见模块 docstring）
    "routers.analytics",
    "routers.auth",
    "routers.chat",
    "routers.interview",
    "routers.knowledge",
    "routers.position",
    "routers.question_bank",
    "routers.screenshot",
    "routers.sessions",
    "routers.system_audio",
    "routers.upload",
    # 服务层
    "services.agent_tools",
    "services.audio_transcribe",
    "services.chunker",
    "services.coding_problem",
    "services.llm_client",
    "services.model_registry",
    "services.parser",
    "services.position_store",
    "services.rag_pipeline",
    "services.screen_capture",
    "services.system_audio",
    "services.upload_store",
    "services.vector_store",
    # 工具
    "utils.auth",
    "utils.context_manager",
    "utils.position_classifier",
    "utils.prompt_loader",
    # 第三方：延迟 import / SQLAlchemy 方言 / 打包钩子需要显式点名
    "aiosqlite",                        # sqlite+aiosqlite:// 由 SQLAlchemy 动态加载
    "duckduckgo_search",                # services/agent_tools.py 函数内 import
    "fitz",                             # services/parser.py 函数内 import（PyMuPDF 旧名）
    "windows_capture",                  # screen_capture.py 条件 import（Windows 专属）
    "soundcard",                        # system_audio.py 条件 import（WASAPI 回环）
    "clr",                              # pythonnet —— pywebview 的 Windows 后端依赖
    "webview.platforms.edgechromium",   # pywebview 默认 Windows 后端（WebView2）
    "langchain_text_splitters",         # chunker 依赖（纯 Python，体积可忽略）
    # passlib 按 schemes 配置**动态加载** handler（utils/auth.py 用 bcrypt），
    # 静态分析看不到；email_validator 由 pydantic 校验 EmailStr 时懒加载，
    # 同样是漏打包重灾区（症状：注册/登录时才 ModuleNotFoundError）。
    "passlib.handlers.bcrypt",
    "email_validator",
    # python-jose 按算法动态选后端（jose.jws 内部 import backends.xxx），
    # 三个后端都是纯 Python 小模块，全带上避免挑食。
    "jose.backends.cryptography_backend",
    "jose.backends.ecdsa_backend",
    "jose.backends.rsa_backend",
    # FastAPI/Starlette 处理上传时按版本 import multipart 或 python_multipart
    "multipart",
    "python_multipart",
]

# ── 排除：默认关闭的重依赖，显著减小包体 ──
# 注意：排除后若用户在 .env 里打开对应开关，代码已有降级路径
# （跳过注册 / 明确告警），不会崩溃。
EXCLUDES = [
    # RAG 向量库链（requirements-rag.txt）
    "torch",
    "faiss",
    "sentence_transformers",
    "transformers",
    "langchain_huggingface",
    "langchain_community",
    # 语音微服务链（stt_service / tts_service）
    "faster_whisper",
    "ctranslate2",
    "av",
    "onnxruntime",
    "piper",
    "piper_tts",
    "routers.stt",
    "routers.tts",
    "stt_service",
    "tts_service",
    # 开发 / 测试期工具
    "pytest",
    "IPython",
    "tkinter",
    "matplotlib",
]

a = Analysis(
    [os.path.join(PROJECT_ROOT, "desktop.py")],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # 只读资源：目标路径即 __file__ 相对路径，冻结后解析到 _MEIPASS
        (os.path.join(PROJECT_ROOT, "frontend", "dist"), "frontend/dist"),
        (os.path.join(PROJECT_ROOT, "prompts"), "prompts"),
        (os.path.join(PROJECT_ROOT, "data", "question_bank.db"), "data"),
        # 打包内置的默认 .env（暂存后以 .env 之名收入；安装目录里的 .env 优先级更高）
        (_STAGED_ENV, "."),
    ],
    hiddenimports=HIDDEN_IMPORTS,
    hooks=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InterviewAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 会误杀部分 C 扩展（cv2 / pythonnet 的 DLL），关掉
    console=True,  # 启动期显示控制台日志，随后由 desktop.py --hide-console 自动隐藏
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="InterviewAgent",
)
