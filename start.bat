@echo off
chcp 65001 >nul
title Interview Agent 平台 — 一键启动

echo ========================================
echo   Interview Agent — AI 模拟面试平台
echo ========================================
echo.

:: ========== 检查 Python ==========
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

:: ========== 检查 Node.js ==========
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Node.js，请先安装 Node.js 18+
    pause
    exit /b 1
)

:: ========== 检测虚拟环境 ==========
set VENV_PYTHON=python
if exist ".venv\Scripts\python.exe" (
    set VENV_PYTHON=.venv\Scripts\python.exe
    echo [提示] 使用虚拟环境: .venv
) else (
    echo [提示] 未检测到虚拟环境，使用系统 Python
)

:: ========== 检查 .env 文件 ==========
if not exist ".env" (
    echo [提示] 未找到 .env 文件，正在从 .env.example 复制...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [提示] 已创建 .env，请编辑填入你的 DEEPSEEK_API_KEY 和 JWT_SECRET
    ) else (
        echo [警告] .env.example 也不存在，请手动创建 .env 文件
    )
)

:: ========== 安装 Python 依赖 ==========
echo [1/4] 检查 Python 依赖...
REM 删除旧的标记文件以强制重新检查（平台化新增了依赖）
if exist ".deps_installed" del ".deps_installed" >nul 2>&1
if not exist ".deps_installed" (
    echo 正在安装 Python 依赖（含平台化新增：SQLAlchemy / JWT / bcrypt）...
    %VENV_PYTHON% -m pip install -r requirements.txt -q
    if %errorlevel% neq 0 (
        echo [错误] Python 依赖安装失败，请检查网络连接
        pause
        exit /b 1
    )
    type nul > .deps_installed
    echo Python 依赖安装完成 √
) else (
    echo Python 依赖已就绪 √
)

:: ========== 安装前端依赖 ==========
echo [2/4] 检查前端依赖...
if not exist "frontend\node_modules" (
    echo 正在安装前端依赖...
    cd frontend
    call npm install --silent
    if %errorlevel% neq 0 (
        echo [错误] 前端依赖安装失败
        cd ..
        pause
        exit /b 1
    )
    cd ..
) else (
    echo 前端依赖已就绪 √
)

:: ========== 初始化数据库 ==========
echo [3/5] 初始化数据库...
%VENV_PYTHON% -c "import asyncio; from database import init_db; asyncio.run(init_db()); print('数据库就绪')" 2>nul
if %errorlevel% neq 0 (
    echo [警告] 数据库初始化失败，应用将尝试首次请求时自动建表
) else (
    echo 数据库就绪 √
)

:: ========== 语音服务（可选，需在启动后端之前选择） ==========
echo.
echo --------------------------------------
echo   语音功能（STT识别 + TTS朗读）
echo   启用后可以：用麦克风说话 / AI语音回复
echo --------------------------------------
set /p ENABLE_VOICE="启用语音功能？[y/n]（默认 n）: "
if /i "%ENABLE_VOICE%"=="y" goto :voice_setup
if /i "%ENABLE_VOICE%"=="yes" goto :voice_setup
goto :voice_done

:voice_setup
set ENABLE_VOICE=y
set VOICE_ENABLED=true
set STT_ENABLED=true
set TTS_ENABLED=true
set STT_SERVICE_URL=http://localhost:8001
set TTS_SERVICE_URL=http://localhost:8002
REM HuggingFace 镜像（国内必须，否则模型下载超时）
if not defined HF_ENDPOINT set HF_ENDPOINT=https://hf-mirror.com

echo.
echo   选择 STT 推理设备：
echo     [1] CPU
echo     [2] GPU
set /p STT_DEVICE_CHOICE="请选择 [1/2]（默认 1）: "
if "%STT_DEVICE_CHOICE%"=="2" (
    set STT_DEVICE=cuda
    set STT_PIP_PKGS=faster-whisper ctranslate2
    echo [语音] 已选择 GPU 模式
) else (
    set STT_DEVICE=cpu
    set STT_PIP_PKGS=faster-whisper
    echo [语音] 已选择 CPU 模式
)

echo [语音] 安装语音依赖...
%VENV_PYTHON% -m pip install %STT_PIP_PKGS% -q
%VENV_PYTHON% -m pip install silero-vad numpy ffmpeg-python -q
%VENV_PYTHON% -m pip install piper-tts huggingface_hub -q
echo [语音] 依赖安装完成
:voice_done

:: ========== 启动后端 ==========
echo [4/5] 启动后端服务 (端口 8000)...
if /i "%ENABLE_VOICE%"=="y" (
    echo [语音] 后端将加载语音路由...
)
start "InterviewAgent-Backend" cmd /c "%VENV_PYTHON% -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

:: 等待后端启动（HuggingFace 模型加载需要时间）
echo 等待后端启动（首次可能需要下载模型，请耐心等待）...
timeout /t 8 /nobreak >nul

:: 验证后端是否就绪
echo 验证后端就绪...
%VENV_PYTHON% -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" 2>nul
if %errorlevel% neq 0 (
    echo 后端启动较慢，再等待 5 秒...
    timeout /t 5 /nobreak >nul
)

:: ========== 启动语音微服务（如果启用） ==========
if /i "%ENABLE_VOICE%"=="y" goto :start_voice
if /i "%ENABLE_VOICE%"=="yes" goto :start_voice
goto :skip_voice

:start_voice
echo [语音] 启动 STT 语音识别服务 (端口 8001)...
start "InterviewAgent-STT" cmd /c "%VENV_PYTHON% -m uvicorn stt_service.main:app --host 0.0.0.0 --port 8001"
echo [语音] 启动 TTS 语音合成服务 (端口 8002)...
start "InterviewAgent-TTS" cmd /c "%VENV_PYTHON% -m uvicorn tts_service.main:app --host 0.0.0.0 --port 8002"
echo [语音] 已启动（首次需下载模型 ~200MB，稍等片刻）
:skip_voice

:: ========== 启动前端 ==========
echo [5/5] 启动前端服务 (端口 5173)...
cd frontend
start "InterviewAgent-Frontend" cmd /c "npx vite --host 0.0.0.0"
cd ..

echo.
echo ========================================
if /i "%ENABLE_VOICE%"=="y" (
    echo   🎤 语音模式已启用
    echo   STT: http://localhost:8001
    echo   TTS: http://localhost:8002
)
echo   启动完成！
echo   前端地址: http://localhost:5173
echo   登录页面: http://localhost:5173/login
echo   后端地址: http://localhost:8000
echo   API 文档: http://localhost:8000/docs
echo.
echo   [提示] 首次使用请先注册账号
echo ========================================
echo.
echo 按任意键打开前端页面...
pause >nul
start http://localhost:5173
