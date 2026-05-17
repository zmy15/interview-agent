@echo off
chcp 65001 >nul
title 面试 Agent — 一键启动

echo ========================================
echo   面试 Agent — AI 模拟面试助手
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

:: ========== 检查 .env 文件 ==========
if not exist ".env" (
    echo [提示] 未找到 .env 文件，正在从 .env.example 复制...
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [提示] 已创建 .env，请编辑填入你的 DEEPSEEK_API_KEY
    ) else (
        echo [警告] .env.example 也不存在，请手动创建 .env 文件
    )
)

:: ========== 安装 Python 依赖 ==========
echo [1/4] 检查 Python 依赖...
if not exist ".deps_installed" (
    echo 正在安装 Python 依赖...
    pip install -r requirements.txt -q
    if %errorlevel% neq 0 (
        echo [错误] Python 依赖安装失败
        pause
        exit /b 1
    )
    type nul > .deps_installed
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

:: ========== 启动后端 ==========
echo [3/4] 启动后端服务 (端口 8000)...
start "InterviewAgent-Backend" cmd /c "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

:: 等待后端启动
echo 等待后端启动...
timeout /t 3 /nobreak >nul

:: ========== 启动前端 ==========
echo [4/4] 启动前端服务 (端口 5173)...
cd frontend
start "InterviewAgent-Frontend" cmd /c "npx vite --host 0.0.0.0"
cd ..

echo.
echo ========================================
echo   启动完成！
echo   前端地址: http://localhost:5173
echo   后端地址: http://localhost:8000
echo   API 文档: http://localhost:8000/docs
echo ========================================
echo.
echo 按任意键打开前端页面...
pause >nul
start http://localhost:5173
