# 🌌 **ASTRA v2.0.0**
<p align="center">
  <img src="https://github.com/Akash-Kadali/ASTRA/blob/main/data/astra.png" alt="ASTRA Logo" width="700"/>
</p>

# 🌌 ASTRA v2.1.0
### Autonomous System for Talent & Resume Automation

### *Autonomous System for Talent & Resume Automation*

**Author:** Sri Akash Kadali

> *“Intelligence that understands your profile, humanizes your story, and aligns every resume to the role.”*

---

## 📘 Overview

**ASTRA** is an **AI-powered LaTeX resume and job-application automation suite**.
It fuses the precision of LLMs with human-sounding tone control to create **ATS-safe**, **context-aware**, and **interview-ready** career materials.

The platform runs locally as a **FastAPI + PyWebView desktop app**, giving a native ChatGPT-like experience with persistent memory, LaTeX integration, and analytics.

---

### 🧩 Core Modules

| Module                          | Purpose                                                                        |
| ------------------------------- | ------------------------------------------------------------------------------ |
| 🧠 **MasterMind**               | ChatGPT-style reasoning assistant with memory (RAG-like context)               |
| 🗣️ **SuperHuman**              | AI text humanizer for resumes, cover letters, and answers                      |
| 💬 **Talk to ASTRA**            | Job-aware Q&A module — answers recruiter/interview questions using JD + resume |
| 🧾 **Resume Optimizer**         | Contextual LaTeX optimizer that aligns your resume with a JD                   |
| ✍️ **CoverLetter Engine**       | Auto-drafts role-specific cover letters (GPT + SuperHuman integration)         |
| 🧍 **Humanize (AIHumanize.io)** | Enhances bullet points for readability & tone                                  |
| 📊 **Dashboard**                | Tracks tone, model usage, fit scores, and recent sessions                      |
| ⚙️ **Utils / Models Routers**   | Health, config, model catalog, and helper APIs                                 |

---

## 🏗️ Project Structure

```
ASTRA/
│
├── backend/
│   ├── api/
│   │   ├── optimize.py          ← Resume optimizer / JD parser
│   │   ├── coverletter.py       ← Cover letter generator
│   │   ├── talk.py              ← “Talk to ASTRA” endpoint
│   │   ├── superhuman.py        ← Local AI humanizer
│   │   ├── humanize.py          ← AIHumanize.io integration
│   │   ├── mastermind.py        ← MasterMind assistant backend
│   │   ├── dashboard.py         ← Analytics + trends
│   │   ├── context_store.py     ← JD + Resume memory store
│   │   ├── models_router.py     ← Model list + pricing
│   │   ├── utils_router.py      ← Helpers (ping, base64, escape)
│   │   └── debug.py             ← FE→BE logger
│   │
│   ├── core/
│   │   ├── config.py            ← Global paths, env, and defaults
│   │   ├── compiler.py          ← Secure pdflatex wrapper
│   │   ├── security.py          ← Safe file + LaTeX validation
│   │   └── utils.py             ← Logging, hashing, helpers
│   │
│   └── data/
│       ├── contexts/            ← Saved JD + resume contexts
│       ├── history/             ← User activity JSONL
│       ├── logs/                ← Event logs for dashboard
│       └── mastermind_sessions/ ← Stored MasterMind chats
│
├── frontend/
│   ├── master.html              ← Main app UI
│   ├── master.js                ← Unified JS controller
│   ├── static/css/              ← Theming + layout
│   └── static/assets/           ← Icons, favicon, logos
│
├── main.py                      ← FastAPI + PyWebView launcher
└── requirements.txt
```

---

## ⚙️ Setup & Environment

### 1️⃣ Install dependencies

```bash
pip install fastapi uvicorn httpx openai python-dotenv pywebview pydantic
```

### 2️⃣ Environment variables (`.env`)

```bash
OPENAI_API_KEY=sk-xxxxxx
HUMANIZE_API_KEY=Bearer xxxxx
DEBUG=true
DEFAULT_MODEL=gpt-4o-mini
API_BASE_URL=http://127.0.0.1:8000
```

### 3️⃣ Run ASTRA

```bash
python main.py
```

**What happens:**

* FastAPI backend starts on **localhost:8000**
* Frontend (`master.html`) loads inside a **desktop window (PyWebView)**
* Routers auto-register, static files mount
* Logs + sessions persist in `/backend/data/`

