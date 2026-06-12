<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/TypeScript-6.0-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/DeepSeek-V4-536DFE?logo=openai&logoColor=white" alt="DeepSeek">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

<h1 align="center">🎯 Interview Agent</h1>
<p align="center"><strong>AI-Powered Mock Interview Platform — Be Prepared for Every Interview</strong></p>

<p align="center">
  <a href="#-quick-start">🚀 Quick Start</a> •
  <a href="#-features">✨ Features</a> •
  <a href="#-tech-stack">🧰 Tech Stack</a> •
  <a href="#-project-structure">📁 Structure</a> •
  <a href="#-usage-guide">📖 Usage</a> •
  <a href="#-api-overview">🔌 API</a>
</p>

<p align="center">
  <a href="./README.md">中文文档</a>
</p>

---

## 📖 Overview

Interview Agent is an LLM-powered AI mock interview platform supporting both **interviewer** and **candidate** perspectives. With RAG-based vector knowledge retrieval and web search capabilities, it delivers context-aware, intelligent conversations for every interview session.

### Core Scenarios

| Mode | Description |
|------|-------------|
| 🎯 **You are the Interviewer** | You act as interviewer, asking questions to the AI candidate. The AI draws from JD, resume, code files, and knowledge base to give informed answers |
| 🧑 **You are the Candidate** | You act as a job candidate, answering questions from the AI interviewer. AI generates questions from JD and resume; supports interview timer, question planning, progress tracking, and report generation |

---

## ✨ Features

- 🤖 **Dual-Mode AI Chat** — Seamlessly switch between interviewer & candidate modes with SSE streaming
- 🔑 **Frontend API Key Config** — Configure your DeepSeek API Key directly in the UI; key stored locally only
- ⏱️ **Interview Time Planning** — Set duration in candidate mode, auto-calculates question count with phase breakdown
- 🎯 **Practice Flow** — Candidate mode: AI asks → you answer → progress tracking → one-click report
- 🧑‍💻 **Coding Challenge Mode** — Tech positions only; intelligently selects LeetCode-style problems with difficulty adaptation
- 🎓 **Candidate Leveling** — Supports intern / new grad / experienced levels; auto-adjusts question difficulty
- 🔄 **Interview Rounds** — First / Second / HR round, each with tailored evaluation focus
- 📚 **RAG Knowledge Base** — Upload PDF / Word / text files; LangChain FAISS vector search enhances response quality
- 🌐 **Web Search** — DuckDuckGo integration for real-time technical information
- 📝 **Interview Reports** — Multi-dimensional evaluation (technical skills / communication / overall performance) with structured per-question assessment
- 🗂️ **Position Management** — Create positions, add multiple JDs, link knowledge bases, filter by JD
- 🎛️ **Model Selection** — Choose between DeepSeek V4 Pro / Flash, toggle thinking mode & reasoning effort
- 🔒 **Security** — CORS domain whitelist + FAISS index SHA-256 integrity verification
- 📐 **Context Window Management** — tiktoken precise token counting + LangChain trim_messages smart trimming
- 🎤 **Voice Input (STT)** — Hold to talk / Spacebar to record; faster-whisper streaming recognition with real-time text
- 🔊 **Voice Playback (TTS)** — One-click AI reply reading; Piper TTS Chinese voice synthesis
- 🎛️ **Flexible Voice Toggle** — Choose CPU/GPU at startup; Docker Profile on-demand; disabled by default, zero impact
- 🖥️ **Modern UI** — React + Ant Design 6 with responsive layout
- 🐳 **One-Click Deploy** — Local scripts / Docker Compose / Single container — three ways to launch


---

## 🚀 Quick Start

Pick one of three methods:

| Method | Command | Platform |
|--------|---------|----------|
| 📜 Local Script | `start.bat` / `./start.sh` | Windows / macOS / Linux |
| 🐳 Docker Compose | `docker-compose up -d` | All platforms |
| 📦 Single Container | `docker run` | All platforms |

