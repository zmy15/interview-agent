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
echo   STT 推理设备选择：
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

REM Model is decided by STT_MODEL in .env (the STT service loads it).
REM Shown here for reference only; this does not override it.
for /f "tokens=1,* delims==" %%A in ('findstr /B /C:"STT_MODEL=" ".env" 2^>nul') do set _STT_MODEL_SHOW=%%B
if not defined _STT_MODEL_SHOW set _STT_MODEL_SHOW=base (default)
echo [语音] Whisper 模型: %_STT_MODEL_SHOW%  ^(改 .env 的 STT_MODEL 可切换^)

echo [语音] 安装语音依赖...
%VENV_PYTHON% -m pip install %STT_PIP_PKGS% -q
%VENV_PYTHON% -m pip install silero-vad numpy ffmpeg-python -q
%VENV_PYTHON% -m pip install piper-tts huggingface_hub -q
REM 繁简转换（Whisper 中文输出默认繁体，转简体后再返回）
%VENV_PYTHON% -m pip install zhconv -q
echo [语音] 依赖安装完成
:voice_done

:: ========== 启动后端 ==========
echo [4/5] 启动后端服务 (端口 8000)...
if /i "%ENABLE_VOICE%"=="y" (
    echo [语音] 后端将加载语音路由...
)
call :check_port 8000 backend
if %errorlevel% neq 0 (
    echo [ERROR] Backend not started. Free port 8000 and re-run this script.
    echo         If an instance is already running, just use it.
    pause
    exit /b 1
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
set STT_STARTED=n
set TTS_STARTED=n

call :check_port 8001 STT
if %errorlevel% neq 0 goto :voice_stt_skip
echo [语音] 启动 STT 语音识别服务 (端口 8001)...
start "InterviewAgent-STT" cmd /c "%VENV_PYTHON% -m uvicorn stt_service.main:app --host 0.0.0.0 --port 8001"
set STT_STARTED=y
:voice_stt_skip

call :check_port 8002 TTS
if %errorlevel% neq 0 goto :voice_tts_skip
echo [语音] 启动 TTS 语音合成服务 (端口 8002)...
start "InterviewAgent-TTS" cmd /c "%VENV_PYTHON% -m uvicorn tts_service.main:app --host 0.0.0.0 --port 8002"
set TTS_STARTED=y
:voice_tts_skip

:: 用 goto 而非 if(...) 块：块内 set 的变量在块外读取时，
:: cmd 已在解析阶段完成 %VAR% 展开，会读到旧值。
if /i "%STT_STARTED%%TTS_STARTED%"=="yy" goto :voice_all_ok
echo [语音] 部分服务未启动（端口被占用，详见上方警告）
goto :skip_voice
:voice_all_ok
echo [语音] 已启动（首次需下载模型 ~200MB，稍等片刻）
:skip_voice

:: ========== 启动前端 ==========
echo [5/5] 启动前端服务 (端口 5173)...
set FRONTEND_STARTED=n
call :check_port 5173 frontend
if %errorlevel% neq 0 goto :frontend_skip
cd frontend
start "InterviewAgent-Frontend" cmd /c "npx vite --host 0.0.0.0"
cd ..
set FRONTEND_STARTED=y
:frontend_skip

echo.
echo ========================================
:: NOTE: keep the parenthesised if/else bodies ASCII-only.
:: Non-ASCII inside ( ) blocks breaks cmd's parser under chcp 65001.
if /i "%ENABLE_VOICE%"=="y" (
    echo   [Voice] enabled
    if /i "%STT_STARTED%"=="y" (echo   STT: http://localhost:8001) else (echo   STT: NOT started - port 8001 in use)
    if /i "%TTS_STARTED%"=="y" (echo   TTS: http://localhost:8002) else (echo   TTS: NOT started - port 8002 in use)
)
echo   启动完成！
if /i "%FRONTEND_STARTED%"=="y" (
    echo   Frontend: http://localhost:5173
    echo   Login:    http://localhost:5173/login
) else (
    echo   Frontend: NOT started - port 5173 in use; reuse the running one
)
echo   后端地址: http://localhost:8000
echo   API 文档: http://localhost:8000/docs
echo.
echo   [提示] 首次使用请先注册账号
echo ========================================
echo.
echo 按任意键打开前端页面...
pause >nul
start http://localhost:5173
goto :eof


:: ============================================================
::  端口预检查（子程序）
::
::  为什么需要：用 start 启动的服务若端口被占用，uvicorn 会立刻
::  报「[Errno 10048] ... 只允许使用一次」然后退出。由于是在
::  新窗口里跑的，那个窗口一闪而过，用户只会看到「少了一个弹窗」，
::  完全不知道原因（曾因此误以为功能坏了）。
::
::  用法：call :check_port 8001 STT 语音识别
::        返回 errorlevel=0 表示端口空闲，=1 表示被占用
:: ============================================================
:check_port
:: Usage: call :check_port <port> <name> <desc>
:: Returns errorlevel 0 = free, 1 = in use.
::
:: Why: a service started via `start` runs in its own window. If the
:: port is taken, uvicorn exits immediately and that window flashes
:: away -- the user only sees "one window is missing" and has no idea
:: why. This pre-check reports the conflict and the owning PID instead.
::
:: NOTE: keep this block ASCII-only. Non-ASCII text inside for/f
:: blocks breaks cmd's parser under chcp 65001.
set "_CP_PORT=%~1"
set "_CP_NAME=%~2"
set "_CP_DESC=%~3"

netstat -ano -p TCP 2>nul | findstr /R /C:":%_CP_PORT% .*LISTENING" >nul 2>&1
if %errorlevel% neq 0 (
    exit /b 0
)

set "_CP_PID="
for /f "tokens=5" %%P in ('netstat -ano -p TCP 2^>nul ^| findstr /R /C:":%_CP_PORT% .*LISTENING"') do (
    if not defined _CP_PID set "_CP_PID=%%P"
)

echo.
echo [WARN] Port %_CP_PORT% is already in use - cannot start %_CP_NAME%.
if defined _CP_PID (
    echo        Owning PID = %_CP_PID%
    echo        Inspect / stop it with:
    echo            tasklist /FI "PID eq %_CP_PID%"
    echo            taskkill /PID %_CP_PID% /F
)
echo        This service will be skipped. Free the port and re-run.
echo.
exit /b 1
