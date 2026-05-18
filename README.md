<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/TypeScript-6.0-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/DeepSeek-V4-536DFE?logo=openai&logoColor=white" alt="DeepSeek">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

<h1 align="center">🎯 Interview Agent</h1>
<p align="center"><strong>AI 模拟面试助手 — 让每一次面试都更有准备</strong></p>

<p align="center">
  <a href="#-一键启动">🚀 一键启动</a> •
  <a href="#-功能特性">✨ 功能特性</a> •
  <a href="#-技术栈">🧰 技术栈</a> •
  <a href="#-项目结构">📁 项目结构</a> •
  <a href="#-使用指南">📖 使用指南</a> •
  <a href="#-api-概览">🔌 API</a>
</p>

---

## 📖 简介

Interview Agent 是一个基于大语言模型的 AI 模拟面试平台，支持**面试官**和**求职者**双重视角。结合 RAG 向量知识库与联网搜索能力，为每一场面试提供上下文感知的智能对话体验。

### 核心场景

| 模式 | 说明 |
|------|------|
| 🎯 **你是面试官** | 用户以面试官身份向 AI 求职者提问。AI 结合岗位 JD、简历、代码文件和知识库给出专业回答，帮助面试官练习提问技巧 |
| 🧑 **你是求职者** | 用户以求职者身份接受 AI 面试官提问。AI 根据 JD 和简历自动出题，支持设置面试时长、推算题数、追踪进度，结束后生成评估报告 |

---

## ✨ 功能特性

- 🤖 **双模式 AI 对话** — 面试官 / 求职者自由切换，SSE 流式输出
- 🔑 **前端 API Key 配置** — 在界面中直接配置 DeepSeek API Key，密钥仅存本地
- ⏱️ **面试时长推算** — 求职者模式下设置面试时长，自动推算问题数量与阶段拆分
- 🎯 **模拟练习流程** — 求职者模式：AI 逐题提问 → 你回答 → 进度追踪 → 生成报告
- 🧑‍💻 **编程题模式** — 技术岗专属，根据岗位类型智能选题（LeetCode 风格），支持难度自适应
- 🎓 **候选人分级** — 支持实习 / 校招 / 社招三种级别，自动调整问题难度与深度
- 🔄 **面试轮次** — 初试 / 复试 / HR 面，不同轮次侧重不同考察方向
- 📚 **RAG 向量知识库** — 上传 PDF / Word / 文本，LangChain FAISS 向量检索增强回答质量
- 🌐 **联网搜索** — 集成 DuckDuckGo，实时获取最新技术资讯
- 📝 **面试报告生成** — 多维度评估（技术能力 / 沟通表达 / 综合素质），支持结构化 QA 逐题评估
- 🗂️ **岗位管理** — 创建岗位、添加多份 JD、关联知识库，支持按 JD 筛选
- 🎛️ **模型选择** — 支持 DeepSeek V4 Pro / Flash，可切换思考模式与推理强度
- 🔒 **安全机制** — CORS 域名白名单 + FAISS 索引 SHA-256 完整性校验
- 📐 **上下文窗口管理** — tiktoken 精确 token 计数 + LangChain trim_messages 智能裁剪
- 🖥️ **现代化 UI** — React + Ant Design 6，响应式布局
- 🐳 **一键部署** — 支持本地脚本 / Docker Compose / 单容器三种启动方式

---

## 🚀 一键启动

三种方式任选其一：

| 方式 | 命令 | 平台 |
|------|------|------|
| 📜 本地脚本 | `start.bat` / `./start.sh` | Windows / macOS / Linux |
| 🐳 Docker Compose | `docker-compose up -d` | 全平台 |
| 📦 单容器 | `docker run` | 全平台 |

