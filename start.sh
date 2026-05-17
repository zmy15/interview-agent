#!/usr/bin/env bash
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  面试 Agent — AI 模拟面试助手${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ========== 检测操作系统 ==========
OS_TYPE=$(uname -s)
echo -e "${GREEN}[信息]${NC} 检测到系统: ${OS_TYPE}"

# ========== 检查 Python ==========
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo -e "${RED}[错误]${NC} 未找到 Python，请先安装 Python 3.11+"
    exit 1
fi

# 优先使用 python3
if command -v python3 &> /dev/null; then
    PYTHON=python3
    PIP=pip3
else
    PYTHON=python
    PIP=pip
fi

# ========== 检查 Node.js ==========
if ! command -v node &> /dev/null; then
    echo -e "${RED}[错误]${NC} 未找到 Node.js，请先安装 Node.js 18+"
    exit 1
fi

# ========== 检查 .env 文件 ==========
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}[提示]${NC} 未找到 .env 文件，正在从 .env.example 复制..."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}[提示]${NC} 已创建 .env，请编辑填入你的 DEEPSEEK_API_KEY"
    else
        echo -e "${RED}[警告]${NC} .env.example 也不存在，请手动创建 .env 文件"
    fi
fi

# ========== 安装 Python 依赖 ==========
echo -e "${GREEN}[1/4]${NC} 检查 Python 依赖..."
if [ ! -f ".deps_installed" ]; then
    echo "正在安装 Python 依赖..."
    $PIP install -r requirements.txt -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}[错误]${NC} Python 依赖安装失败"
        exit 1
    fi
    touch .deps_installed
else
    echo -e "Python 依赖已就绪 ${GREEN}√${NC}"
fi

# ========== 安装前端依赖 ==========
echo -e "${GREEN}[2/4]${NC} 检查前端依赖..."
if [ ! -d "frontend/node_modules" ]; then
    echo "正在安装前端依赖..."
    cd frontend
    npm install --silent
    if [ $? -ne 0 ]; then
        echo -e "${RED}[错误]${NC} 前端依赖安装失败"
        cd ..
        exit 1
    fi
    cd ..
else
    echo -e "前端依赖已就绪 ${GREEN}√${NC}"
fi

# ========== 启动后端 ==========
echo -e "${GREEN}[3/4]${NC} 启动后端服务 (端口 8000)..."
$PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo -e "后端 PID: ${BACKEND_PID}"

# 等待后端启动
sleep 3

# ========== 启动前端 ==========
echo -e "${GREEN}[4/4]${NC} 启动前端服务 (端口 5173)..."
cd frontend
npx vite --host 0.0.0.0 &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  启动完成！${NC}"
echo -e "  前端地址: ${GREEN}http://localhost:5173${NC}"
echo -e "  后端地址: ${GREEN}http://localhost:8000${NC}"
echo -e "  API 文档: ${GREEN}http://localhost:8000/docs${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "按 ${YELLOW}Ctrl+C${NC} 停止所有服务"

# 自动打开浏览器
if command -v open &> /dev/null; then
    open http://localhost:5173 2>/dev/null &
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5173 2>/dev/null &
fi

# 捕获退出信号，清理子进程
cleanup() {
    echo ""
    echo -e "${YELLOW}正在停止服务...${NC}"
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}服务已停止${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 等待子进程
wait
