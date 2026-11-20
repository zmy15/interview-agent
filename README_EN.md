<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React">
  <img src="https://img.shields.io/badge/TypeScript-6.0-3178C6?logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/DeepSeek-V4-536DFE?logo=openai&logoColor=white" alt="DeepSeek">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

<h1 align="center">🎯 Interview Agent</h1>

<p align="center">
  <a href="#-overview">Overview</a> •
  <a href="#-features">Features</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-configuration">Configuration</a> •
  <a href="#-usage-guide">Usage</a> •
  <a href="#-api-overview">API</a> •
  <a href="#-notes">Notes</a>
</p>

<p align="center">
  <a href="./README.md">中文文档</a>
</p>

---

## 📖 Overview

Interview Agent is an **LLM-powered mock interview platform**. It splits "interview preparation" into two freely switchable perspectives, and combines a RAG vector knowledge base with web search so every turn carries the context of the job JD, your resume and the knowledge base.

### Two Core Scenarios

| Mode | Description |
|------|-------------|
| 🎯 **You are the Interviewer** (`interviewer`) | You act as the interviewer and question the AI candidate. The AI answers using the JD, resume, code and knowledge base — handy for practising questioning and quickly validating a candidate's talking points |
| 🧑 **You are the Candidate** (`candidate`) | The AI plays the interviewer and questions you. It generates questions from the JD and resume, supports a timer, question planning and progress tracking, then produces a multi-dimensional report |

### Three Real-time Aids

Besides the mock practice, the project offers real-time help for **actual interviews** (all built on Windows capabilities):

---

## ✨ Features

**Chat & Interview**
- 🤖 Dual-mode AI chat with SSE streaming (reasoning chain and answer pushed on separate channels)
- ⏱️ Interview time planning: estimates question count and phase breakdown from duration + answer length + candidate level + interview round, with **dynamic replanning**
- 🎓 Candidate levels: intern / new grad / experienced, automatically adjusting difficulty and count
- 🔄 Interview rounds: first / second / HR (HR is capped at 30 minutes and excludes coding challenges)
- 🧑‍💻 Coding challenges: picked from the question bank by position type (candidate mode + tech positions only)
- 📝 Interview report: multi-dimensional evaluation (technical / communication / overall) with structured per-question assessment
- 🗂️ Question bank: hand-written questions, LeetCode import, three usage modes (strict / mixed / adaptive)
- 📎 Prompt documents: upload txt / md (also pdf / docx) and send them to the AI as background material
- 💬 Session history: full replay of past conversations, including reasoning chains and token counts

**Knowledge & Retrieval**
- 📚 RAG knowledge base: upload PDF / Word / text / code / project archives; FAISS vector search enriches answers
- 🌐 Web search: DuckDuckGo integration for up-to-date technical information
- 🗂️ Position management: multiple JDs per position, paste the first JD right at creation, pick which JD a conversation uses

**Platform & Experience**
- 🔐 User accounts: JWT auth (access + refresh) with per-user data isolation; one switch to **single-user mode** (no login)
- 📊 Analytics dashboard: overview stats, progress trends, weakness analysis, multi-session comparison
- 🎛️ Model selection: list fetched live from the official `GET /models` (not hard-coded), with thinking toggle and reasoning effort
- 🔒 Security: CORS whitelist, bcrypt password hashing, FAISS index SHA-256 integrity check
- 📐 Context management: exact tiktoken counting + smart trimming for long-context models
- ⚡ Prefix-cache friendly: context is fixed as "prompt → resume → JD → (optional RAG) → each turn", byte-identical across a session so server-side prefix caching keeps hitting
- 🖥️ UI customization: 7 colour presets plus custom background / text colour, with WCAG contrast hints
- 🪟 Standalone window mode: always-on-top, opacity, capture exclusion, global F8 hotkey — one window, nothing else
- 🐳 Multiple deployments: local scripts / Docker Compose / single container

> 🎤 **Voice features (STT / TTS) are all off by default** — enable them in `.env`; when disabled they have zero impact on the system.

---

## 🚀 Quick Start

### Prerequisites

