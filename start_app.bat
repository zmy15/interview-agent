@echo off
chcp 65001 >nul
title Interview Agent — 独立窗口模式

:: ============================================================
::  Interview Agent — 独立窗口启动
::  在一个独立的应用窗口中启动（后端 + 已构建前端一体）
::  可选参数会原样传给 desktop.py，例如：
::      start_app.bat --width 1600 --height 900 --no-topmost
::      start_app.bat --port 8123 --fullscreen
:: ============================================================

setlocal

cd /d "%~dp0"

echo ========================================
echo   Interview Agent — 独立窗口模式
echo ========================================
echo.

:: ========== 检测虚拟环境 ==========
set VENV_PYTHON=python
if exist ".venv\Scripts\python.exe" (
    set VENV_PYTHON=.venv\Scripts\python.exe
    echo [提示] 使用虚拟环境: .venv
)

:: ========== 检查 .env ==========
if not exist ".env" (
    if exist ".env.example" (
        echo [提示] 未找到 .env，正在从 .env.example 复制...
        copy ".env.example" ".env" >nul
        echo [提示] 请编辑 .env 填入 DEEPSEEK_API_KEY 和 JWT_SECRET
    )
)

:: ========== 安装 Python 依赖 ==========
if not exist ".deps_installed" (
    echo [1/3] 安装 Python 依赖...
    %VENV_PYTHON% -m pip install -r requirements.txt -q
    if %errorlevel% neq 0 (
        echo [错误] Python 依赖安装失败，请检查网络连接
        pause
        exit /b 1
    )
    type nul > .deps_installed
) else (
    echo [1/3] Python 依赖已就绪 √
)

:: ========== 构建前端（首次或源码更新时） ==========
if not exist "frontend\dist\index.html" (
    echo [2/3] 未找到前端构建产物，正在构建...
    if not exist "frontend\node_modules" (
        echo       安装前端依赖（首次较慢）...
        pushd frontend
        call npm install --silent
        if %errorlevel% neq 0 (
            echo [错误] 前端依赖安装失败
            popd
            pause
            exit /b 1
        )
        popd
    )
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
) else (
    echo [2/3] 前端构建产物已就绪 √
)

:: ========== 启动独立窗口 ==========
echo [3/3] 启动独立窗口...
echo.
%VENV_PYTHON% desktop.py --capture-exclude false%*

if %errorlevel% neq 0 (
    echo.
    echo [错误] 独立窗口启动失败（退出码 %errorlevel%）
    pause
    exit /b %errorlevel%
)

endlocal