> **First time?** Copy `.env.example` → `.env` and fill in your [DeepSeek API Key](https://platform.deepseek.com/)
> 
> **China mainland users**: First launch downloads the Embedding model (~90MB). `.env` includes `HF_ENDPOINT=https://hf-mirror.com` by default — no extra setup needed.

### Key Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API Key (required) |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | Default model |
| `AVAILABLE_MODELS` | `deepseek-v4-pro,deepseek-v4-flash` | Available model list |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model name |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace mirror (for China users) |
| `VECTOR_SEARCH_TOP_K` | `3` | RAG retrieval top-K documents |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Allowed frontend origins (comma-separated) |
| `FAISS_VERIFY_INTEGRITY` | `true` | FAISS index SHA-256 integrity check |
| `MAX_CONTEXT_TOKENS` | `800000` | Context window limit (tokens) |
| `DEEPSEEK_THINKING_ENABLED` | `true` | Enable thinking mode by default |
| `VOICE_ENABLED` | `false` | 🎤 Voice feature master switch |
| `STT_ENABLED` | `false` | Speech-to-Text (voice to text) |
| `TTS_ENABLED` | `false` | Text-to-Speech (text to voice) |
| `STT_MODEL` | `small` | Whisper model (base:140MB / small:480MB) |
| `STT_DEVICE` | `cpu` | Inference device (cpu / cuda) |
| `TTS_SPEED` | `1.0` | Speech rate (0.5-2.0) |

<details>
<summary><b>Method 1: Local Script (dev recommended)</b></summary>

**Windows** — Double-click `start.bat`

**macOS / Linux**:
```bash
chmod +x start.sh
./start.sh
```

The script automates: environment check → dependency install → start backend `:8000` + frontend `:5173` → open browser.
</details>

<details>
<summary><b>Method 2: Docker Compose (deploy recommended)</b></summary>

#### Prerequisites

- Docker 20.10+ & Docker Compose v2+
- DeepSeek API Key

#### Standard Deployment (with RAG)

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env and fill in DEEPSEEK_API_KEY

# 2. Launch
docker-compose up -d

# 3. Verify
docker-compose ps
```

Visit **http://localhost**

> First launch downloads the Embedding model (~90MB) via HuggingFace mirror. Startup takes ~2-3 minutes.

#### Lightweight Deployment (no RAG, for CUDA-less / low-resource environments)

```bash
# Skip vector knowledge base dependencies, reduce image size by ~2GB
SKIP_RAG=true RAG_ENABLED=false docker-compose up -d
```

> Core features (chat, interview simulation, report generation) work fully. Only knowledge base upload & RAG retrieval are unavailable.

#### Architecture

```
Browser → Nginx (:80) → /api/* reverse proxy → FastAPI (:8000)
                       → other paths → frontend static files
```

#### Common Commands

| Command | Description |
|---------|-------------|
| `docker-compose up -d` | Start (standard mode) |
| `SKIP_RAG=true RAG_ENABLED=false docker-compose up -d` | Start (no RAG) |
| `docker-compose down` | Stop & remove containers |
| `docker-compose down -v` | Stop & remove containers + volumes |
| `docker-compose logs -f backend` | View backend logs |
| `docker-compose restart backend` | Restart backend |
| `docker compose --profile cpu up` | Start (CPU voice mode) |
| `docker compose --profile gpu up` | Start (GPU voice mode) |
| `docker compose --profile voice up` | Start (full voice features) |

#### Voice Features

```bash
# Local dev: choose y at startup → select CPU/GPU → auto install deps + download models
start.bat   # or ./start.sh

# Docker: enable via Profile
docker compose --profile cpu up    # CPU voice
docker compose --profile gpu up    # GPU voice

# STT-only or TTS-only
docker compose --profile stt up    # STT only
docker compose --profile tts up    # TTS only
```

First run auto-downloads models (whisper ~480MB + Piper ~50MB).

#### Data Persistence

| Data | Location | Notes |
|------|----------|-------|
| FAISS vector index | `chroma_data` volume | RAG knowledge base index |
| Upload records / problem bank | `data` volume | `uploads.json`, `leetcode_problems.json` |
| STT models | `stt_models` volume | Whisper model files |
| TTS models | `tts_models` volume | Piper voice model files |
| Position data | `positions.json` | In-image, resets on rebuild |

</details>

<details>
<summary><b>Method 3: Single Container</b></summary>

```bash
# Build (without RAG)
docker build --build-arg SKIP_RAG=true -t interview-agent .

# Run
docker run -d \
  --name interview-agent \
  -p 8000:8000 \
  --env-file .env \
  -e RAG_ENABLED=false \
  -v interview-data:/app/data \
  interview-agent
```

Visit **http://localhost:8000**

> To include RAG, remove `--build-arg SKIP_RAG=true`, add `-e RAG_ENABLED=true` and `-v interview-chroma:/app/chroma_data`.

</details>

---

## 🧰 Tech Stack

### Backend
| Component | Technology |
|-----------|------------|
| Web Framework | FastAPI + Uvicorn |
| LLM | DeepSeek V4 Pro / Flash (OpenAI-compatible API) |
| Streaming | Server-Sent Events (SSE) |
| RAG Pipeline | LangChain LCEL + FAISS |
| Vector Store | langchain-community FAISS |
| Embedding | HuggingFace sentence-transformers (all-MiniLM-L6-v2) |
| Token Counting | tiktoken (cl100k_base) |
| Context Trimming | LangChain trim_messages |
| Prompt Templates | LangChain ChatPromptTemplate |
| Text Splitting | langchain-text-splitters RecursiveCharacterTextSplitter |
| Web Search | DuckDuckGo Search |
| Doc Parsing | PyMuPDF + python-docx |
| Validation | Pydantic v2 |

### Frontend
| Component | Technology |
|-----------|------------|
| Framework | React 19 + TypeScript |
| Build Tool | Vite 8 |
| UI Library | Ant Design 6 |
| Router | React Router 7 |
| State Mgmt | Zustand |
| Markdown | react-markdown + remark-gfm |

---

## 📁 Project Structure

```
interview-agent/
├── main.py                  # FastAPI entry point
├── config.py                # Environment config
├── requirements.txt         # Python dependencies
├── Dockerfile               # Multi-stage build (frontend + backend)
├── docker-compose.yml       # Docker Compose orchestration
├── start.bat                # Windows one-click launcher
├── start.sh                 # macOS/Linux one-click launcher
├── .env.example             # Environment template
├── positions.json           # Position data
│
├── routers/                 # API routes
│   ├── chat.py              #   Chat (SSE streaming)
│   ├── interview.py         #   Interview control (start/stop/report/plan)
│   ├── position.py          #   Position management
│   ├── upload.py            #   File upload
│   └── knowledge.py         #   Knowledge base
│
├── services/                # Business logic
│   ├── llm_client.py        #   DeepSeek client
│   ├── vector_store.py      #   LangChain FAISS vector store
│   ├── rag_pipeline.py      #   LCEL RAG retrieval pipeline
│   ├── chunker.py           #   Document chunking
│   ├── parser.py            #   File parsing (PDF/Word)
│   ├── agent_tools.py       #   Web search tools
│   ├── coding_problem.py    #   Coding challenge selector
│   ├── model_registry.py    #   Model registry
│   ├── position_store.py    #   Position persistence
│   └── upload_store.py      #   Upload persistence
│
├── utils/                   # Utilities
│   ├── context_manager.py   #   Context window management (tiktoken)
│   ├── prompt_loader.py     #   Prompt template loader (LangChain)
│   └── position_classifier.py  # Position type classifier
│
├── models/
│   └── schemas.py           # Pydantic data models
│
├── prompts/                 # System prompts
│   ├── interviewer.txt      #   Interviewer persona
│   ├── candidate.txt        #   Candidate persona
│   └── report.txt           #   Report generation
│
├── data/
│   └── leetcode_problems.json  # Coding problem bank
│
├── frontend/                # React frontend
│   ├── Dockerfile           #   Frontend image
│   ├── nginx.conf           #   Nginx config
│   └── src/
│       ├── api/             #   API client
│       ├── pages/           #   Pages
│       ├── components/      #   Components
│       ├── stores/          #   State
│       └── hooks/           #   Hooks
│
├── tests/                   # Tests
└── chroma_data/             # FAISS index storage
    └── faiss_indexes/       #   Per-collection directories
```

---

## 📖 Usage Guide

### You are the Interviewer

```
Create Position → Add JD → Upload Knowledge → Upload Resume/Code → Switch Mode → Ask AI Candidate
```

1. Create a position and add a job description in the "Positions" page
2. Upload relevant documents (tech specs, FAQs, etc.) in the "Knowledge Base" page
3. Upload a candidate's resume (PDF / Word) and code files in the "Upload" page
4. Switch to "AI Chat" page, select **🎯 You are the Interviewer** mode
5. Ask the AI candidate questions — the AI draws from JD, resume, code, and knowledge base for informed answers
6. After the session, go to "Report" page to generate an evaluation

### You are the Candidate

```
Create Position → Add JD → Upload Knowledge → Upload Resume → Set Duration → Calculate Questions → Start Practice → AI Asks, You Answer → Generate Report
```

1. Create a target position with its JD
2. Upload relevant documents and your resume in the "Knowledge Base" and "Upload" pages
3. Switch to "AI Chat" page, select **🧑 You are the Candidate** mode
4. Choose interview duration (15/30/45/60 min), click **Calculate** to get estimated question count
5. Click **Start Practice** — the AI interviewer automatically asks questions one by one
6. Answer each question; track progress in real-time (question N of M)
7. Click **End Practice** when done, then go to "Report" page to generate a multi-dimensional evaluation

### ChatRequest Parameters

```json
{
  "messages": [{"role": "user", "content": "Tell me about yourself"}],
  "mode": "interviewer",
  "position_name": "Frontend Engineer",
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

| Parameter | Type | Description |
|-----------|------|-------------|
| `mode` | `string` | `"interviewer"` or `"candidate"` |
| `position_name` | `string` | Linked position name, triggers RAG retrieval |
| `jd_id` | `string` | Specify a particular JD (empty = use all JDs) |
| `use_search` | `bool` | Enable web search |
| `coding_enabled` | `bool` | Enable coding challenge (candidate mode + tech positions only) |
| `model` | `string` | Model selection; defaults to `deepseek-v4-pro` |
| `thinking_enabled` | `bool` | Enable deep thinking mode |
| `reasoning_effort` | `string` | Reasoning depth: `"high"` / `"max"` |
| `api_key` | `string` | Frontend-configured DeepSeek API Key (optional, takes priority over .env) |
| `candidate_level` | `string` | Candidate level: `"intern"` / `"new_grad"` / `"experienced"` |
| `interview_round` | `string` | Interview round: `"first"` / `"second"` / `"hr"` |
| `interview_duration_minutes` | `int` | Total interview duration (minutes), affects time budget awareness |
| `interview_question_count` | `int` | Planned question count |

---

## 🔌 API Overview

| Module | Method | Path | Description |
|--------|--------|------|-------------|
| Chat | `GET` | `/chat/models` | List available models |
| Chat | `POST` | `/chat/stream` | SSE streaming chat |
| Position | `GET` `POST` | `/positions` | List / Create positions |
| Position | `GET` `PUT` `DELETE` | `/positions/{name}` | Position CRUD |
| Position | `POST` `PUT` `DELETE` | `/positions/{name}/jds` | JD management (multiple JDs) |
| Interview | `POST` | `/interview/start` | Start interview (assemble system prompt) |
| Interview | `POST` | `/interview/stop` | Stop interview |
| Interview | `POST` | `/interview/report` | Generate report (structured per-question assessment) |
| Interview | `POST` | `/interview/plan` | 🆕 Interview time planning (phase breakdown + dynamic replan) |
| Upload | `POST` | `/upload/resume` | Upload resume |
| Upload | `POST` | `/upload/code` | Upload code |
| Knowledge | `POST` | `/knowledge/upload` | Upload document |
| Knowledge | `GET` | `/knowledge/collections` | List collections |
| Knowledge | `DELETE` | `/knowledge/{name}` | Delete collection |
| Knowledge | `POST` | `/knowledge/search` | Vector search |

> Full API docs: visit **http://localhost:8000/docs** (Swagger) or **/redoc** after launching

---

## 🧪 Running Tests

```bash
pytest tests/ -v
```

---

## 🤝 Contributing

Issues and Pull Requests are welcome!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT © 2025
