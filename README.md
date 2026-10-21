<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/TypeScript-6.0-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/DeepSeek-V4-536DFE?logo=openai&logoColor=white" alt="DeepSeek">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

<h1 align="center">🎯 Interview Agent</h1>
<p align="center"><strong>AI 模拟面试平台 — 双视角演练 · RAG 知识库 · 实时辅助</strong></p>

<p align="center">
  <a href="#-简介">简介</a> •
  <a href="#-功能特性">功能特性</a> •
  <a href="#-快速开始">快速开始</a> •
  <a href="#-配置项">配置项</a> •
  <a href="#-使用指南">使用指南</a> •
  <a href="#-api-概览">API</a> •
  <a href="#-注意事项">注意事项</a>
</p>

---

## 📖 简介

Interview Agent 是一个基于大语言模型的 **AI 模拟面试平台**。它把「准备面试」这件事拆成两个可自由切换的视角，并结合 RAG 向量知识库与联网搜索，让每一轮对话都带上岗位 JD、简历与知识库的上下文。

### 双核心场景

| 模式 | 说明 |
|------|------|
| 🎯 **你是面试官**（`interviewer`） | 你扮演面试官向 AI 求职者提问。AI 结合岗位 JD、简历、代码与知识库给出专业回答，适合练习提问技巧、快速验证候选人口径 |
| 🧑 **你是求职者**（`candidate`） | AI 扮演面试官向你提问。系统按 JD 与简历出题，支持设置时长、推算题量、追踪进度，结束后生成多维度评估报告 |

### 三大「实战辅助」能力

除模拟演练外，本项目还提供了面向**真实面试场景**的实时辅助（均基于 Windows 平台能力）：

| 能力 | 抓取对象 | 用途 |
|------|----------|------|
| 📷 **截图答题** | 屏幕画面（Windows Graphics Capture） | 一键截取主显示器，交给视觉模型提取题目并作答 |
| 🎧 **系统音频转写** | 扬声器回环（WASAPI Loopback） | 抓取会议软件 / 视频里对方说的话，实时转文字 |
| 🎤 **语音输入 / 朗读** | 麦克风（STT）与扬声器（TTS） | 按住说话转文字；AI 回复一键朗读 |

---

## ✨ 功能特性

**对话与面试**
- 🤖 双模式 AI 对话，SSE 流式输出（思维链与正文分通道推送）
- ⏱️ 面试时长推算：按「时长 + 回答长度 + 候选人级别 + 面试轮次」计算题量与环节拆分，支持**动态重规划**
- 🎓 候选人分级：实习 / 校招 / 社招，自动调整问题难度与数量
- 🔄 面试轮次：一面 / 二面 / HR 面（HR 面强制 30 分钟上限并禁用编程题）
- 🧑‍💻 编程题模式：按岗位类型从题库选题（仅求职者模式 + 技术岗生效）
- 📝 面试报告：多维度评估（技术能力 / 沟通表达 / 综合素质），支持结构化 QA 逐题评估
- 🗂️ 题库管理：自建题目、从 LeetCode 题库导入、三种使用模式（严格 / 混合 / 灵活改编）
- 💬 会话历史：完整回放历史对话，含思维链与 token 计数

**知识与检索**
- 📚 RAG 向量知识库：上传 PDF / Word / 文本 / 代码 / 项目压缩包，FAISS 向量检索增强回答
- 🌐 联网搜索：集成 DuckDuckGo，实时补充最新技术资讯
- 🗂️ 岗位管理：一个岗位可挂多份 JD，可指定对话使用哪一份

**平台与体验**
- 🔐 用户系统：JWT 认证（access + refresh），数据按用户隔离；也可一键切换到**单用户免登录模式**
- 📊 分析仪表盘：概览统计、进步趋势、薄弱项分析、多次面试对比
- 🎛️ 模型选择：模型列表从官方 `GET /models` 动态获取（不硬编码），支持思考开关与推理强度
- 🔒 安全机制：CORS 白名单、bcrypt 密码哈希、FAISS 索引 SHA-256 完整性校验
- 📐 上下文管理：tiktoken 精确计数 + 智能裁剪，适配超长上下文模型
- ⚡ 前缀缓存友好：上下文固定为「prompt → 简历 → JD →（可选 RAG）→ 每轮问答」，同一场面试里前缀逐字节不变，服务端 prefix caching 稳定命中
- 🖥️ 界面定制：7 套配色预设 + 自定义背景 / 文字色，WCAG 对比度提示
- 🪟 独立窗口模式：置顶、透明度、捕获排除、全局 F8 热键，只留一个窗口
- 🐳 多种部署：本地脚本 / Docker Compose / 单容器

> 🎤 **语音功能（STT/TTS）默认全部关闭**，需在 `.env` 中主动开启，未开启时对系统零影响。

---

## 🚀 快速开始

### 前置要求

