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
| 🕴️ **Interviewer Mode** | Simulates a professional interviewer — generates targeted questions from job descriptions & knowledge bases, evaluates candidate responses, and produces interview reports. Supports setting interview duration with auto-calculated question count |
| 🧑‍💻 **Candidate Mode** | You ask questions, AI responds as a candidate — helps interviewers practice questioning techniques or quickly assess potential candidate performance |

---

## ✨ Features

- 🤖 **Dual-Mode AI Chat** — Seamlessly switch between interviewer & candidate modes with SSE streaming
- � **Frontend API Key Config** — Configure your DeepSeek API Key directly in the UI; key stored locally only
- ⏱️ **Interview Time Planning** — Set interview duration in candidate mode, auto-calculates question count
- 🎯 **Practice Flow** — Progress tracking + question counter, one-click report generation after practice
- �📚 **RAG Knowledge Base** — Upload PDF / Word / text files; FAISS vector search enhances response quality
- 🌐 **Web Search** — DuckDuckGo integration for real-time technical information
- 📝 **Interview Reports** — Multi-dimensional evaluation (technical skills / communication / overall performance)
- 🗂️ **Position Management** — Create positions, add JDs, link knowledge bases
- 🎛️ **Model Selection** — Choose between DeepSeek V4 Pro / Flash, toggle thinking mode
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

```bash
docker-compose up -d
```

Visit **http://localhost**

Architecture: `Nginx (:80)` → frontend static files + `/api/*` reverse proxy → `FastAPI (:8000)`
</details>

<details>
<summary><b>Method 3: Single Container</b></summary>

```bash
docker build -t interview-agent .
docker run -p 8000:8000 --env-file .env interview-agent
```

Visit **http://localhost:8000**

Three-stage build: Node compiles frontend → pip installs deps → FastAPI serves everything
</details>

---

## 🧰 Tech Stack

### Backend
| Component | Technology |
|-----------|------------|
| Web Framework | FastAPI + Uvicorn |
| LLM | DeepSeek V4 Pro / Flash |
| Streaming | Server-Sent Events (SSE) |
| Vector Store | FAISS + sentence-transformers |
| Embedding | all-MiniLM-L6-v2 |
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
│   ├── interview.py         #   Interview control
│   ├── position.py          #   Position management
│   ├── upload.py            #   File upload
│   └── knowledge.py         #   Knowledge base
│
├── services/                # Business logic
│   ├── llm_client.py        #   DeepSeek client
│   ├── vector_store.py      #   FAISS vector store
│   ├── chunker.py           #   Document chunking
│   ├── parser.py            #   File parsing
│   └── agent_tools.py       #   Search tools
│
├── prompts/                 # System prompts
│   ├── interviewer.txt      #   Interviewer persona
│   ├── candidate.txt        #   Candidate persona
│   └── report.txt           #   Report generation
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
└── tests/                   # Tests
```

---

## 📖 Usage Guide

### Interviewer Mode

```
Create Position → Add JD → Upload Knowledge → Upload Resume → Set Duration → Calculate Questions → Start Practice → Chat → Generate Report
```

1. Create a position and add a job description in the "Positions" page
2. Upload relevant documents (tech specs, FAQs, etc.) in the "Knowledge Base" page
3. Upload a candidate's resume (PDF / Word) in the "Upload" page
4. Switch to "AI Chat" page, select **AI Interviewer** mode
5. Choose interview duration (15/30/45/60 min), click **Calculate** to get question count
6. Click **Start Practice** — the AI automatically asks questions based on JD and knowledge base
7. Track progress in real-time (question N of M), click **End Practice** when done
8. Go to "Report" page to generate a multi-dimensional evaluation with one click

### Candidate Mode

```
Create Position → Add JD → Ask Questions → AI Responds
```

1. Create a target position with its JD
2. Switch to **I am a Candidate** mode and ask the AI candidate questions
3. Evaluate the AI's response quality to get familiar with potential candidate performance

### ChatRequest Parameters

```json
{
  "messages": [{"role": "user", "content": "Tell me about yourself"}],
  "mode": "interviewer",
  "position_name": "Frontend Engineer",
  "use_search": false,
  "model": "deepseek-v4-pro",
  "thinking_enabled": true,
  "reasoning_effort": "high",
  "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `mode` | `string` | `"interviewer"` or `"candidate"` |
| `position_name` | `string` | Linked position name, triggers RAG retrieval |
| `use_search` | `bool` | Enable web search |
| `model` | `string` | Model selection; defaults to `deepseek-v4-pro` |
| `thinking_enabled` | `bool` | Enable deep thinking mode |
| `reasoning_effort` | `string` | Reasoning depth: `"high"` / `"max"` |
| `api_key` | `string` | Frontend-configured DeepSeek API Key (optional, takes priority over .env) |

---

## 🔌 API Overview

| Module | Method | Path | Description |
|--------|--------|------|-------------|
| Chat | `GET` | `/chat/models` | List available models |
| Chat | `POST` | `/chat/stream` | SSE streaming chat |
| Position | `GET` `POST` | `/positions` | List / Create positions |
| Position | `GET` `PUT` `DELETE` | `/positions/{name}` | Position CRUD |
| Position | `POST` `PUT` `DELETE` | `/positions/{name}/jds` | JD management |
| Interview | `POST` | `/interview/start` | Start interview |
| Interview | `POST` | `/interview/stop` | Stop interview |
| Interview | `POST` | `/interview/report` | Generate report |
| Interview | `POST` | `/interview/plan` | 🆕 Interview time planning |
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