Then open in browser (or auto-launch window):
👉 [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 🧠 Key Backend Components

### 🔹 `optimize.py` — Resume Optimizer

* Extracts **skills**, **courses**, and **role** from JD.
* Canonicalizes tech stack names (e.g., *PyTorch → Data & ML*).
* Generates 4-line skill tables with GPT-proposed labels.
* Produces LaTeX-safe replacements for the resume body.

### 🔹 `coverletter.py` — Cover Letter Generator

* Parses **company** & **role** with GPT JSON.
* Drafts 2–4 factual, JD-grounded paragraphs.
* Optionally humanizes tone via `/api/superhuman`.
* Injects body into base LaTeX template & compiles to PDF.

### 🔹 `talk.py` — “Talk to ASTRA”

* Accepts JD + question and answers like an interview coach.
* Summarizes resumes (via `gpt-4o-mini`) for factual context.
* Generates short, non-hallucinated answers.
* Optionally humanizes via SuperHuman rewrite.

### 🔹 `superhuman.py` — Humanizer Engine

* Refines tone, grammar, and structure across modes:

  * `resume`, `coverletter`, `paragraph`, `sentence`
* Tone options: `formal`, `balanced`, `conversational`, `confident`, `academic`
* Ensures **no fabrication** and **LaTeX-safe output**.

### 🔹 `humanize.py` — AIHumanize.io Integration

* Targets LaTeX `\resumeItem{}` lines.
* Asynchronous, multi-retry rewriting.
* Removes unsafe preambles, escapes stray `%`.
* Returns clean, enhanced bullets.

### 🔹 `mastermind.py` — Chat Assistant

* Persistent, persona-aware AI chat (MasterMind).
* Stores JSON session histories in `/data/mastermind_sessions/`.
* Trims long contexts, supports tone + model selection.
* Ideal for reasoning, explanation, or JD analysis.

### 🔹 `context_store.py`

* Saves and loads job context bundles (JD + resume + PDFs).
* Used by **Talk to ASTRA** and **Dashboard**.
* Auto-timestamps each entry (`company_role_YYYYMMDD-HHMMSS`).

### 🔹 `dashboard.py`

* Aggregates logs into charts and analytics.
* Tracks usage counts per feature and tone.
* Produces Mon-Sun trend vectors and recent history list.

### 🔹 `models_router.py`

* Provides list of all **OpenAI** and **AIHumanize** models.
* Includes aliases, pricing, and provider metadata for frontend dropdowns.

### 🔹 `utils_router.py`

* Utility suite for:

  * `/ping`, `/version`, `/config`
  * Base64 encode/decode
  * LaTeX escape/unescape
  * Safe filename + slug creation
  * Logging frontend telemetry

### 🔹 `debug.py`

* FE→BE logger for diagnostics.
* Accepts arbitrary JSON or text payloads.
* Writes event data to persistent logs.

---

## 🧩 Core Framework Files

### `core/config.py`

* Manages directory layout, env vars, and default `.tex` templates.
* Exposes:

  * `APP_VERSION`, `DEFAULT_MODEL`, `OPENAI_API_KEY`, `DATA_DIR`
  * Paths for logs, contexts, and sessions
* Generates fallback LaTeX templates if missing.

### `core/compiler.py`

* Sandboxed LaTeX → PDF builder using `pdflatex`.
* Runs in temp dir, no shell escape, double-pass compile.
* Logs results and returns PDF bytes.

### `core/security.py`

* Validates uploads (only `.tex` / `.txt`, ≤5 MB).
* `secure_tex_input()` ensures raw LaTeX is passed through safely.

### `core/utils.py`

* Central logging & diagnostics.
* `log_event()` appends to JSONL for dashboard analytics.
* Includes hashing, filename safety, and benchmarking tools.

---

## 🖥️ Frontend Overview

* **`master.html`**: Unified single-page dark-themed interface.
* **`master.js`**: Routes user actions to backend endpoints.
* CSS and animations follow ChatGPT-like theme (`#0a1020` base color).

Front-end Modules:

* Resume Optimizer
* Cover Letter Generator
* Talk to ASTRA
* Dashboard (analytics, history, trends)

---

## 💾 Data Directories

| Path                         | Purpose                         |
| ---------------------------- | ------------------------------- |
| `data/logs/events.jsonl`     | All system + API events         |
| `data/history/history.jsonl` | Past actions (for Dashboard)    |
| `data/contexts/`             | Stored JD + resume contexts     |
| `data/mastermind_sessions/`  | MasterMind chat histories       |
| `data/cache/latex_builds/`   | Temporary LaTeX build artifacts |

---

## 🔐 Security

* File validation enforced in `security.py`.
* `pdflatex` runs without `--shell-escape`.
* No arbitrary OS calls or evals.
* Every text path goes through `secure_tex_input()`.

---

## 📈 Logging & Analytics

All events use:

```python
log_event("event_name", {"meta": {...}})
```

Stored in `/data/logs/events.jsonl`, visualized by `dashboard.py`.

Examples:

* `optimize_resume`
* `superhuman_rewrite`
* `talk_answer_raw`
* `coverletter_draft_fail`
* `frontend_debug`

---

## 🧱 Run Modes

| Mode                               | Description                      |
| ---------------------------------- | -------------------------------- |
| `python main.py`                   | Full desktop app with GUI        |
| `uvicorn backend.api:app --reload` | FastAPI API-only mode            |
| `/api/docs`                        | Swagger UI for testing endpoints |

---

## 🛠️ Roadmap (v2.2.x → v3.0)

* ✅ AI-driven fit-score visualization
* 🪶 PDF → LaTeX reverse parser
* 🌐 Cloud sync for sessions + contexts
* 🔄 WebSocket real-time chat for MasterMind
* 💡 Resume ranking dashboard for multiple roles
* 🧬 RAG pipeline (ASTRA Memory) for dynamic context retrieval

---

## 🪙 License & Attribution

Copyright © 2025 **Sri Akash Kadali**
Licensed for educational and research use.
Trademarks: ASTRA™, MasterMind™, SuperHuman™ belong to their respective author.

---