> **首次使用**：复制 `.env.example` → `.env`，填入 [DeepSeek API Key](https://platform.deepseek.com/)
> 
> **国内用户注意**：首次启动需下载 Embedding 模型（约 90MB），`.env` 中已默认配置 HuggingFace 镜像 `HF_ENDPOINT=https://hf-mirror.com`，无需额外操作。

### 主要配置项

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API Key（必填） |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | 默认模型 |
| `AVAILABLE_MODELS` | `deepseek-v4-pro,deepseek-v4-flash` | 可选模型列表 |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding 模型名 |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace 镜像（国内用户） |
| `VECTOR_SEARCH_TOP_K` | `3` | RAG 检索返回文档数 |
| `CORS_ORIGINS` | `http://localhost:5173,...` | 允许的前端来源（逗号分隔） |
| `FAISS_VERIFY_INTEGRITY` | `true` | FAISS 索引 SHA-256 完整性校验 |
| `MAX_CONTEXT_TOKENS` | `800000` | 上下文窗口上限（token） |
| `DEEPSEEK_THINKING_ENABLED` | `true` | 默认启用思考模式 |

<details>
<summary><b>方式一：本地脚本（开发推荐）</b></summary>

**Windows** — 双击 `start.bat`

**macOS / Linux**：
```bash
chmod +x start.sh
./start.sh
```

脚本自动完成：环境检测 → 安装依赖 → 启动后端 `:8000` + 前端 `:5173` → 打开浏览器。
</details>

<details>
<summary><b>方式二：Docker Compose（部署推荐）</b></summary>

```bash
docker-compose up -d
```

访问 **http://localhost**

架构：`Nginx (:80)` → 前端静态文件 + `/api/*` 反代 → `FastAPI (:8000)`
</details>

<details>
<summary><b>方式三：单容器 Docker</b></summary>

```bash
docker build -t interview-agent .
docker run -p 8000:8000 --env-file .env interview-agent
```

访问 **http://localhost:8000**

三阶段构建：Node 编译前端 → pip 依赖 → FastAPI 全托管
</details>

---

## 🧰 技术栈

### 后端
| 组件 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| LLM | DeepSeek V4 Pro / Flash（OpenAI 兼容协议） |
| 流式输出 | Server-Sent Events (SSE) |
| RAG 管线 | LangChain LCEL + FAISS |
| 向量存储 | langchain-community FAISS |
| Embedding | HuggingFace sentence-transformers (all-MiniLM-L6-v2) |
| Token 计数 | tiktoken (cl100k_base) |
| 上下文裁剪 | LangChain trim_messages |
| 提示模板 | LangChain ChatPromptTemplate |
| 文档分块 | langchain-text-splitters RecursiveCharacterTextSplitter |
| 联网搜索 | DuckDuckGo Search |
| 文档解析 | PyMuPDF + python-docx |
| 数据校验 | Pydantic v2 |

### 前端
| 组件 | 技术 |
|------|------|
| 框架 | React 19 + TypeScript |
| 构建工具 | Vite 8 |
| UI 库 | Ant Design 6 |
| 路由 | React Router 7 |
| 状态管理 | Zustand |
| Markdown | react-markdown + remark-gfm |

---

## 📁 项目结构

```
interview-agent/
├── main.py                  # FastAPI 入口
├── config.py                # 环境变量配置
├── requirements.txt         # Python 依赖
├── Dockerfile               # 多阶段构建（前端+后端）
├── docker-compose.yml       # Docker Compose 编排
├── start.bat                # Windows 一键启动
├── start.sh                 # macOS/Linux 一键启动
├── .env.example             # 环境变量模板
├── positions.json           # 岗位数据
│
├── routers/                 # API 路由
│   ├── chat.py              #   对话 (SSE 流式)
│   ├── interview.py         #   面试控制（开始/停止/报告/计划）
│   ├── position.py          #   岗位管理
│   ├── upload.py            #   文件上传
│   └── knowledge.py         #   知识库管理
│
├── services/                # 业务逻辑
│   ├── llm_client.py        #   DeepSeek 客户端
│   ├── vector_store.py      #   LangChain FAISS 向量存储
│   ├── rag_pipeline.py      #   LCEL RAG 检索管线
│   ├── chunker.py           #   文档分块
│   ├── parser.py            #   文件解析 (PDF/Word)
│   ├── agent_tools.py       #   联网搜索工具
│   ├── coding_problem.py    #   编程题智能选题
│   ├── model_registry.py    #   模型注册表
│   ├── position_store.py    #   岗位持久化
│   └── upload_store.py      #   上传文件持久化
│
├── utils/                   # 工具模块
│   ├── context_manager.py   #   上下文窗口管理 (tiktoken)
│   ├── prompt_loader.py     #   提示模板加载 (LangChain)
│   └── position_classifier.py  # 岗位类型分类器
│
├── models/
│   └── schemas.py           # Pydantic 数据模型
│
├── prompts/                 # 系统提示词
│   ├── interviewer.txt      #   面试官
│   ├── candidate.txt        #   求职者
│   └── report.txt           #   报告生成
│
├── data/
│   └── leetcode_problems.json  # 编程题库
│
├── frontend/                # React 前端
│   ├── Dockerfile           #   前端镜像
│   ├── nginx.conf           #   Nginx 配置
│   └── src/
│       ├── api/             #   API 客户端
│       ├── pages/           #   页面
│       ├── components/      #   组件
│       ├── stores/          #   状态
│       └── hooks/           #   Hooks
│
├── tests/                   # 测试
└── chroma_data/             # FAISS 索引存储
    └── faiss_indexes/       #   按知识库名分目录
```

---

## 📖 使用指南

### 你是面试官

```
创建岗位 → 添加 JD → 上传知识库 → 上传简历/代码 → 切换模式 → 向 AI 求职者提问
```

1. 在「岗位管理」页面创建岗位，添加职位描述
2. 在「知识库」页面上传相关文档（技术规范、FAQ 等）
3. 在「上传」页面上传候选人简历（PDF / Word）和代码文件
4. 切换到「AI 对话」页面，选择 **🎯 你是面试官** 模式
5. 向 AI 求职者提问，AI 会结合 JD、简历、代码和知识库给出专业回答
6. AI 回答完毕后，前往「面试报告」页面生成评估

### 你是求职者

```
创建岗位 → 添加 JD → 上传知识库 → 上传简历 → 设置面试时长 → 推算题数 → 开始练习 → AI 提问你回答 → 生成报告
```

1. 创建目标岗位并填写 JD
2. 在「知识库」页面上传相关文档，在「上传」页面上传你的简历
3. 切换到「AI 对话」页面，选择 **🧑 你是求职者** 模式
4. 选择面试时长（15/30/45/60 分钟），点击 **推算** 获取预估题数
5. 点击 **开始模拟练习**，AI 面试官自动逐题提问
6. 在输入框中回答每个问题，练习中实时显示进度（第 N/M 题）
7. 完成后点击 **结束练习**，前往「面试报告」页面一键生成多维度评估

### ChatRequest 参数

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
  "interview_question_count": 10
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `mode` | `string` | `"interviewer"` 面试官 / `"candidate"` 求职者 |
| `position_name` | `string` | 关联岗位名称，触发 RAG 检索 |
| `jd_id` | `string` | 指定使用某份 JD（为空则使用全部 JD） |
| `use_search` | `bool` | 是否启用联网搜索 |
| `coding_enabled` | `bool` | 是否启用编程题（仅求职者模式+技术岗生效） |
| `model` | `string` | 模型选择，默认 `deepseek-v4-pro` |
| `thinking_enabled` | `bool` | 是否启用深度思考 |
| `reasoning_effort` | `string` | 推理强度：`"high"` / `"max"` |
| `api_key` | `string` | 前端配置的 DeepSeek API Key（可选，优先级高于 .env） |
| `candidate_level` | `string` | 候选人级别：`"intern"` / `"new_grad"` / `"experienced"` |
| `interview_round` | `string` | 面试轮次：`"first"` / `"second"` / `"hr"` |
| `interview_duration_minutes` | `int` | 面试总时长（分钟），影响时间预算感知 |
| `interview_question_count` | `int` | 计划题目数量 |

---

## 🔌 API 概览

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 对话 | `GET` | `/chat/models` | 可用模型列表 |
| 对话 | `POST` | `/chat/stream` | SSE 流式对话 |
| 岗位 | `GET` `POST` | `/positions` | 列表 / 创建岗位 |
| 岗位 | `GET` `PUT` `DELETE` | `/positions/{name}` | 岗位 CRUD |
| 岗位 | `POST` `PUT` `DELETE` | `/positions/{name}/jds` | JD 管理（支持多份 JD） |
| 面试 | `POST` | `/interview/start` | 开始面试（组装 system prompt） |
| 面试 | `POST` | `/interview/stop` | 停止面试 |
| 面试 | `POST` | `/interview/report` | 生成报告（支持结构化 QA 逐题评估） |
| 面试 | `POST` | `/interview/plan` | 🆕 面试时长推算（含阶段拆分、动态重规划） |
| 上传 | `POST` | `/upload/resume` | 上传简历 |
| 上传 | `POST` | `/upload/code` | 上传代码 |
| 知识库 | `POST` | `/knowledge/upload` | 上传文档 |
| 知识库 | `GET` | `/knowledge/collections` | 列出知识库 |
| 知识库 | `DELETE` | `/knowledge/{name}` | 删除知识库 |
| 知识库 | `POST` | `/knowledge/search` | 向量检索 |

> 完整 API 文档：启动后访问 **http://localhost:8000/docs** (Swagger) 或 **/redoc**

---

## 🧪 运行测试

```bash
pytest tests/ -v
```

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