| Item | Requirement |
|------|-------------|
| Python | 3.11+ |
| Node.js | 18+ (needed to build the frontend; CI uses 22) |
| DeepSeek API Key | [platform.deepseek.com](https://platform.deepseek.com/) |
| OS | Core features run on Windows / macOS / Linux; **screenshot answering, system audio capture and the standalone window are Windows-only** |

### Step 1: Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in at least:

```bash
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
JWT_SECRET=replace-with-a-long-random-string
```

> **China mainland users**: `.env.example` already points `HF_ENDPOINT` at `https://hf-mirror.com`, so the first launch downloads the embedding model (~90MB) without extra setup.
>
> You can also leave `DEEPSEEK_API_KEY` empty — enter it once in the UI (the key is stored encrypted in the server database, never in the browser), and the UI value takes precedence.

### Step 2: Choose a Launch Method

| Method | Command | Platform | Notes |
|--------|---------|----------|-------|
| 🪟 **Standalone window** (recommended on Windows) | `start_app.bat` or `python desktop.py` | Windows | Backend + frontend + voice services in one app window |
| 📜 **Local scripts** (recommended for development) | `start.bat` / `./start.sh` | All | Backend `:8000` + frontend `:5173` (hot reload) |
| 🐳 **Docker Compose** | `docker-compose up -d` | All | Nginx `:80` → backend `:8000` |
| 📦 **Single container** | `docker run` | All | Backend serves the frontend build directly |

#### Method 1: Local Scripts (development)

**Windows** — double-click `start.bat` (it only forwards to `start.ps1`, the logic lives in PowerShell; you can also run `.\start.ps1` directly)

**macOS / Linux**

```bash
chmod +x start.sh
./start.sh
```

The script automatically: checks Python / Node → **creates a `.venv` on first launch and installs dependencies into it** → creates `.env` → initialises the database → (optionally) configures voice → starts backend and frontend → opens the browser. Afterwards open <http://localhost:5173> for the UI and <http://localhost:8000/docs> for the API docs.

> Requires Python 3.11+. Installation is skipped when `requirements.txt` is unchanged; only the first launch (or a dependency change) downloads packages.

Startup asks whether to enable voice features (default `n`); answering `y` then asks for the STT device (CPU / GPU).

#### Method 2: Standalone Window (Windows)

```bash
# Recommended: double-click start_app.bat (it forwards to start_app.ps1, no terminal window)
.\start_app.ps1              # or run the PowerShell launcher directly
python desktop.py            # or bypass the launcher and pass your own flags
# or go through main.py (flags are forwarded)
python main.py --desktop
python main.py --desktop --no-topmost --width 1366 --height 768
```

The desktop build has the same features as the web build; only the form differs:

| | Web `start.bat` | Desktop `start_app.bat` |
|---|---|---|
| Backend | separate cmd window | inside the desktop process |
| Frontend | Vite dev server (5173, hot reload) | `dist` build served by the backend |
| Voice services | one cmd window each | inside the desktop process, **no windows** |
| Visible windows | 4 consoles + 1 browser | **a single window + tray icon** |

Default behaviours:

- **No login by default** (single-user mode, data belongs to the local account `desktop@local`). To bring back the login page, set `AUTH_REQUIRED=true` in `.env` or use `start_app.bat --auth-required true`.
- **No voice prompts by default** — whether voice is enabled is decided entirely by `VOICE_ENABLED` / `STT_ENABLED` / `TTS_ENABLED` in `.env`.
- **No terminal window at all.** Logs go to `logs/start_app.log` (launcher), `logs/desktop.log` (app) and `logs/app-stderr.log` (uncaught exceptions). Use `.\start_app.ps1 -Foreground` to watch logs live.
- **Tray icon** (on by default): click to show/hide the window, right-click for logs or exit; when hidden, the taskbar button is removed too, so no dead button is left behind. Use `-NoTray` to skip the tray.
- **Closing with X sends the app to the tray** instead of exiting (browser window mode cannot intercept closing, so X still exits).
- The standalone window requires a frontend build first; `start_app.ps1` rebuilds automatically when assets are missing or sources changed.

**Common launch flags**

| Flag | Default | Description |
|------|---------|-------------|
| `--host` / `--port` | `127.0.0.1` / `8000` | Listen address and port |
| `--auto-port` | `false` | Pick the next free port when the default is taken |
| `--reload` | `false` | Hot reload (development) |
| `--shell {auto,native,browser}` | `auto` | Window implementation, see the table below |
| `--window-title TEXT` | `Interview Agent — AI Mock Interview` | Window title |
| `--width` / `--height` | `1280` / `800` | Window size |
| `--topmost [BOOL]` / `--no-topmost` | `true` | Always on top |
| `--opacity N` | `1.0` | Window opacity `0.2`–`1.0` (percentage `20`–`100` also accepted) |
| `--zoom N` | `1.0` | UI zoom `0.5`–`2.0` (percentage also accepted) |
| `--capture-exclude [BOOL]` | `true` | Keep the window out of screenshots / recordings (native only) |
| `--click-through [BOOL]` | `false` | Mouse pass-through: clicks and wheel go to the window below, so you can edit text hidden behind the overlay. Toggle at runtime with **F9** or the tray menu (native only) |
| `--hide-taskbar [BOOL]` | `false` | Hide the taskbar button (defaults to `true` when `--tray` is on) |
| `--tray [BOOL]` | `false` | Show a system tray icon: click to toggle, right-click to exit |
| `--tray-notify [BOOL]` | `false` | Tray balloon hints (on register and when sent to tray). Off by default because Windows 11 renders them as notifications that cover content |
| `--close-to-tray [BOOL]` | follows `--tray` | X goes to tray instead of exiting (not interceptable in browser mode) |
| `--fullscreen [BOOL]` | `false` | Start fullscreen |
| `--app PATH` | — | Page to open on start, e.g. `--app /login` |
| `--browser PATH` | — | [browser mode] Browser executable |
| `--user-data-dir PATH` | `~/.interview-agent/desktop-profile` | [browser mode] Browser profile directory |
| `--debug` | `false` | [native mode] Open WebView devtools |
| `--hide-console [BOOL]` | `true` | Hide the launcher console after start. **Note**: ineffective with the Windows 11 default terminal (Windows Terminal); launching via `start_app.ps1` never shows a console |
| `--auth-required [BOOL]` | `false` | Require login; `true` restores the login page |
| `--no-console` | `false` | Do not print startup logs |
| `--open-timeout SEC` | `90` | Max seconds to wait for the service to be ready |

**Two window implementations**

| `--shell` | Engine | Always on top | Capture exclusion | Global F8 hotkey | Requires |
|-----------|--------|---------------|-------------------|------------------|----------|
| `native` (preferred by `auto`) | Edge WebView2 | ✅ | ✅ really works | ✅ fires even when unfocused | `pywebview` + WebView2 runtime |
| `browser` | System Edge / Chrome `--app` | ✅ | ❌ blocked across processes | ⚠️ only when focused | nothing (zero deps) |

> Without `pywebview` the app falls back to `browser` mode and keeps working — but a `browser`-mode window belongs to the browser process, so the OS security boundary prevents **capture exclusion and the global hotkey** (the hotkey only works while focused).

#### Method 3: Docker Compose

```bash
cp .env.example .env      # edit and fill in DEEPSEEK_API_KEY
docker-compose up -d
docker-compose ps
```

Open <http://localhost> (Nginx listens on port 80).

**Lightweight deployment (no RAG, for CUDA-less / low-resource hosts)**

```bash
SKIP_RAG=true RAG_ENABLED=false docker-compose up -d
```

> The image shrinks by roughly 2GB. Chat, mock interviews and reports work fully; only knowledge-base upload and RAG retrieval are unavailable.

**Voice features (via profiles)**

```bash
docker compose --profile cpu up     # CPU voice (STT + TTS)
docker compose --profile gpu up     # GPU voice
docker compose --profile stt up     # STT only
docker compose --profile tts up     # TTS only
docker compose --profile voice up   # full voice stack
```

Models are downloaded on first use (Whisper ~200MB + Piper ~50MB) and persisted in the `stt_models` / `tts_models` volumes.

**Service and routing layout**

```
Browser → Nginx (:80) ─┬─ /api/*     → proxy → FastAPI (backend:8000)
                       ├─ /api/stt/* → proxy → STT service (stt:8000)
                       ├─ /api/tts/* → proxy → TTS service (tts:8000)
                       └─ anything else → frontend static files (SPA fallback to index.html)
```

**Common commands**

| Command | Description |
|---------|-------------|
| `docker-compose up -d` | Start (standard mode) |
| `docker-compose down` | Stop and remove containers |
| `docker-compose down -v` | Stop and remove containers + volumes (**wipes data**) |
| `docker-compose logs -f backend` | Follow backend logs |
| `docker-compose restart backend` | Restart the backend |

#### Method 4: Single Container

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

Open <http://localhost:8000>.

> To include RAG, drop `--build-arg SKIP_RAG=true` and add `-e RAG_ENABLED=true` plus `-v interview-chroma:/app/chroma_data`.

### Step 3: Create an Account

The web build needs a one-time sign-up (email + password, at least 6 characters). The desktop build skips login by default.

---

## ⚙️ Configuration

Everything is configured through `.env` in the project root (template: [.env.example](.env.example)), read by [config.py](config.py). **Command-line flags override `.env`**, and normal-chat UI choices (model, thinking toggle, reasoning effort) override the `.env` defaults; screenshot answering has its own thinking setting and ignores the UI thinking toggle.

### Model & LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | DeepSeek API Key (may be left empty and set in the UI) |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API base URL |
| `DEEPSEEK_MODEL` | `deepseek-v4-pro` | Default model |
| `DEEPSEEK_THINKING_ENABLED` | `true` | Enable thinking mode by default |
| `DEEPSEEK_REASONING_EFFORT` | `high` | Reasoning effort: `low` (fast, cheap) / `high` (official default) / `max` (most thorough) |
| `AVAILABLE_MODELS` | `deepseek-v4-pro,deepseek-v4-flash` | **Fallback only**: normally fetched from the official `GET /models` |
| `MAX_CONTEXT_TOKENS` | `1000000` | Total context window budget (tokens) |
| `SYSTEM_RESERVED_TOKENS` | `16000` | Tokens reserved for system messages |
| `PREFIX_CACHE_MAX_ENTRIES` | `64` | How many sessions' stable prefixes to cache |
| `PREFIX_CACHE_MAX_TOKENS` | `200000` | Token cap for one stable prefix; beyond it, nothing is cached |
| `PREFIX_CACHE_TTL_SECONDS` | `1800` | Stable-prefix cache lifetime (seconds) |
| `PROMPT_DOC_MAX_CHARS` | `80000` | Max characters kept per attached document (extra is truncated) |
| `PROMPT_DOC_MAX_TOTAL_CHARS` | `200000` | Combined character cap for all attached documents |
| `PROMPT_DOC_MAX_FILES` | `8` | Max number of attached documents |

### RAG Knowledge Base

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_ENABLED` | `true` | Master switch for RAG (off = no knowledge context in chat) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model name |
| `HF_ENDPOINT` | `https://hf-mirror.com` | HuggingFace mirror (a must in mainland China) |
| `HF_HOME` | `./hf_cache` | Model cache directory |
| `CHROMA_PERSIST_PATH` | `./chroma_data` | Root of the vector index storage (`faiss_indexes/` inside) |
| `VECTOR_SEARCH_TOP_K` | `3` | Documents returned per retrieval |
| `FAISS_VERIFY_INTEGRITY` | `true` | FAISS index SHA-256 integrity check (keep on in production) |

> RAG needs extra packages: `pip install -r requirements-rag.txt` (`faiss-cpu` + `sentence-transformers` + `langchain-huggingface`). **The app still starts without them** — knowledge-base upload and retrieval are simply unavailable (the startup log says so).

### Auth & Database

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTH_REQUIRED` | `true` | `true` = login required, data isolated per user; `false` = single-user mode without login |
| `JWT_SECRET` | `change-me-...` | **Must be replaced** with a long random string in production |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime (minutes) |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `30` | Refresh token lifetime (days) |
| `FREE_DAILY_INTERVIEW_LIMIT` | `10` | Daily interview limit for free users |
| `DB_TYPE` | `sqlite` | `sqlite` (development) / `postgresql` (production) |
| `DATABASE_URL` | — | Full connection string; overrides every `DB_*` below |
| `DB_HOST` / `DB_PORT` | `localhost` / `5432` | PostgreSQL host and port |
| `DB_USER` / `DB_PASSWORD` | `interview` / — | PostgreSQL credentials |
| `DB_NAME` | `interview_platform` | Database name |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | `10` / `20` | Connection pool size and overflow |
| `DB_ECHO` | `false` | Print SQL statements |

> The SQLite file lives at `data/interview_platform.db` (absolute path, independent of the working directory).

### Service & Security

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` / `PORT` | `127.0.0.1` / `8000` | Listen address and port (local only by default) |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173` | Allowed frontend origins, comma-separated |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

> ⚠️ With `allow_credentials=True`, CORS must not use `*` — list concrete origins. Set your real domain in production.

### Screenshot Answering

| Variable | Default | Description |
|----------|---------|-------------|
| `SCREENSHOT_ENABLED` | `true` | Master switch (off = routes not registered, UI says unavailable) |
| `SCREENSHOT_VISION_MODEL` | empty | Preferred vision model; empty = first image-capable model on the account |
| `SCREENSHOT_DIR` | `screenshots` | Where captures are saved |
| `SCREENSHOT_MAX_IMAGE_EDGE` | `0` | Longest edge of the uploaded image; `0` keeps the monitor's native resolution |
| `SCREENSHOT_MAX_TOKENS` | `-1` | Max tokens per answer; `-1` omits `max_tokens` and sets no local limit |
| `SCREENSHOT_THINKING_ENABLED` | `true` | Whether screenshot Q&A uses thinking mode; the normal-chat toggle has no effect |
| `SCREENSHOT_SAVE` | `true` | Keep every capture on disk |

### System Audio Capture

| Variable | Default | Description |
|----------|---------|-------------|
| `SYSTEM_AUDIO_ENABLED` | `false` | Master switch (off = `/system-audio` routes not registered) |
| `SYSTEM_AUDIO_DEVICE` | empty | Capture device id; empty = system default playback device |
| `SYSTEM_AUDIO_BLOCK_MS` | `100` | Audio block length read from the loopback (ms) |
| `SYSTEM_AUDIO_AUTOSTART` | `true` | Start capturing when the service boots |
| `SYSTEM_AUDIO_TRANSCRIPT_BUFFER` | `200` | Transcription lines kept in memory |
| `SYSTEM_AUDIO_STT_TIMEOUT` | `30` | Timeout for connecting to the STT service (s) |
| `SYSTEM_AUDIO_STT_PING_TIMEOUT` | `120` | STT WebSocket ping timeout (s) |

### Voice (STT / TTS)

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_ENABLED` | `false` | Master switch for voice |
| `STT_ENABLED` | `false` | Speech-to-text |
| `TTS_ENABLED` | `false` | Text-to-speech |
| `STT_BACKEND` | `qwen3_asr` | Recognition backend: `qwen3_asr` (better Chinese) / `faster_whisper` (legacy Whisper pipeline) |
| `STT_QWEN_MODEL` | `Qwen/Qwen3-ASR-0.6B` | Qwen3-ASR weights: HF repo id or local directory (relative paths resolve from the project root). 1.7B is more accurate but needs ~4GB VRAM |
| `STT_LANGUAGE` | `auto` | `auto` = let Qwen detect the language (better for mixed CN/EN) / `zh` = force Chinese |
| `STT_QWEN_MAX_NEW_TOKENS` | `256` | Max tokens generated per chunk by Qwen3-ASR |
| `STT_MODEL` | `base` | Whisper model (only with `STT_BACKEND=faster_whisper`): `tiny` / `base` / `small` / `medium` / `large-v3-turbo` |
| `STT_DEVICE` | `cpu` | Inference device: `cpu` / `cuda`. Whisper needs **CUDA 12** (cuBLAS 12 + cuDNN 9); Qwen needs a **CUDA build of torch** |
| `STT_COMPUTE_TYPE` | `int8` | Quantization: `int8` / `float16` / `int8_float16` (empty = auto: GPU→float16, CPU→int8) |
| `STT_SERVICE_URL` | `http://stt:8000` | STT service URL (`http://localhost:8001` when running locally) |
| `STT_WS_URL` | `ws://stt:8000/stream` | STT WebSocket URL |
| `STT_DOCKERFILE` | `Dockerfile` | `Dockerfile` (CPU) / `Dockerfile.gpu` (GPU) |
| `VAD_SILENCE_TIMEOUT` | `1.0` | VAD silence timeout (s) |
| `STT_CHUNK_MAX_SECONDS` | `25` | Hard chunk ceiling for continuous speech (s) |
| `STT_CHUNK_OVERLAP_SECONDS` | `0.5` | Overlap between chunks when hard-cutting (s) |
| `STT_CHUNK_CONTEXT_CHARS` | `120` | Cross-chunk context length (characters) fed from the previous chunk |
| `TTS_VOICE` | `zh_CN-huayan-medium` | Piper Chinese voice model |
| `TTS_SPEED` | `1.0` | Speech rate (`0.5`–`2.0`) |
| `TTS_SERVICE_URL` | `http://tts:8000` | TTS service URL (`http://localhost:8002` when running locally) |
| `TTS_WS_URL` | `ws://tts:8000/stream` | TTS WebSocket URL |

### Standalone Window

| Variable | Default | Description |
|----------|---------|-------------|
| `DESKTOP_MODE` | `false` | Start in standalone-window mode (set automatically by `desktop.py`) |
| `DESKTOP_WIDTH` / `DESKTOP_HEIGHT` | `1280` / `800` | Window size |
| `DESKTOP_TOPMOST` | `true` | Always on top |
| `DESKTOP_CAPTURE_EXCLUDE` | `true` | Keep the window out of screen capture (native only) |
| `DESKTOP_HIDE_TASKBAR` | `false` | Hide the taskbar button |
| `DESKTOP_OPACITY` | `1.0` | Window opacity |
| `DESKTOP_ZOOM` | `1.0` | UI zoom |
| `DESKTOP_BROWSER` | empty | Browser path (browser mode only); empty = auto-detect Edge / Chrome |

---

## 📖 Usage Guide

### Scenario 1: You are the Interviewer

```
Create position → Paste JD → Upload knowledge → Upload resume/code → Switch to "You are the Interviewer" → Ask the AI candidate
```

1. Create a position on the **Positions** page — you can paste its JD in the same dialog (or leave it empty and add it later via **Manage JD**)
2. Upload reference documents (tech specs, FAQs…) on the **Knowledge Base** page
3. Upload the candidate's resume (PDF / Word) and code files on the **Upload** page
4. Open **AI Chat** and pick the **🎯 You are the Interviewer** mode
5. Ask the AI candidate questions — it answers using the JD, resume, code and knowledge base
6. When done, generate the evaluation on the **Report** page

### Scenario 2: You are the Candidate

```
Create position → Paste JD → Upload knowledge → Upload resume → Set duration → Estimate questions → Start practice → Answer → Generate report
```

1. Create the target position and fill in its JD
2. Upload knowledge-base documents and your resume
3. Open **AI Chat** and pick the **🧑 You are the Candidate** mode
4. Choose the duration (15 / 30 / 45 / 60 minutes) and click **Estimate** for the expected question count
5. Click **Start practice** and the AI interviewer asks questions one by one
6. Answer in the input box; progress (question N of M) is shown live
7. Click **End practice** and generate the multi-dimensional evaluation on the **Report** page

### Scenario 3: Real-time Aids

- **Screenshot answering**: click the **Screenshot** button right of the input box on the AI Chat page, or press **`F8`**. The capture follows the current conversation and is sent together with anything you typed in the input box (only this one image), with the answer rendered straight into the chat.
- **System audio transcription**: enable it in **Settings → Listen to system audio** (or set `SYSTEM_AUDIO_ENABLED=true`) to have whatever your computer plays transcribed live.
- **Voice input / playback**: once voice is enabled, a record button appears in the input box and a read-aloud button appears under AI replies.

### Question Bank Modes

When you pick bank questions for a conversation, you also choose how strictly the AI must follow them:

| Mode | Description |
|------|-------------|
| `strict` | The AI must read out the bank questions verbatim, in order — no edits, skips or self-written questions |
| `mixed` (default) | Bank questions are mandatory and all must be asked; the AI may add up to 2 follow-ups of its own |
| `adaptive` | The bank is a reference: wording, difficulty and order may change, but the core assessment points stay |

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
  "interview_question_count": 10,
  "prompt_documents": [
    {"name": "personal.md", "text": "Experience / project details…"},
    {"name": "project.md", "text": "Architecture and key technical points…"}
  ],
  "question_bank_ids": [],
  "question_bank_mode": "mixed"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | `string` | `null` | `"interviewer"` or `"candidate"` |
| `position_name` | `string` | `null` | Linked position; **also triggers RAG retrieval** (empty = no retrieval) |
| `jd_id` | `string` | `null` | Which JD to use (empty = all JDs) |
| `use_search` | `bool` | `false` | Enable web search |
| `coding_enabled` | `bool` | `false` | Enable coding challenges (**only with `mode="candidate"`**) |
| `model` | `string` | `null` | Override the default model |
| `thinking_enabled` | `bool` | `null` | Override the default thinking toggle |
| `reasoning_effort` | `string` | `null` | `"low"` / `"high"` / `"max"` |
| `api_key` | `string` | `null` | Key supplied by the client; takes precedence over `.env` |
| `resume_text` | `string` | `null` | Resume text |
| `code_context` | `string` | `null` | Code text (interviewer mode only) |
| `candidate_level` | `string` | `null` | `"intern"` / `"new_grad"` / `"experienced"` |
| `interview_round` | `string` | `null` | `"first"` / `"second"` / `"hr"` |
| `interview_duration_minutes` | `int` | `30` | Total duration, drives the time budget awareness |
| `interview_question_count` | `int` | `0` | Planned question count (0 = default 8) |
| `interview_coding_min` | `int` | `0` | Minutes reserved for coding challenges |
| `prompt_notes` | `string` | `null` | Extra instructions from the PromptEditor, appended to the system prompt |
| `prompt_documents` | `{name,text}[]` | `null` | Background documents sent with the prompt (placed after system, before the dialogue) |
| `question_bank_ids` | `string[]` | `null` | Selected question-bank IDs |
| `question_bank_mode` | `string` | `"mixed"` | Question-bank mode: `strict` / `mixed` / `adaptive` |

### Question Count & Time Planning

Clicking **Estimate** (or calling `POST /interview/plan`) derives the question count from **duration, answer length, candidate level and interview round**, split into self-introduction, technical Q&A, coding and reverse-question phases.

- The count is clamped to 2 – 30; HR rounds are capped at 30 minutes and skip coding challenges.
- During practice the plan is **re-planned dynamically**, adjusting the remaining count and current phase from elapsed time and answered questions.

---

## 🔌 API Overview

Backend routes are registered **twice**: without a prefix (`/chat/stream`) and with `/api` (`/api/chat/stream`). That is why the Vite dev server strips `/api` and proxies to `:8000`.

> Interactive docs: after launching, open <http://localhost:8000/docs> (Swagger) or `/redoc`.

### Chat & Interview

| Module | Method | Path | Description |
|--------|--------|------|-------------|
| Chat | `GET` | `/chat/models` | Available models (`?refresh=true` bypasses the cache) |
| Chat | `POST` | `/chat/stream` | SSE streaming chat |
| Interview | `POST` | `/interview/start` | Start an interview (assembles the system prompt) |
| Interview | `POST` | `/interview/stop` | Stop the interview |
| Interview | `POST` | `/interview/report` | Generate the report (structured per-question assessment) |
| Interview | `POST` | `/interview/plan` | Time planning (phase breakdown + dynamic replanning) |

**SSE frame format**: each frame is `data: {"type": "...", "content": "..."}`, where `type` is `reasoning` (chain of thought) / `content` (answer) / `system_prefix` (stable prefix, see below) / `error`; the stream ends with `data: [DONE]`.

The `system_prefix` frame carries `content` (the whole system text) and `fingerprint`, and is **only sent on the first turn, or when the backend finds the client copy is stale**. The frontend stores it per mode (not in the message list, not persisted) and sends it back as `messages[0]` on later turns; if the backend compares it byte for byte and it matches, it is reused — so "prompt + resume + JD" stays identical for the whole session. The response header also carries `X-Prefix-Fingerprint` to line the `fp=` in logs up with a session.

### Positions / Question Bank / Upload / Knowledge

| Module | Method | Path | Description |
|--------|--------|------|-------------|
| Position | `GET` `POST` | `/positions` | List / create a position (may include its first JD) |
| Position | `GET` `PUT` `DELETE` | `/positions/{name}` | Position detail / update / delete |
| Position | `POST` `PUT` `DELETE` | `/positions/{name}/jds` | JD management (multiple JDs per position) |
| Question bank | `GET` `POST` | `/question-bank/` | List / add questions |
| Question bank | `GET` `PUT` `DELETE` | `/question-bank/{id}` | Question detail / update / delete |
| Question bank | `POST` | `/question-bank/import/leetcode` | Bulk import from LeetCode |
| Question bank | `GET` | `/question-bank/categories/list` | Category list |
| Upload | `POST` | `/upload/resume` | Upload a resume |
| Upload | `POST` | `/upload/code` | Upload code |
| Upload | `POST` | `/upload/project` | Upload a project (parses structure and tech stack) |
| Upload | `POST` | `/upload/document` | Upload a prompt document (text only, not stored) |
| Upload | `GET` `DELETE` | `/upload/files` | List / clear upload records |
| Upload | `GET` `DELETE` | `/upload/files/{id}` | One record's detail / delete it |
| Knowledge | `POST` | `/knowledge/upload` | Upload a document and index it |
| Knowledge | `GET` | `/knowledge/collections` | List all knowledge bases |
| Knowledge | `GET` | `/knowledge/search` | Vector search (`top_k` 1–20) |
| Knowledge | `DELETE` | `/knowledge/collections/{name}` | Delete a knowledge base |
| Knowledge | `GET` `POST` | `/knowledge/rag-status` `rag-toggle` | Query / toggle RAG at runtime |

### Sessions / Analytics / Auth

| Module | Method | Path | Description |
|--------|--------|------|-------------|
| Session | `GET` | `/sessions/` | Past sessions |
| Session | `GET` | `/sessions/{id}` | Session detail + message replay + QA records + report |
| Session | `DELETE` | `/sessions/{id}` | Delete a session |
| Analytics | `GET` | `/analytics/dashboard` | Overview dashboard |
| Analytics | `GET` | `/analytics/progress` | Progress trends (`7d` / `30d` / `90d`) |
| Analytics | `GET` | `/analytics/weakness` | Weakness analysis and suggestions |
| Analytics | `GET` | `/analytics/comparison` | Multi-session comparison |
| Analytics | `GET` | `/analytics/stats` | Aggregate statistics |
| Auth | `GET` | `/auth/mode` | Current auth mode (no token needed) |
| Auth | `POST` | `/auth/register` `login` `refresh` | Register / log in / refresh token |
| Auth | `GET` `PUT` | `/auth/me` | Current user / update profile |

### Real-time Aids (conditionally registered)

| Module | Method | Path | Description |
|--------|--------|------|-------------|
| Screenshot | `GET` | `/screenshot/info` | Capture capability, monitors and vision-model info |
| Screenshot | `POST` | `/screenshot/capture` | Capture the primary monitor and let the vision model answer (optional `messages` continue the conversation; only one image per request) |
| System audio | `GET` | `/system-audio/info` `devices` `status` | Capability / device list / running status |
| System audio | `POST` | `/system-audio/start` `stop` `clear` | Start / stop capture / clear transcripts |
| System audio | `GET` | `/system-audio/transcript` | Incremental transcripts (`?since=<seq>`) |
| Voice | `GET` | `/stt/health` `/tts/health` | Microservice health checks |
| Voice | `POST` | `/stt/transcribe` `/tts/synthesize` | Batch recognition / synthesis (fallback endpoints) |

> Screenshot and system-audio routes are **registered only when enabled**: with `SCREENSHOT_ENABLED=false` or `SYSTEM_AUDIO_ENABLED=false` they do not exist. In that case `/api/*` 404s return a **structured JSON hint** (usually "the feature switch is off") instead of HTML that makes the frontend fail in `JSON.parse`.

---

## 📷 Screenshot Answering

Click the **Screenshot** button (or press **`F8`**) right of the input box on the **AI Chat** page: the **primary monitor** is captured and handed to a vision model to extract and answer the question, with the answer shown in the chat.

**Prerequisites**

| Item | Requirement |
|------|-------------|
| OS | Windows 10 2004 (build 19041) or later |
| Python package | `windows-capture` (installed with `requirements.txt`) |
| Model | Must accept image input |

**Usage notes**

- The capture uses the model selected in the **model selector**; if it does not accept images you get a clear hint and the image is **not** sent to a text-only model (those don't error — they make up an answer).
- Captures **continue the current conversation**: earlier messages are sent as plain-text context (at most the latest 20 messages / 12000 characters, dropping the oldest), so you can chat a couple of turns, say "continuing the previous question", then press F8.
- Each request sends **exactly one image** — the one just captured; history is always text, old images are never re-sent.
- The reply contains **only the answer**: no restating of the question, no "recognised question" or "uncertainty" sections. Add extra requirements in the input box if needed.
- The `📷 Screenshot · size · elapsed · model` line above the message is UI state (`Message.meta`) and **never enters the context**.
- You can type an instruction first (e.g. "just the answer, no explanation"); it is sent together with the capture, so "type the requirement, then press F8" works.
- In **standalone window mode**, F8 is a system-wide global hotkey that **fires even when the window is unfocused** (exactly what screenshotting needs); in browser mode it only works while focused.
- In standalone window mode the app excludes itself from capture, so it never photographs itself.
- If another program already owns the hotkey, it degrades to an in-window shortcut.

> **About thinking and output length**: screenshot answering enables thinking by default, and the normal-chat thinking toggle does not affect it. With `SCREENSHOT_MAX_TOKENS=-1`, the app does not send `max_tokens` and applies no local output limit; the model or server may still enforce its own hard limit. If a reply is truncated, the UI says so explicitly.

---

## 🎧 System Audio Transcription

The mirror image of screenshot answering: screenshots grab "what is on screen", system audio grabs "what the speakers play". In an interview the other side's questions often come from a meeting app, a video or a web page, which **a microphone cannot hear**. This feature captures the speaker device directly through the Windows WASAPI loopback and transcribes it live.

**Prerequisites (all three required)**

1. `SYSTEM_AUDIO_ENABLED=true` (otherwise the routes are not registered);
2. `VOICE_ENABLED=true` or `STT_ENABLED=true`, and the **STT service is running** (`docker compose --profile stt up`, or run `stt_service` locally);
3. `STT_SERVICE_URL` points at that service (`http://localhost:8001` when running locally).

> Windows only. When STT is not ready, capture keeps running but produces no text; the status explains why, and it reconnects once STT is up.

---

## 🧪 Tests & Static Checks

```bash
pytest tests/ -v      # backend tests
ruff check .          # Python static checks (optional)
```

Tests marked `windows_only` / `slow` are skipped on Linux CI; CI also runs `npm run build` for the frontend (which includes `tsc` type checking).

Optionally install [pre-commit](https://pre-commit.com) (`pip install pre-commit && pre-commit install`) to check config syntax, large files, line endings, trailing whitespace and private keys before committing; [pre-commit.ci](https://pre-commit.ci) runs the same hooks on pull requests.

---

## 🔧 Tech Stack

### Backend

| Component | Technology |
|-----------|------------|
| Web framework | FastAPI + Uvicorn |
| LLM | DeepSeek V4 Pro / Flash (OpenAI-compatible API) |
| Streaming | Server-Sent Events (SSE) |
| Validation | Pydantic v2 |
| ORM | SQLAlchemy 2.0 Async (SQLite / PostgreSQL) |
| Auth | python-jose (JWT) + passlib/bcrypt |
| RAG pipeline | LangChain LCEL + FAISS |
| Embedding | sentence-transformers (`all-MiniLM-L6-v2`) |
| Token counting / trimming | tiktoken (cl100k_base) |
| Document parsing | PyMuPDF + python-docx |
| Web search | DuckDuckGo Search |
| STT | Qwen3-ASR-0.6B (transformers) / faster-whisper (CTranslate2), switchable + Silero VAD |
| TTS | Piper TTS |

### Frontend

| Component | Technology |
|-----------|------------|
| Framework | React 19 + TypeScript 6 |
| Build tool | Vite 8 |
| UI library | Ant Design 6 |
| Router | React Router 7 |
| State management | Zustand 5 |
| Markdown | react-markdown + remark-gfm + react-syntax-highlighter |

---

## ⚠️ Notes

### General

- **The first launch downloads models.** The RAG embedding model is ~90MB (mirror configured by default); voice models are ~250MB (Whisper + Piper). Keep the network available.
- **Ports**: backend `8000`, frontend `5173`, local voice `8001` (STT) / `8002` (TTS), Docker frontend `80`. `start.bat` checks for conflicts and prints the occupying PID; `desktop.py` can shift ports with `--auto-port`.
- **`.env` is not committed** (already in `.gitignore`) — never commit a `.env` that contains keys.
- **Replace `JWT_SECRET`.** The default is a public placeholder; using it in production is as good as no signature protection.
- **CORS must not use `*`** because `allow_credentials=True` is on — list concrete origins and set real domains in production.
- **Single-user mode is not just "hide the login page".** With `AUTH_REQUIRED=false`, every token-protected API (positions / question bank / sessions / uploads / analytics) automatically uses the fixed local account `desktop@local`, so the desktop build keeps full parity with the web build. That account is created with the tables, its `hashed_password` is a one-way placeholder, and **it cannot be used to log in with a password**.
- **SQLite suits single-machine use.** For multi-user or high concurrency, switch to `DB_TYPE=postgresql` and configure `DB_*`.

### RAG & Models

- **RAG dependencies are heavy** (`sentence-transformers` pulls in `torch`, ~2GB). If you don't need the knowledge base, set `RAG_ENABLED=false` and skip `requirements-rag.txt`; for Docker use `SKIP_RAG=true`.
- **RAG enabled but dependencies missing** still starts, but knowledge-base upload / list / search return **503**, while file indexing and RAG injection silently skip — easy to misread as "it works but finds nothing".
- **Keep `FAISS_VERIFY_INTEGRITY` on in production.** The index's `index.pkl` is pickled; this module verifies its SHA-256 to prevent tampering. If verification fails and you trust the file, delete the matching `.sha256` and reload.
- **Knowledge-base directory names are rewritten.** Non-ASCII characters in position names become underscores with a `kb_` prefix (e.g. "前端工程师" → `kb__kb`); this is normal and the UI still shows the original name.
- **`/knowledge/rag-toggle` only affects the current process**; a restart restores the `.env` value.
- **The model list comes from the remote API.** If `GET /models` is unreachable it falls back to `AVAILABLE_MODELS` in `.env`; in that case all models are marked as not image-capable and screenshot answering reports itself unavailable.
- **Coding-challenge selection is randomised** — the same input may yield different problems.

### API Behaviour

- **`/chat/stream` only reads `api_key` from the request body**, not the `X-DEEPSEEK-API-KEY` header (`/chat/models` reads both). Passing the key only as a header silently falls back to `DEEPSEEK_API_KEY` from `.env`.
- **`code_context` currently has no effect**; code and project context always come from RAG retrieval.
- **`position_name` also triggers RAG**: only when it is set is that position's knowledge base searched.
- **Position names are limited** to 2–50 characters, allowing letters, digits, Chinese, underscores, hyphens **and spaces** (no dots, slashes and similar). Duplicate names for the same user return **409**.
- **A position can be created together with its first JD** via the `jd_content` field of `POST /positions` (empty = no JD).
- **`position_type` is fixed when the position is created.** "Tech support" and "design / UI / UX" count as **non-technical**, so coding challenges stay disabled there.
- **`/interview/report` returns HTTP 200 even on failure**, with `Report generation failed: ...` in the body — callers must detect it.

### Upload Limits & Formats

| Endpoint | Size limit | Accepted formats | Error |
|----------|-----------|------------------|-------|
| `/upload/resume` | **5MB** | `.pdf` `.docx` `.doc` `.txt` | 413 |
| `/upload/code` | **2MB** | `.py` `.js` `.ts` `.jsx` `.tsx` `.java` `.go` `.cpp` `.c` `.h` `.hpp` `.rs` `.rb` `.php` `.swift` `.kt` `.scala` `.cs` `.vue` `.html` `.css` `.scss` `.sql` `.sh` `.bash` `.yaml` `.yml` `.json` `.xml` `.md` `.r` `.m` | 413 |
| `/upload/project` | **50MB** | `.zip` `.tar.gz` `.tgz` `.tar.bz2` `.tar.xz` `.tar` `.7z` (`.7z` needs `py7zr`) | 413 |
| `/upload/document` | **5MB** | `.txt` `.md` `.markdown` `.text` `.rst` `.csv` `.tsv` `.json` `.yaml` `.yml` `.xml` `.log` `.ini` `.pdf` `.docx` | 413 |
| `/knowledge/upload` (`doc_type=faq`) | **10MB** | same as resume (**no `.md`**) | 413 |
| `/knowledge/upload` (`doc_type=code`) | **10MB** | same as code | 413 |
| `/knowledge/upload` (`doc_type=project`) | **50MB** | same as archives | 413 |

Other conventions:

- **Stored text is truncated to 100KB**, while the upload response returns the full text: right after uploading the frontend has everything, but later reads only return the 100KB version.
- Knowledge-base search accepts `top_k` **1–20**; out-of-range values silently fall back to 3.
- Parse failures return **422**; unsupported extensions return **400**.
- Only **code** and **projects** are indexed into the vector store (resumes are not).
- `/upload/document` only returns the extracted text (GBK-encoded txt is detected automatically); it writes no upload record and builds no index, and over-long content is truncated with a marker at the end.
- Project parsing skips system junk files and infers the tech stack (Python / React / Java / Go / Rust / Docker…).

### Windows-only Features

| Feature | Dependency | When missing |
|---------|------------|--------------|
| Screenshot answering | `windows-capture` | The API returns install instructions instead of a 500 |
| System audio capture | `soundcard` (WASAPI loopback) | A clear "Windows only" message |
| Standalone window | `pywebview` + WebView2 runtime | Falls back to a browser `--app` window (capture exclusion stops working) |

> These dependencies carry platform markers in `requirements.txt`, so non-Windows installs skip them automatically; the features are unavailable but the service runs fine.

### Standalone Window Mode

- **A frontend build must exist**, otherwise `/` degrades to plain JSON health info — run `cd frontend && npm run build` first.
- **`--capture-exclude` only takes effect in native mode**; browser mode cannot do it across processes (the setting shows as disabled in the UI).
- **`--opacity` bottoms out at 20%** so the window cannot become unusably faint.
- Window options (always-on-top / opacity / zoom / capture exclusion / hide taskbar) can all be **changed at runtime** in the Settings panel; launch flags only set the initial state.
- **Mouse pass-through (`--click-through`)**: clicks and the wheel go to the window below, handy for editing text behind the overlay. It applies to the **whole window**, so buttons stop working while it is on — turn it off with **F9** or from the tray menu. Not supported in browser `--app` mode.

### Voice Features

- **All three switches default to `false`**; when off, no routes are registered and no dependencies load — zero impact.
- **Running locally**, point `STT_SERVICE_URL` / `TTS_SERVICE_URL` at `http://localhost:8001` / `http://localhost:8002`; inside the Docker network that is `http://stt:8000` / `http://tts:8000`. `start.bat` sets the former automatically.
- **Two recognition backends** (`STT_BACKEND`):
  - `qwen3_asr` (default): clearly better on Chinese and dialects; the 0.6B model needs ~1.8GB VRAM and turns 6 seconds of audio into text in about a second.
  - `faster_whisper`: the original pipeline, runs on plain CPU, older ecosystem.

#### Switching Between Qwen3-ASR and Whisper

Both backends share the same code path — **change `.env` and restart**, no code changes:

| Scenario | `STT_BACKEND` | `STT_DEVICE` | Dependencies in |
|---|---|---|---|
| GPU, Chinese first (default) | `qwen3_asr` | `cuda` | `.venv-stt` |
| **CPU-only machine** | `faster_whisper` | `cpu` | main `.venv` |
| GPU but low on VRAM | `faster_whisper` | `cuda` | main `.venv` |

The first launch detects the hardware and writes those three values automatically (`python scripts/detect_stt_env.py --patch .env` re-runs it manually): an NVIDIA GPU with ≥6GB VRAM gets Qwen + CUDA, otherwise it falls back to Whisper + CPU + `small`.

Download size on first launch: Qwen environment ~4.8GB plus 1.8GB of weights (kept in `.venv-stt/`); Whisper environment ~100MB plus weights (`base` 145MB / `small` 480MB).

For a larger Qwen model: `STT_QWEN_MODEL=Qwen/Qwen3-ASR-1.7B` (repo id, downloaded automatically) or `STT_QWEN_MODEL=models/Qwen3-ASR-1.7B` (local directory, fetched first with `python scripts/download_qwen_asr.py --model 1.7b`).

**Switching a CPU machine back to Whisper**: set `STT_BACKEND=faster_whisper` / `STT_DEVICE=cpu` / `STT_MODEL=small` in `.env` (leaving `STT_COMPUTE_TYPE` empty selects int8), `pip install faster-whisper ctranslate2` in the main environment, then restart — the launcher picks the interpreter by backend (Qwen → `.venv-stt`, Whisper → main `.venv`). Verify with the `backend` field of `curl http://localhost:8001/health`.

A few notes:

- The two backends **coexist**; switching back and forth needs no reinstall. Qwen must run in its own `.venv-stt` environment (its pinned `transformers` conflicts with the main environment); the launcher creates it on first start.
- On CPU, `small` runs at about 0.35x real time (near real-time, weaker on terminology and punctuation) and `large-v3-turbo` at about 1x (fine for transcription, not for live captions).
- With `STT_DEVICE=cuda`: Whisper goes through ctranslate2 and needs CUDA 12's cuBLAS + cuDNN 9; Qwen goes through torch and needs a CUDA build of torch.
- To drop Qwen for good: delete `.venv-stt` and `models/Qwen3-ASR-*` (~6.6GB total) and set `STT_BACKEND=faster_whisper`.

### Frontend & Local Storage

- **Login tokens and UI preferences live in browser localStorage**; the API key does not — it is stored encrypted in the server database and the UI only shows a masked hint.
- **Chat messages keep the latest 100** (independently per mode) and QA records the latest 30; refreshing the page resets practice progress.
- **Do not use the frontend dev server for production**: `start.bat` / `start.sh` start the hot-reloading dev server; only Docker and standalone window mode serve the build.

### Launch Scripts

- `start.bat` (forwards to `start.ps1`) / `start.sh` / `start_app.bat` create `.venv` and install dependencies on first launch (without touching the system Python), and skip installation while `requirements.txt` is unchanged. Requires **Python 3.11+**; the frontend needs **Node 20+**.
- `start.ps1` / `start.sh` ask interactively whether to enable voice; `start_app.*` reads `.env` only and never asks. Voice choices made there last only for the current window — write them into `.env` to keep them.
- `start.ps1` supports `-SkipDeps` (skip environment creation and installation); `start_app.ps1` supports `-Foreground` (logs in the foreground), `-SkipDeps`, `-NoBuild`, `-NoTray`, `-ShowTaskbar`.
- **Closing the window with X sends it to the tray instead of exiting**; quit from the tray context menu (deliberate, so a mistimed click cannot kill an interview).

### Troubleshooting

- `/api/*` returning 404 with a "feature switch is off" hint means the route was never registered — check the `.env` switch and restart the service.
- Desktop logs are in `logs/desktop.log`; after hiding the console, stdout/stderr go to `logs/app-*.log`.
- HuggingFace downloads stuck at 0 bytes: `config.py` already sets `HF_HUB_DISABLE_XET=1`; in mainland China also confirm `HF_ENDPOINT` has not been changed.

---

## 🤝 Contributing

Issues and pull requests are welcome.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT © 2025
