#!/usr/bin/env bash
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Interview Agent — AI 模拟面试平台${NC}"
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

# ========== 检测虚拟环境 ==========
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
    PIP=".venv/bin/pip"
    echo -e "${GREEN}[提示]${NC} 使用虚拟环境: .venv"
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
echo -e "${GREEN}[1/5]${NC} 检查 Python 依赖..."
# 删除旧标记以强制重新检查（平台化新增了依赖）
rm -f .deps_installed
if [ ! -f ".deps_installed" ]; then
    echo "正在安装 Python 依赖（含平台化新增：SQLAlchemy / JWT / bcrypt）..."
    $PIP install -r requirements.txt -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}[错误]${NC} Python 依赖安装失败，请检查网络连接"
        exit 1
    fi
    touch .deps_installed
    echo -e "Python 依赖安装完成 ${GREEN}√${NC}"
else
    echo -e "Python 依赖已就绪 ${GREEN}√${NC}"
fi

# ========== 安装前端依赖 ==========
echo -e "${GREEN}[2/5]${NC} 检查前端依赖..."
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

# ========== 初始化数据库 ==========
echo -e "${GREEN}[3/5]${NC} 初始化数据库..."
$PYTHON -c "import asyncio; from database import init_db; asyncio.run(init_db()); print('数据库就绪')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}[警告]${NC} 数据库初始化失败，应用将尝试首次请求时自动建表"
else
    echo -e "数据库就绪 ${GREEN}√${NC}"
fi

# ========== 语音服务（可选，需在启动后端之前选择） ==========
echo ""
echo -e "${CYAN}-------------------------------------${NC}"
echo -e "${CYAN}  语音功能（STT识别 + TTS朗读）${NC}"
echo -e "${CYAN}  启用后可以：用麦克风说话 / AI语音回复${NC}"
echo -e "${CYAN}-------------------------------------${NC}"
read -p "启用语音功能？[y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    export VOICE_ENABLED=true
    export STT_ENABLED=true
    export TTS_ENABLED=true
    export STT_SERVICE_URL=http://localhost:8001
    export TTS_SERVICE_URL=http://localhost:8002

    echo ""
    echo "  选择 STT 推理设备："
    echo "    [1] CPU（推荐，无需显卡）"
    echo "    [2] GPU（需要 NVIDIA 显卡 + CUDA 12.x）"
    read -p "请选择 [1/2]（默认 1）: " -n 1 -r
    echo
    if [[ $REPLY == "2" ]]; then
        export STT_DEVICE=cuda
        echo -e "${GREEN}[语音]${NC} 已选择 GPU 模式"
        $PIP install faster-whisper ctranslate2 -q 2>/dev/null
    else
        export STT_DEVICE=cpu
        echo -e "${GREEN}[语音]${NC} 已选择 CPU 模式"
        $PIP install faster-whisper -q 2>/dev/null
    fi

    echo -e "${GREEN}[语音]${NC} 安装语音依赖..."
    $PIP install silero-vad numpy ffmpeg-python piper-tts -q 2>/dev/null
    echo -e "${GREEN}[语音]${NC} 依赖安装完成"
    VOICE_ON=1
else
    VOICE_ON=0
fi

# ========== 启动后端 ==========
echo -e "${GREEN}[4/5]${NC} 启动后端服务 (端口 8000)..."
if [ "$VOICE_ON" = "1" ]; then
    echo -e "${GREEN}[语音]${NC} 后端将加载语音路由..."
fi
$PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo -e "后端 PID: ${BACKEND_PID}"

# 等待后端启动
sleep 3

# ========== 启动语音微服务（如果启用） ==========
if [ "$VOICE_ON" = "1" ]; then
    echo -e "${GREEN}[语音]${NC} 启动 STT 语音识别 (端口 8001)..."
    $PYTHON -m uvicorn stt_service.main:app --host 0.0.0.0 --port 8001 &
    STT_PID=$!
    echo -e "${GREEN}[语音]${NC} 启动 TTS 语音合成 (端口 8002)..."
    $PYTHON -m uvicorn tts_service.main:app --host 0.0.0.0 --port 8002 &
    TTS_PID=$!
    echo -e "${GREEN}[语音]${NC} 已启动（首次需下载模型 ~200MB，稍等片刻）"
fi

# ========== 启动前端 ==========
echo -e "${GREEN}[5/5]${NC} 启动前端服务 (端口 5173)..."
cd frontend
npx vite --host 0.0.0.0 &
FRONTEND_PID=$!
cd ..

echo ""
echo -e "${CYAN}========================================${NC}"
if [ "$VOICE_ON" = "1" ]; then
    echo -e "  🎤 ${GREEN}语音模式已启用${NC}"
    echo -e "  STT: ${GREEN}http://localhost:8001${NC}"
    echo -e "  TTS: ${GREEN}http://localhost:8002${NC}"
fi
echo -e "${CYAN}  启动完成！${NC}"
echo -e "  前端地址: ${GREEN}http://localhost:5173${NC}"
echo -e "  登录页面: ${GREEN}http://localhost:5173/login${NC}"
echo -e "  后端地址: ${GREEN}http://localhost:8000${NC}"
echo -e "  API 文档: ${GREEN}http://localhost:8000/docs${NC}"
echo ""
echo -e "  ${YELLOW}[提示]${NC} 首次使用请先注册账号"
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
    [ -n "$STT_PID" ] && kill $STT_PID 2>/dev/null
    [ -n "$TTS_PID" ] && kill $TTS_PID 2>/dev/null
    echo -e "${GREEN}服务已停止${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 等待子进程
wait