| 项目 | 要求 |
|------|------|
| Python | 3.11+ |
| Node.js | 18+（构建前端需要；CI 使用 22） |
| DeepSeek API Key | [platform.deepseek.com](https://platform.deepseek.com/) |
| 操作系统 | Windows / macOS / Linux 均可跑核心功能；**截图答题、系统音频捕获、独立窗口为 Windows 专属** |

### 第一步：配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填入：

```bash
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
JWT_SECRET=请换成一串足够长的随机字符串
```

> **国内用户**：`.env.example` 已默认配置 HuggingFace 镜像 `HF_ENDPOINT=https://hf-mirror.com`，首次启动下载 Embedding 模型（约 90MB）无需额外操作。
>
> 也可以完全不填 `DEEPSEEK_API_KEY` —— 前端支持在界面上直接填写 API Key（仅存本地浏览器），此时界面的 Key 优先级更高。

### 第二步：选择一种启动方式

| 方式 | 命令 | 适用平台 | 说明 |
|------|------|----------|------|
| 🪟 **独立窗口**（推荐 Windows） | `start_app.bat` 或 `python desktop.py` | Windows | 后端 + 前端 + 语音微服务装进一个应用窗口 |
| 📜 **本地脚本**（开发推荐） | `start.bat` / `./start.sh` | 全平台 | 后端 `:8000` + 前端 `:5173`（热更新） |
| 🐳 **Docker Compose** | `docker-compose up -d` | 全平台 | Nginx `:80` → 后端 `:8000` |
| 📦 **单容器** | `docker run` | 全平台 | 后端直接托管前端构建产物 |

#### 方式一：本地脚本（开发推荐）

**Windows** — 双击 `start.bat`

**macOS / Linux**

```bash
chmod +x start.sh
./start.sh
```

脚本会自动完成：检查 Python / Node → 创建 `.env` → 安装依赖 → 初始化数据库 → （可选）配置语音 → 启动后端与前端 → 打开浏览器。启动后访问前端 <http://localhost:5173>，API 文档 <http://localhost:8000/docs>。

启动过程中会询问是否启用语音功能（默认 `n`）；选 `y` 后会继续询问 STT 推理设备（CPU / GPU）。

#### 方式二：独立窗口模式（Windows）

```bash
python desktop.py
# 或经由 main.py 启动（参数自动转发）
python main.py --desktop
python main.py --desktop --no-topmost --width 1366 --height 768
```

桌面版与网页版功能一致，区别只在「形态」：

| | 网页版 `start.bat` | 桌面版 `start_app.bat` |
|---|---|---|
| 后端 | 独立 cmd 窗口 | 桌面进程内 |
| 前端 | Vite dev（5173，热更新） | 后端托管的 `dist` 构建产物 |
| 语音微服务 | 各自一个 cmd 窗口 | 桌面进程内，**不弹窗** |
| 可见窗口 | 4 个控制台 + 1 个浏览器 | **只有 1 个独立窗口** |

> 桌面版**默认免登录**（单用户模式，数据归属本机账号 `desktop@local`）。想恢复登录页：`.env` 中设 `AUTH_REQUIRED=true`，或 `start_app.bat --auth-required true`。
>
> 桌面版**默认不询问语音开关**，是否启用完全由 `.env` 中的 `VOICE_ENABLED` / `STT_ENABLED` / `TTS_ENABLED` 决定，保持双击即用。
>
> **控制台启动后会自动隐藏**，日志写入 `logs/desktop.log`。排查问题用 `start_app.bat --hide-console false` 保留黑窗口。
>
> 独立窗口要求先构建前端：`cd frontend && npm run build`（`start_app.bat` 会在产物缺失或源码更新时自动重新构建）。

**常用启动参数**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` / `--port` | `127.0.0.1` / `8000` | 监听地址与端口 |
| `--auto-port` | `false` | 端口被占用时自动向后查找可用端口 |
| `--reload` | `false` | 开启热重载（开发用） |
| `--shell {auto,native,browser}` | `auto` | 窗口实现方式，见下表 |
| `--window-title TEXT` | `面试 Agent — AI 模拟面试助手` | 窗口标题 |
| `--width` / `--height` | `1280` / `800` | 窗口尺寸 |
| `--topmost [BOOL]` / `--no-topmost` | `true` | 窗口置顶 |
| `--opacity N` | `1.0` | 窗口透明度 `0.2`–`1.0`（也可写 `20`–`100` 百分数） |
| `--zoom N` | `1.0` | 界面缩放 `0.5`–`2.0`（也可写百分数） |
| `--capture-exclude [BOOL]` | `true` | 从截屏 / 录屏中排除窗口（仅 native 真正生效） |
| `--hide-taskbar [BOOL]` | `false` | 隐藏任务栏图标 |
| `--fullscreen [BOOL]` | `false` | 全屏启动 |
| `--app PATH` | — | 启动后打开的页面，如 `--app /login` |
| `--browser PATH` | — | 【browser 模式】指定浏览器可执行文件 |
| `--user-data-dir PATH` | `~/.interview-agent/desktop-profile` | 【browser 模式】浏览器用户数据目录 |
| `--debug` | `false` | 【native 模式】开启 WebView 开发者工具 |
| `--hide-console [BOOL]` | `true` | 启动后隐藏启动器控制台 |
| `--auth-required [BOOL]` | `false` | 是否要求登录；`true` 恢复登录页 |
| `--no-console` | `false` | 不输出启动日志 |
| `--open-timeout SEC` | `90` | 等待服务就绪的最长秒数 |

**两种窗口实现**

| `--shell` | 内核 | 置顶 | 捕获排除 | 全局 F8 热键 | 依赖 |
|-----------|------|------|----------|--------------|------|
| `native`（auto 时优先） | Edge WebView2 | ✅ | ✅ 真正生效 | ✅ 窗口失焦也能触发 | `pywebview` + WebView2 运行时 |
| `browser` | 系统 Edge / Chrome `--app` | ✅ | ❌ 系统跨进程限制 | ⚠️ 仅窗口聚焦时 | 无（零依赖） |

> 未安装 `pywebview` 时自动回退到 `browser` 模式，功能不受影响（仅捕获排除无效）。
>
> **为什么 `browser` 做不到捕获排除？** Windows 的 `SetWindowDisplayAffinity` 只能作用于本进程拥有的窗口；`browser` 模式窗口属于浏览器进程，跨进程调用会被系统拒绝。`native` 模式下窗口由本进程创建，因此截屏 / 录屏 / 直播中该窗口内容不可见。
>
> **为什么 `browser` 做不到全局热键？** 网页 JS 的 `keydown` 只在窗口聚焦时才有事件，这是浏览器的安全边界。`native` 模式改由 Python 侧调用 Win32 `RegisterHotKey` 注册，系统投递 `WM_HOTKEY`，因此焦点在任何窗口上都能触发。

#### 方式三：Docker Compose

```bash
cp .env.example .env      # 编辑填入 DEEPSEEK_API_KEY
docker-compose up -d
docker-compose ps
```

访问 <http://localhost>（Nginx 监听 80 端口）。

**轻量部署（无 RAG，适合无 CUDA / 低资源环境）**

```bash
SKIP_RAG=true RAG_ENABLED=false docker-compose up -d
```

> 镜像体积减少约 2GB。对话、面试模拟、报告生成等核心功能完全正常，仅知识库上传与 RAG 检索不可用。

**语音功能（通过 Profile 启用）**

```bash
docker compose --profile cpu up     # CPU 语音（STT + TTS）
docker compose --profile gpu up     # GPU 语音
docker compose --profile stt up     # 仅 STT 语音识别
docker compose --profile tts up     # 仅 TTS 语音合成
docker compose --profile voice up   # 语音全功能
```

首次使用会自动下载模型（Whisper 约 200MB + Piper 约 50MB），由 `stt_models` / `tts_models` 卷持久化。

**服务与路由架构**

```
Browser → Nginx (:80) ─┬─ /api/*     → 反代 → FastAPI (backend:8000)
                       ├─ /api/stt/* → 反代 → STT 服务 (stt:8000)
                       ├─ /api/tts/* → 反代 → TTS 服务 (tts:8000)
                       └─ 其他路径    → 前端静态文件（SPA 回退 index.html）
```

**常用命令**

| 命令 | 说明 |
|------|------|
| `docker-compose up -d` | 启动（标准模式） |
| `docker-compose down` | 停止并删除容器 |
| `docker-compose down -v` | 停止并删除容器 + 数据卷（**会清空数据**） |
| `docker-compose logs -f backend` | 查看后端日志 |
| `docker-compose restart backend` | 重启后端 |

#### 方式四：单容器 Docker

```bash
# 构建（不含 RAG）
docker build --build-arg SKIP_RAG=true -t interview-agent .

# 运行
docker run -d \
  --name interview-agent \
  -p 8000:8000 \
  --env-file .env \
  -e RAG_ENABLED=false \
  -v interview-data:/app/data \
  interview-agent
```

访问 <http://localhost:8000>。

> 需要 RAG 时去掉 `--build-arg SKIP_RAG=true`，并加上 `-e RAG_ENABLED=true` 与 `-v interview-chroma:/app/chroma_data`。

### 第三步：注册账号

网页版首次使用需要注册（邮箱 + 密码，密码至少 6 位）。桌面版默认免登录，直接进入。

---

## ⚙️ 配置项

所有配置通过项目根目录的 `.env` 文件提供（模板见 [.env.example](.env.example)），由 [config.py](config.py) 读取。**命令行参数优先于 `.env`**，界面上的选择（模型、思考开关、推理强度）优先于 `.env` 中的默认值。

### 模型与 LLM

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API Key（可留空，改由界面填写） |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 地址 |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | 默认模型 |
| `DEEPSEEK_THINKING_ENABLED` | `true` | 默认是否启用思考模式 |
| `DEEPSEEK_REASONING_EFFORT` | `high` | 推理强度：`low`（快省）/ `high`（官方默认）/ `max`（最充分） |
| `AVAILABLE_MODELS` | `deepseek-v4-pro,deepseek-v4-flash` | **仅兜底**：正常由官方 `GET /models` 动态获取 |
| `MAX_CONTEXT_TOKENS` | `1000000` | 上下文窗口总预算（token） |
| `SYSTEM_RESERVED_TOKENS` | `16000` | 为 system 消息预留的 token 数 |
| `PREFIX_CACHE_MAX_ENTRIES` | `64` | 最多缓存多少场面试的稳定前缀 |
| `PREFIX_CACHE_MAX_TOKENS` | `200000` | 单条稳定前缀的 token 上限，超过则不缓存 |
| `PREFIX_CACHE_TTL_SECONDS` | `1800` | 稳定前缀缓存存活时间（秒） |

### 上下文结构（前缀缓存）

每轮发给模型的 messages 顺序固定为：

```
system:  静态指令 → 经验级别 → 轮次 → 岗位类型 → 题库/补充说明 → 简历 → JD →（时间预算）
user:    历史提问……（每轮只在尾部追加）
user:    本轮提问 + 【参考上下文】RAG / 联网搜索 / 编程题   ← 唯一每轮变化的部分
```

这套顺序是为**服务端前缀缓存（prefix caching）**服务的：DeepSeek 按 token
前缀匹配 KV，只要前缀逐字节一致就能复用，省下重复的 prefill。因此

- 静态指令排在简历/JD **之前**，跨会话可复用的前缀最长；
- `system` 在同一场面试里只构建一次并进程内缓存，绝不逐轮重建；
- RAG 检索结果、联网搜索、编程题等**每轮变化**的内容，一律追加到
  **最后一条 user 消息的末尾**，绝不放进 `system`（放进去会让它之后的 KV 全部失效）；
- token 裁剪只作用于对话部分，`system` 原样透传（裁它会让前缀变短、缓存失效）。

> **实测（deepseek-flash，2026-10）**：缓存确实是「从第 0 个 token 起的严格前缀匹配」。
> 用同一段 nonce 前缀做对照实验——只改尾部时 `cache_hit=128`（命中前半段），
> 而在前缀**中途**插入一句话则 `cache_hit=0`（整条前缀连同后面全部作废）。
> 这就是「变化的内容只能放尾部」的实证依据。
>
> 真实面试场景下同前缀连发三轮的命中率约 82–85%，未命中的部分正好是本轮新增的问答。
> 需要复现可跑 `scripts/verify_prefix_cache.py`（只读 `.env` 的 Key，不写业务数据）。

日志里可直接观测命中情况：

```
Prefix cache HIT | fp=xxxx | 1537 chars / ~1500 tokens      # 进程内前缀复用
Context: 22 messages, ~1843 tokens (... prefix=cache, fp=xxxx)
LLM usage | prompt=1504 (cache_hit=1408, cache_miss=96) | cache_hit_rate=93.6%   # 服务端前缀缓存
```

配置开关见 `PREFIX_CACHE_*`；`prefix=client` 表示前端回传的 system 与后端
权威前缀一致（这是最理想的情况）。

### RAG 知识库

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RAG_ENABLED` | `true` | RAG 检索增强总开关（关闭后对话不注入知识库上下文） |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding 模型名 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace 镜像（国内用户必配） |
| `HF_HOME` | `./hf_cache` | 模型缓存目录 |
| `CHROMA_PERSIST_PATH` | `./chroma_data` | 向量索引存储根目录（内部为 `faiss_indexes/`） |
| `VECTOR_SEARCH_TOP_K` | `3` | 每次检索返回的文档块数 |
| `FAISS_VERIFY_INTEGRITY` | `true` | FAISS 索引 SHA-256 完整性校验（生产环境务必开启） |

> RAG 需要额外依赖：`pip install -r requirements-rag.txt`（`faiss-cpu` + `sentence-transformers` + `langchain-huggingface`）。**未安装时应用仍可启动**，只是知识库上传与检索不可用（启动日志会给出提示）。

### 认证与数据库

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AUTH_REQUIRED` | `true` | `true` 需登录且数据按用户隔离；`false` 为单用户免登录模式 |
| `JWT_SECRET` | `change-me-...` | **生产环境必须替换**为足够长的随机串 |
| `JWT_ALGORITHM` | `HS256` | JWT 签名算法 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | 访问令牌有效期（分钟） |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` | 刷新令牌有效期（天） |
| `FREE_DAILY_INTERVIEW_LIMIT` | `10` | 免费用户每日面试次数限制 |
| `DB_TYPE` | `sqlite` | `sqlite`（开发）/ `postgresql`（生产） |
| `DATABASE_URL` | — | 直接提供完整连接串可覆盖以下所有 `DB_*` 配置 |
| `DB_HOST` / `DB_PORT` | `localhost` / `5432` | PostgreSQL 地址与端口 |
| `DB_USER` / `DB_PASSWORD` | `interview` / — | PostgreSQL 账号 |
| `DB_NAME` | `interview_platform` | 数据库名 |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `20` | 连接池大小与溢出上限 |
| `DB_ECHO` | `false` | 是否打印 SQL |

> SQLite 数据库文件固定在 `data/interview_platform.db`（使用绝对路径，不受工作目录影响）。

### 服务与安全

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 监听地址与端口（默认仅本机可访问） |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173` | 允许的前端来源，逗号分隔 |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

> ⚠️ `allow_credentials=True` 时 CORS 不能使用 `*`，必须写具体域名。生产环境请改为实际域名。

### 截图答题

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SCREENSHOT_ENABLED` | `true` | 截图接口总开关（关闭后路由不注册，前端提示未启用） |
| `SCREENSHOT_VISION_MODEL` | 空 | 视觉模型兜底偏好；留空则自动选账号下第一个支持图片的模型 |
| `SCREENSHOT_DIR` | `screenshots` | 截图保存目录 |
| `SCREENSHOT_MAX_IMAGE_EDGE` | `1280` | 上传前图片最长边（像素） |
| `SCREENSHOT_MAX_TOKENS` | `8192` | 单次回答最大 token 数 |
| `SCREENSHOT_THINKING_ENABLED` | `false` | 截图问答默认是否启用思考模式 |
| `SCREENSHOT_SAVE` | `true` | 是否把每次截图留档到磁盘 |

### 系统音频捕获

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SYSTEM_AUDIO_ENABLED` | `false` | 总开关（关闭时 `/system-audio` 路由不注册） |
| `SYSTEM_AUDIO_DEVICE` | 空 | 捕获设备 id；留空用系统默认播放设备 |
| `SYSTEM_AUDIO_BLOCK_MS` | `100` | 每次从回环读取的音频块长度（毫秒） |
| `SYSTEM_AUDIO_AUTOSTART` | `true` | 服务启动时是否自动开始捕获 |
| `SYSTEM_AUDIO_TRANSCRIPT_BUFFER` | `200` | 转写结果在内存中保留的条数 |
| `SYSTEM_AUDIO_STT_TIMEOUT` | `30` | 连接 STT 微服务的超时（秒） |
| `SYSTEM_AUDIO_STT_PING_TIMEOUT` | `120` | STT WebSocket 心跳超时（秒） |

### 语音（STT / TTS）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VOICE_ENABLED` | `false` | 语音功能总开关 |
| `STT_ENABLED` | `false` | 语音识别（语音转文字） |
| `TTS_ENABLED` | `false` | 语音合成（文字转语音） |
| `STT_MODEL` | `base` | Whisper 模型：`tiny` / `base` / `small` / `medium` / `large-v3-turbo` |
| `STT_DEVICE` | `cpu` | 推理设备：`cpu` / `cuda` |
| `STT_COMPUTE_TYPE` | `int8` | 量化类型：`int8` / `float16` / `int8_float16`（留空按设备自动：GPU→float16，CPU→int8） |
| `STT_SERVICE_URL` | `http://stt:8000` | STT 微服务地址（本地运行为 `http://localhost:8001`） |
| `STT_WS_URL` | `ws://stt:8000/stream` | STT WebSocket 地址 |
| `STT_DOCKERFILE` | `Dockerfile` | `Dockerfile`（CPU）/ `Dockerfile.gpu`（GPU） |
| `VAD_SILENCE_TIMEOUT` | `1.0` | VAD 静默判定超时（秒） |
| `STT_CHUNK_MAX_SECONDS` | `25` | 连续语音硬切上限（秒） |
| `STT_CHUNK_OVERLAP_SECONDS` | `0.5` | 硬切时前后块重叠时长（秒） |
| `STT_CHUNK_CONTEXT_CHARS` | `120` | 跨块上下文长度（字符），注入上一块尾部文本 |
| `TTS_VOICE` | `zh_CN-huayan-medium` | Piper 中文语音模型 |
| `TTS_SPEED` | `1.0` | 语速（`0.5`–`2.0`） |
| `TTS_SERVICE_URL` | `http://tts:8000` | TTS 微服务地址（本地运行为 `http://localhost:8002`） |
| `TTS_WS_URL` | `ws://tts:8000/stream` | TTS WebSocket 地址 |

### 独立窗口

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DESKTOP_MODE` | `false` | 是否以独立窗口模式启动（`desktop.py` 会自动设置） |
| `DESKTOP_WIDTH` / `DESKTOP_HEIGHT` | `1280` / `800` | 窗口尺寸 |
| `DESKTOP_TOPMOST` | `true` | 窗口置顶 |
| `DESKTOP_CAPTURE_EXCLUDE` | `true` | 从屏幕捕获中排除窗口（仅 native 生效） |
| `DESKTOP_HIDE_TASKBAR` | `false` | 隐藏任务栏图标 |
| `DESKTOP_OPACITY` | `1.0` | 窗口透明度 |
| `DESKTOP_ZOOM` | `1.0` | 界面缩放 |
| `DESKTOP_BROWSER` | 空 | 指定浏览器路径（仅 browser 模式），留空自动查找 Edge / Chrome |

---

## 📖 使用指南

### 场景一：你是面试官

```
创建岗位 → 添加 JD → 上传知识库 → 上传简历/代码 → 切换为「你是面试官」 → 向 AI 求职者提问
```

1. 在**岗位管理**页创建岗位并添加职位描述（JD）
2. 在**知识库**页上传相关文档（技术规范、FAQ 等）
3. 在**上传**页上传候选人简历（PDF / Word）与代码文件
4. 进入 **AI 对话**页，选择 **🎯 你是面试官** 模式
5. 向 AI 求职者提问，AI 会结合 JD、简历、代码与知识库回答
6. 结束后前往**面试报告**页生成评估

### 场景二：你是求职者

```
创建岗位 → 添加 JD → 上传知识库 → 上传简历 → 设置时长 → 推算题数 → 开始练习 → 回答 → 生成报告
```

1. 创建目标岗位并填写 JD
2. 上传知识库文档与你的简历
3. 进入 **AI 对话**页，选择 **🧑 你是求职者** 模式
4. 选择面试时长（15 / 30 / 45 / 60 分钟），点击 **推算** 获取预估题量
5. 点击 **开始模拟练习**，AI 面试官逐题提问
6. 在输入框回答，练习中实时显示进度（第 N/M 题）
7. 完成后点击 **结束练习**，前往**面试报告**页生成多维度评估

### 场景三：实战辅助

- **截图答题**：在 AI 对话页点击输入框右侧的 **截图** 按钮，或直接按 **`F8`**。截图会连同输入框中的补充要求一起发给模型，回答直接渲染在对话里。
- **系统音频转写**：在**设置 → 监听系统音频**中开启（或设 `SYSTEM_AUDIO_ENABLED=true`），即可把电脑正在播放的声音实时转成文字。
- **语音输入 / 朗读**：启用语音功能后，输入框出现录音按钮；AI 回复下方出现朗读按钮。

### 题库使用模式

在对话中选择题库题目时，可指定 AI 的出题策略：

| 模式 | 说明 |
|------|------|
| `strict`（严格） | AI 必须且只能逐题照读题库题目，不可修改、跳过或自编 |
| `mixed`（混合，默认） | 题库题目为必考题，全部问到；可自行补充不超过 2 道追问 |
| `adaptive`（灵活改编） | 题库作为参考，可调整措辞、难度与顺序，核心考察点不变 |

### ChatRequest 主要参数

```json
{
  "messages": [{"role": "user", "content": "请介绍一下你自己"}],
  "mode": "interviewer",
  "position_name": "前端工程师",
  "jd_id": "jd_001",
  "use_search": false,
  "coding_enabled": false,
  "model": "deepseek-v4-pro",
  "thinking_enabled": true,
  "reasoning_effort": "high",
  "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "candidate_level": "experienced",
  "interview_round": "first",
  "interview_duration_minutes": 30,
  "interview_question_count": 10,
  "question_bank_ids": [],
  "question_bank_mode": "mixed"
}
```

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `mode` | `string` | `null` | `"interviewer"` 面试官 / `"candidate"` 求职者 |
| `position_name` | `string` | `null` | 关联岗位，**同时触发 RAG 检索**（为空则不检索） |
| `jd_id` | `string` | `null` | 指定使用某份 JD（为空则使用全部 JD） |
| `use_search` | `bool` | `false` | 是否启用联网搜索 |
| `coding_enabled` | `bool` | `false` | 是否启用编程题（**仅 `mode="candidate"` 时生效**） |
| `model` | `string` | `null` | 覆盖默认模型 |
| `thinking_enabled` | `bool` | `null` | 覆盖默认思考开关 |
| `reasoning_effort` | `string` | `null` | `"low"` / `"high"` / `"max"` |
| `api_key` | `string` | `null` | 前端传入的 Key，优先级高于 `.env` |
| `resume_text` | `string` | `null` | 简历文本 |
| `code_context` | `string` | `null` | 代码文本（仅面试官模式使用） |
| `candidate_level` | `string` | `null` | `"intern"` / `"new_grad"` / `"experienced"` |
| `interview_round` | `string` | `null` | `"first"` / `"second"` / `"hr"` |
| `interview_duration_minutes` | `int` | `30` | 面试总时长，影响时间预算感知 |
| `interview_question_count` | `int` | `0` | 计划题目数量（0 表示按默认 8 题） |
| `interview_coding_min` | `int` | `0` | 编程题预留时间（分钟） |
| `prompt_notes` | `string` | `null` | 界面 PromptEditor 的补充说明，追加到 system prompt 末尾 |
| `question_bank_ids` | `string[]` | `null` | 从题库中选定的题目 ID 列表 |
| `question_bank_mode` | `string` | `"mixed"` | 题库使用模式：`strict` / `mixed` / `adaptive` |

### 面试题量与时间推算

点击界面的 **推算** 按钮（或调用 `POST /interview/plan`）会根据**面试时长、回答长度、候选人级别、面试轮次**推算题量，并拆分为自我介绍、技术问答、编程题、反问四个环节。

- 题量会限制在 2 – 30 题之间，HR 面强制 30 分钟上限并禁用编程题。
- 练习过程中系统会**动态重规划**，根据已用时间与已答题数调整剩余题量与当前阶段。

---

## 🔌 API 概览

后端路由**同时注册了两套**：无前缀（`/chat/stream`）与 `/api` 前缀（`/api/chat/stream`）。这就是为什么开发模式下 Vite 会把 `/api` 前缀剥离后转发到 `:8000`。

> 完整交互式文档：启动后访问 <http://localhost:8000/docs>（Swagger）或 `/redoc`。

### 对话与面试

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 对话 | `GET` | `/chat/models` | 可用模型列表（`?refresh=true` 强制刷新缓存） |
| 对话 | `POST` | `/chat/stream` | SSE 流式对话 |
| 面试 | `POST` | `/interview/start` | 开始面试（组装 system prompt） |
| 面试 | `POST` | `/interview/stop` | 停止面试 |
| 面试 | `POST` | `/interview/report` | 生成报告（支持结构化 QA 逐题评估） |
| 面试 | `POST` | `/interview/plan` | 面试时长推算（含阶段拆分与动态重规划） |

**SSE 事件格式**：每帧为 `data: {"type": "...", "content": "..."}`，`type` 取值为 `reasoning`（思维链）/ `content`（正文）/ `system_prefix`（稳定前缀，见下）/ `error`；流结束发送 `data: [DONE]`。

`system_prefix` 帧带 `content`（整段 system 文本）与 `fingerprint`，**只在首轮、或后端发现前端手上那份已过期时下发**。前端把它按模式存起来（不进消息列表、不持久化），后续轮次作为 `messages[0]` 原样回传；后端逐字节比对通过就沿用，因而「prompt + 简历 + JD」在整场面试里完全不变。响应头另带 `X-Prefix-Fingerprint`，便于把日志里的 `fp=` 与某场面试对应起来。

### 岗位 / 题库 / 上传 / 知识库

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 岗位 | `GET` `POST` | `/positions` | 列表 / 创建岗位 |
| 岗位 | `GET` `PUT` `DELETE` | `/positions/{name}` | 岗位详情 / 更新 / 删除 |
| 岗位 | `POST` `PUT` `DELETE` | `/positions/{name}/jds` | JD 管理（一个岗位可挂多份 JD） |
| 题库 | `GET` `POST` | `/question-bank/` | 题目列表 / 新增题目 |
| 题库 | `GET` `PUT` `DELETE` | `/question-bank/{id}` | 题目详情 / 更新 / 删除 |
| 题库 | `POST` | `/question-bank/import/leetcode` | 从 LeetCode 题库批量导入 |
| 题库 | `GET` | `/question-bank/categories/list` | 分类列表 |
| 上传 | `POST` | `/upload/resume` | 上传简历 |
| 上传 | `POST` | `/upload/code` | 上传代码 |
| 上传 | `POST` | `/upload/project` | 上传项目（解析目录结构与技术栈） |
| 上传 | `GET` `DELETE` | `/upload/files` | 上传记录列表 / 清空 |
| 上传 | `GET` `DELETE` | `/upload/files/{id}` | 单条记录详情 / 删除 |
| 知识库 | `POST` | `/knowledge/upload` | 上传文档并建索引 |
| 知识库 | `GET` | `/knowledge/collections` | 列出所有知识库 |
| 知识库 | `GET` | `/knowledge/search` | 向量检索（`top_k` 取值 1–20） |
| 知识库 | `DELETE` | `/knowledge/collections/{name}` | 删除知识库 |
| 知识库 | `GET` `POST` | `/knowledge/rag-status` `rag-toggle` | 查询 / 切换 RAG 开关（运行时） |

### 会话 / 分析 / 认证

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 会话 | `GET` | `/sessions/` | 历史会话列表 |
| 会话 | `GET` | `/sessions/{id}` | 会话详情 + 消息回放 + QA 记录 + 报告 |
| 会话 | `DELETE` | `/sessions/{id}` | 删除会话 |
| 分析 | `GET` | `/analytics/dashboard` | 概览仪表盘 |
| 分析 | `GET` | `/analytics/progress` | 进步趋势（`7d` / `30d` / `90d`） |
| 分析 | `GET` | `/analytics/weakness` | 薄弱项分析与改进建议 |
| 分析 | `GET` | `/analytics/comparison` | 多次面试对比 |
| 分析 | `GET` | `/analytics/stats` | 统计汇总 |
| 认证 | `GET` | `/auth/mode` | 查询当前认证模式（无需 token） |
| 认证 | `POST` | `/auth/register` `login` `refresh` | 注册 / 登录 / 刷新令牌 |
| 认证 | `GET` `PUT` | `/auth/me` | 当前用户信息 / 更新资料 |

### 实战辅助（条件注册）

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 截图 | `GET` | `/screenshot/info` | 截图能力、显示器与视觉模型信息 |
| 截图 | `POST` | `/screenshot/capture` | 截取主显示器并交给视觉模型识别作答 |
| 系统音频 | `GET` | `/system-audio/info` `devices` `status` | 能力 / 设备列表 / 运行状态 |
| 系统音频 | `POST` | `/system-audio/start` `stop` `clear` | 开始 / 停止捕获 / 清空转写 |
| 系统音频 | `GET` | `/system-audio/transcript` | 增量拉取转写结果（`?since=<seq>`） |
| 语音 | `GET` | `/stt/health` `/tts/health` | 微服务健康检查 |
| 语音 | `POST` | `/stt/transcribe` `/tts/synthesize` | 批量识别 / 合成（兜底接口） |

> 截图与系统音频路由**按开关条件注册**：`SCREENSHOT_ENABLED=false` 或 `SYSTEM_AUDIO_ENABLED=false` 时路由不存在。此时 `/api/*` 的 404 会返回**结构化 JSON 提示**（说明「多半是功能开关未开启」），而不是让前端拿到 HTML 去 `JSON.parse` 报出难以理解的错误。

---

## 📷 截图答题

在 **AI 对话页**底部输入框右侧点击 **「截图」** 按钮（或按 **`F8`**），会截取**主显示器**画面，交给视觉模型提取题目并作答，回答直接显示在对话里。

**前置条件**

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10 2004（build 19041）及以上 |
| Python 依赖 | `windows-capture`（已随 `requirements.txt` 安装） |
| 模型 | 必须支持图片输入 |

**使用要点**

- 截图使用界面**模型选择器**中选中的模型；不支持图片输入时会直接提示，**不会**把图片发给纯文本模型（纯文本模型收到图片不会报错，而是编造答案）。
- 输入框里可以先写一句要求（例如「只给答案，不要解释」），截图时会一并作为提问发出，所以可以「先打好要求，再按 F8」。
- **独立窗口模式**下 F8 是系统级全局热键，**窗口失焦也能触发**（这正是截图场景的关键）；浏览器模式下 F8 仅在窗口聚焦时生效。
- 独立窗口模式下，截图前会自动把本应用从屏幕捕获中排除，不会把自己拍进去。
- 全局热键被其它程序占用时会自动退化为窗口内快捷键。

> **关于思考模式**：思维链与正文共享 `max_tokens` 预算，截图答题若开启思考容易导致正文被截断，因此默认关闭。若回答仍被截断，界面会明确标注。

---

## 🎧 系统音频转写

与截图答题对称：截图抓「屏幕上看到的」，系统音频抓「扬声器里放的」。面试时对方的提问往往来自会议软件 / 视频 / 网页播放，**麦克风录不到**，这里通过 Windows WASAPI 回环直接从扬声器设备抓取并实时转文字。

**启用前提（三者缺一不可）**

1. `SYSTEM_AUDIO_ENABLED=true`（否则接口不注册）；
2. `VOICE_ENABLED=true` 或 `STT_ENABLED=true`，且 **STT 微服务已启动**（`docker compose --profile stt up`，或本地跑 `stt_service`）；
3. `STT_SERVICE_URL` 指向该服务（本地运行为 `http://localhost:8001`）。

> 仅支持 Windows。STT 未就绪时捕获仍会运行，只是不产生文字，状态里会说明原因，STT 起来后会自动重连。

---

## 🧪 运行测试

```bash
pytest tests/ -v
```

测试标记（`pytest.ini`）：

| 标记 | 含义 |
|------|------|
| `windows_only` | 依赖 Windows 专有依赖（`windows-capture` / `soundcard` / `pywebview`），在 Linux CI 上跳过 |
| `slow` | 需要真实时间等待的用例 |

CI（[.github/workflows/ci.yml](.github/workflows/ci.yml)）在 Ubuntu 上跑 Python 3.11 / 3.12 的后端测试，以及前端 `npm run build`（含 `tsc` 类型检查）。前端 Lint 目前**不阻断**构建（仓库存在历史 lint 问题）。

---

## 🧹 代码检查（pre-commit）

项目使用 [pre-commit](https://pre-commit.com) 在提交前自动检查代码，并由 [pre-commit.ci](https://pre-commit.ci) 在 PR 上自动运行与修复。

### 本地启用

```bash
pip install pre-commit
pre-commit install          # 安装 git hook，之后每次 commit 自动检查
```

### 常用命令

| 命令 | 说明 |
|------|------|
| `pre-commit run --all-files` | 对全部文件跑一遍检查 |
| `pre-commit run <hook-id>` | 只跑某个钩子，如 `pre-commit run ruff` |
| `pre-commit autoupdate` | 把钩子版本升级到最新 tag |
| `git commit --no-verify` | 跳过本次检查（仅在确有必要时使用） |

### 包含的检查

| 钩子 | 作用 |
|------|------|
| `check-yaml` / `check-json` / `check-toml` | 校验配置文件语法 |
| `check-merge-conflict` | 拦截未解决的合并冲突标记 |
| `check-added-large-files` | 拦截超过 1MB 的大文件 |
| `mixed-line-ending` | 统一换行为 LF |
| `end-of-file-fixer` / `trailing-whitespace` | 修正文件末尾换行与行尾空白 |
| `detect-private-key` | 兜底防止私钥误提交 |
| `ruff` | Python 静态检查，并自动修复导入排序、未使用导入等问题 |

> **未启用 `ruff-format`**：它会重写 64/70 个 Python 文件（约 3.7 万行），与功能改动混在一起会让代码审查失去意义。如需统一格式，建议单独开一个只做格式化的提交，届时再在配置中打开该钩子。
>
> 静止规则集刻意从窄到宽（见 `pyproject.toml`），目前只启用确定性问题与导入排序；`UP`（如 `Optional[X]` → `X | None`）等会带来大量改动的规则尚未开启，可在后续逐步收紧。

### CI 行为

登录 [pre-commit.ci](https://pre-commit.ci) 用 GitHub 账号授权本仓库即可启用，无需额外配置：

- 每个 PR 自动运行钩子，并直接向 PR 提交修复
- 每周一约 16:00 UTC 自动提交钩子版本升级 PR
- 在 PR 中单独一行评论 `pre-commit.ci run` 可重新触发
- 提交信息含 `[skip ci]` / `[skip pre-commit.ci]` 时跳过

---

## 🔧 技术栈

### 后端

| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| LLM | DeepSeek V4 Pro / Flash（OpenAI 兼容协议） |
| 流式输出 | Server-Sent Events (SSE) |
| 数据校验 | Pydantic v2 |
| ORM | SQLAlchemy 2.0 Async（SQLite / PostgreSQL 双模式） |
| 认证 | python-jose (JWT) + passlib/bcrypt |
| RAG 管线 | LangChain LCEL + FAISS |
| Embedding | sentence-transformers (`all-MiniLM-L6-v2`) |
| Token 计数与裁剪 | tiktoken (cl100k_base) |
| 文档解析 | PyMuPDF + python-docx |
| 联网搜索 | DuckDuckGo Search |
| STT | faster-whisper（CTranslate2）+ Silero VAD |
| TTS | Piper TTS |

### 前端

| 组件 | 技术 |
|------|------|
| 框架 | React 19 + TypeScript 6 |
| 构建工具 | Vite 8 |
| UI 库 | Ant Design 6 |
| 路由 | React Router 7 |
| 状态管理 | Zustand 5 |
| Markdown | react-markdown + remark-gfm + react-syntax-highlighter |

---

## ⚠️ 注意事项

### 通用

- **首次启动会下载模型**。RAG 的 Embedding 模型约 90MB（已默认走镜像）；语音模型约 250MB（Whisper + Piper）。请保持网络畅通。
- **端口占用**：后端 `8000`、前端 `5173`、本地语音 `8001`（STT）/ `8002`（TTS）、Docker 前端 `80`。`start.bat` 会在启动前检查端口并打印占用进程的 PID 与处置命令；`desktop.py` 可用 `--auto-port` 自动顺延。
- **`.env` 不入库**（`.gitignore` 已排除），请勿把含密钥的 `.env` 提交到版本库。
- **`JWT_SECRET` 务必替换默认值**。默认值是公开的占位字符串，生产环境使用它等于没有签名保护。
- **CORS 不能用 `*`**。因为启用了 `allow_credentials=True`，必须写成具体域名；生产环境请把 `CORS_ORIGINS` 改为实际域名。
- **单用户模式不是「关掉一个提示」**。开启后（`AUTH_REQUIRED=false`），岗位 / 题库 / 会话 / 上传 / 分析等原本要求 token 的接口都会自动使用固定的本机账号 `desktop@local`，因此桌面版能与网页版拥有一致的完整功能。该账号会在建表时插入，其 `hashed_password` 为不可逆占位值，**不能用于密码登录**。
- **SQLite 适合单机使用**。多用户 / 高并发场景请切换到 `DB_TYPE=postgresql` 并配置 `DB_*`。

### RAG 与模型

- **RAG 依赖很重**（`sentence-transformers` 会拉入 `torch`，约 2GB）。不需要知识库时，建议设置 `RAG_ENABLED=false` 并不安装 `requirements-rag.txt`；Docker 部署用 `SKIP_RAG=true`。
- **未安装 RAG 依赖但 `RAG_ENABLED=true`** 时应用仍能启动，但知识库的上传 / 列表 / 检索会返回 **503**；而上传文件的索引与对话中的 RAG 注入会**静默跳过** —— 容易误判为「功能正常但检索不到内容」。
- **`FAISS_VERIFY_INTEGRITY` 生产环境请保持开启**。索引的 `index.pkl` 使用 pickle 序列化，本模块用 SHA-256 校验防止被篡改。校验失败时，确认可信后删除对应的 `.sha256` 文件再重新加载即可。
- **知识库目录名会被改写**。岗位名中的中文等字符会被替换为下划线并加 `kb_` 前缀（例如「前端工程师」→ `kb__kb`），这是正常的，界面仍显示原始岗位名。
- **`/knowledge/rag-toggle` 只在当前进程内生效**，重启后恢复 `.env` 中的配置。
- **模型列表来自远端**。`GET /models` 不可用时回退到 `.env` 的 `AVAILABLE_MODELS`，此时所有模型都被标记为不支持图片，截图功能会提示不可用。
- **编程题选题带随机性**，同样的输入多次调用可能选出不同题目。

### 接口行为细节

- **`/chat/stream` 只读取请求体里的 `api_key`**，不读取 `X-DEEPSEEK-API-KEY` 请求头（`/chat/models` 两者都读）。若只通过请求头传 Key，对话会静默回退到 `.env` 的 `DEEPSEEK_API_KEY`。
- **`code_context` 字段目前不生效**，代码与项目上下文统一走 RAG 向量检索提供。
- **`position_name` 同时是 RAG 的触发条件**：传入岗位名才会检索该岗位的知识库。
- **岗位名有字符限制**：2–50 个字符，仅允许字母、数字、中文、下划线、连字符（不允许空格、点、斜杠）。同一用户下重名返回 **409**。
- **`position_type` 在岗位创建时判定后不再变化**。「技术支持」「设计 / UI / UX」被归为**非技术岗**，此类岗位下编程题不会启用。
- **`/interview/report` 失败时返回 HTTP 200**，正文为 `报告生成失败: ...`，前端需自行识别。

### 文件上传限制与格式

| 接口 | 大小上限 | 接受格式 | 超限错误 |
|------|----------|----------|----------|
| `/upload/resume` | **5MB** | `.pdf` `.docx` `.doc` `.txt` | 413 |
| `/upload/code` | **2MB** | `.py` `.js` `.ts` `.jsx` `.tsx` `.java` `.go` `.cpp` `.c` `.h` `.hpp` `.rs` `.rb` `.php` `.swift` `.kt` `.scala` `.cs` `.vue` `.html` `.css` `.scss` `.sql` `.sh` `.bash` `.yaml` `.yml` `.json` `.xml` `.md` `.r` `.m` | 413 |
| `/upload/project` | **50MB** | `.zip` `.tar.gz` `.tgz` `.tar.bz2` `.tar.xz` `.tar` `.7z`（`.7z` 需 `py7zr`） | 413 |
| `/knowledge/upload`（`doc_type=faq`） | **10MB** | 同简历格式（**不支持 `.md`**） | 413 |
| `/knowledge/upload`（`doc_type=code`） | **10MB** | 同代码格式 | 413 |
| `/knowledge/upload`（`doc_type=project`） | **50MB** | 同压缩包格式 | 413 |

其他约定：

- **落库文本会截断至 100KB**，但上传接口响应中返回的是完整文本。也就是说：刚上传时前端拿到全文，之后重新读取时只能拿到 100KB 版本。
- 知识库检索的 `top_k` 仅接受 **1–20**，越界时静默回退为 3。
- 文件解析失败返回 **422**，扩展名不支持返回 **400**。
- 只有**代码**与**项目**会被索引进向量库（简历不索引）。
- 项目解析会自动跳过系统垃圾文件，并推断技术栈（Python / React / Java / Go / Rust / Docker 等）。

### Windows 专有功能

| 功能 | 依赖 | 缺失时的表现 |
|------|------|--------------|
| 截图答题 | `windows-capture` | 接口返回明确的安装指引，不抛 500 |
| 系统音频捕获 | `soundcard`（WASAPI 回环） | 明确提示「仅支持 Windows」 |
| 独立窗口 | `pywebview` + WebView2 运行时 | 自动回退到浏览器 `--app` 窗口（捕获排除失效） |

> 这些依赖在 `requirements.txt` 中带平台标记，非 Windows 平台会自动跳过安装，相关功能不可用但服务可正常运行。

### 独立窗口模式

- **必须存在前端构建产物**，否则 `/` 会退化为 JSON 健康信息。先执行 `cd frontend && npm run build`。
- **`--capture-exclude` 仅在 native 模式真正生效**，browser 模式受 Windows 跨进程限制无法生效（界面上该开关显示为禁用）。
- **`--opacity` 下限为 20%**，避免窗口过淡导致无法操作。
- 窗口项（置顶 / 透明度 / 缩放 / 捕获排除 / 隐藏任务栏）均可在界面「设置」面板中**运行中实时调整**，启动参数只决定初始状态。

### 语音功能

- **三个开关默认全为 `false`**，未启用时接口不注册、依赖不加载，对系统零影响。
- **本地运行时**，`STT_SERVICE_URL` / `TTS_SERVICE_URL` 需指向 `http://localhost:8001` / `http://localhost:8002`；Docker 内部网络则是 `http://stt:8000` / `http://tts:8000`。`start.bat` 会自动设置前者。
- **`STT_DEVICE=cuda` 需要 CTranslate2 的 CUDA 运行库**（cuBLAS / cuDNN），与 `torch` 无关；缺少时会自动回退 CPU 并在日志中告警。
- **Whisper 模型选择**：`tiny` / `base` 体积小但中文准确率偏低，建议使用 `large-v3-turbo`。
- 首次转录时 STT 需要加载模型，因此心跳与连接超时设置得比较宽松，避免误报「连不上」。

### 前端与本地存储

- **API Key 保存在浏览器 localStorage 中（明文）**。界面已提示「仅保存在本地浏览器中，不会上传到服务器」，但共享机器上仍需注意。清除方式：把界面的 API Key 输入框留空并确认。
- **登录令牌同样存在 localStorage**，收到 401 时会自动刷新。
- **对话消息只保留最近 100 条**（两种模式各自独立），QA 记录保留最近 30 条。
- **刷新页面会重置练习进度**，需要重新点击「开始模拟练习」。
- **不要使用前端 dev server 作为生产部署方式**。`start.bat` / `start.sh` 启动的是带热更新的 dev server；Docker 与独立窗口模式才使用构建产物。

### 启动脚本

- `start.bat` / `start.sh` **每次启动都会重装 Python 依赖**，每次都会联网耗时。
- `start.bat` / `start.sh` 会**交互询问**是否启用语音；`start_app.bat` 则完全从 `.env` 读取，不提问。
- 语音相关的安装与设备选择在 `start.bat` 中**只在当前窗口会话内生效，不会写回 `.env`**。想让配置长期生效，请手动写入 `.env`。
- 脚本只检查「是否安装了 Node」，并未校验版本。由于前端使用 Vite 8，建议使用 **Node 20+**。
- `start_app.bat` 接受并透传任意参数给 `desktop.py`，例如 `start_app.bat --width 1600 --height 900 --no-topmost`。

### 排查技巧

- `/api/*` 返回 404 且带「功能开关未开启」提示时，说明该功能的路由压根没注册 —— 检查对应的 `.env` 开关并**重启服务**。
- 排查前端拿到 HTML 导致的 `Unexpected token '<'` 报错：本项目已在应用级把 `/api/*` 的 404 兜底为结构化 JSON，若仍见到该报错，请确认请求路径是否真的以 `/api` 开头。
- 桌面版日志在 `logs/desktop.log`（控制台会被自动隐藏）。
- 依赖装不上时优先检查网络；国内环境请确认 `HF_ENDPOINT` 未被改动。
- **HuggingFace 下载卡在 0 字节**：`config.py` 已默认设置 `HF_HUB_DISABLE_XET=1`。新版 `huggingface_hub` 默认启用 Xet 存储后端，其域名不受 `HF_ENDPOINT` 影响，在国内会出现「元数据全部 200，但权重停在 0 字节」的现象。该变量必须**在任何 HF 相关库导入之前**注入，因此写在 `config.py` 顶部。

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request。

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

---

## 📄 License

MIT © 2025
