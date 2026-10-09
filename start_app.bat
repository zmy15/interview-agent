@echo off
chcp 65001 >nul
title Interview Agent — 独立窗口模式

setlocal

cd /d "%~dp0"

echo ========================================
echo   Interview Agent — 独立窗口模式
echo ========================================
echo.

set VENV_PYTHON=python
if exist ".venv\Scripts\python.exe" (
    set VENV_PYTHON=.venv\Scripts\python.exe
    echo [提示] 使用虚拟环境: .venv
)

if not exist ".env" (
    if exist ".env.example" (
        echo [提示] 未找到 .env，正在从 .env.example 复制...
        copy ".env.example" ".env" >nul
        echo [提示] 请编辑 .env 填入 DEEPSEEK_API_KEY 和 JWT_SECRET
    )
)

echo [1/4] 检查 Python 依赖...
%VENV_PYTHON% -m pip install -r requirements.txt -q
if %errorlevel% neq 0 (
    echo [错误] Python 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)
echo       Python 依赖已就绪 √


echo [2/4] 检查前端构建产物...
set NEED_BUILD=n
if not exist "frontend\dist\index.html" (
    set NEED_BUILD=y
) else (
    for /f %%T in ('powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\frontend_stale.ps1" 2^>nul') do set SRC_NEWER=%%T
)


if /i "%SRC_NEWER%"=="newer" set NEED_BUILD=y

if /i "%NEED_BUILD%"=="y" goto :do_build
echo       前端构建产物已就绪 √
goto :after_build

:do_build
echo       前端源码有更新或产物缺失，正在构建...
if not exist "frontend\node_modules" call :install_frontend_deps
pushd frontend
call npm run build
if %errorlevel% neq 0 (
    echo [错误] 前端构建失败
    popd
    pause
    exit /b 1
)
popd
echo       前端构建完成 √

:after_build


echo [3/4] 初始化数据库...
%VENV_PYTHON% -c "import asyncio; from database import init_db; asyncio.run(init_db()); print('数据库就绪')" 2>nul
if %errorlevel% neq 0 goto :db_failed
echo       数据库就绪 √
goto :after_db

:db_failed
echo [警告] 数据库初始化失败，应用将尝试首次请求时自动建表

:after_db


set VOICE_ON=n
for /f "tokens=1,* delims==" %%A in ('findstr /B /C:"VOICE_ENABLED=" /C:"STT_ENABLED=" /C:"TTS_ENABLED=" ".env" 2^>nul') do call :check_true %%B
if /i "%VOICE_ON%"=="y" goto :voice_deps
echo       语音未启用（.env 中三个开关均为 false），跳过
goto :after_voice

:voice_deps
echo       语音已启用，检查语音依赖...
set STT_PIP_PKGS=faster-whisper
for /f "tokens=1,* delims==" %%A in ('findstr /B /C:"STT_DEVICE=" ".env" 2^>nul') do call :check_cuda %%B
%VENV_PYTHON% -m pip install %STT_PIP_PKGS% -q
%VENV_PYTHON% -m pip install silero-vad numpy ffmpeg-python -q
%VENV_PYTHON% -m pip install piper-tts huggingface_hub -q
REM 繁简转换（Whisper 中文输出默认繁体，转简体后再返回）
%VENV_PYTHON% -m pip install zhconv -q
echo       语音依赖已就绪 √
goto :after_voice

:after_voice


echo [4/4] 启动独立窗口...
echo.
echo   启动后控制台会自动隐藏，日志见 logs\desktop.log
echo.
%VENV_PYTHON% desktop.py %*

if %errorlevel% neq 0 goto :launch_failed

endlocal
goto :eof

:launch_failed
echo.
echo [错误] 独立窗口启动失败（退出码 %errorlevel%）
echo        详细日志: logs\desktop.log
pause
exit /b %errorlevel%


:check_true
echo %~1 | findstr /I /C:"true" >nul
if %errorlevel% equ 0 set VOICE_ON=y
goto :eof


:check_cuda
echo %~1 | findstr /I /C:"cuda" >nul
if %errorlevel% equ 0 set STT_PIP_PKGS=faster-whisper ctranslate2
goto :eof


:install_frontend_deps
echo       安装前端依赖（首次较慢）...
pushd frontend
call npm install --silent
if %errorlevel% neq 0 (
    popd
    echo [错误] 前端依赖安装失败
    pause
    exit /b 1
)
popd
goto :eof