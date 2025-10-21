"""
HIREX • core/config.py
Global configuration for backend constants, environment variables,
and directory paths.

Version : 2.0.0
Author  : Sri Akash Kadali
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# 🌍 Environment Setup
# ============================================================

# Load environment variables from .env if present
load_dotenv()


# ============================================================
# 📁 Directory Structure (portable / any machine)
# ============================================================

# Project root:  <repo>/
#   backend/core/config.py  → parents[2] == <repo>
#     core → backend → <repo>
BASE_DIR = Path(__file__).resolve().parents[2]

# Fallback if layout differs (run from packaged app, etc.)
if not (BASE_DIR / "backend").exists():
    # Try one level up from where this file sits
    candidate = Path(__file__).resolve().parents[1]
    if (candidate / "backend").exists():
        BASE_DIR = candidate
    else:
        # Last resort: current working directory
        BASE_DIR = Path.cwd()

# Conventional top-level folders
BACKEND_DIR   = BASE_DIR / "backend"
FRONTEND_DIR  = BASE_DIR / "frontend"
DATA_DIR      = BASE_DIR / "data"
CACHE_DIR     = DATA_DIR / "cache"
TEMP_LATEX_DIR = CACHE_DIR / "latex_builds"
TEMPLATE_DIR  = BACKEND_DIR / "templates"

# Output & storage
OUTPUT_DIR       = DATA_DIR / "output"                  # compiled PDFs
SAMPLES_DIR      = DATA_DIR / "samples"                 # sample tex lives here
LOGS_DIR         = DATA_DIR / "logs"
HISTORY_DIR      = DATA_DIR / "history"
MASTERMINDS_DIR  = DATA_DIR / "mastermind_sessions"
CONTEXTS_DIR     = DATA_DIR / "contexts"                # JD + Resume memory

# Ensure required directories exist on every machine
for d in (
    DATA_DIR, CACHE_DIR, TEMP_LATEX_DIR, TEMPLATE_DIR, OUTPUT_DIR,
    SAMPLES_DIR, LOGS_DIR, HISTORY_DIR, MASTERMINDS_DIR, CONTEXTS_DIR
):
    d.mkdir(parents=True, exist_ok=True)


# ============================================================
# ⚙️ Core Application Settings
# ============================================================

APP_NAME     = "HIREX"
APP_VERSION  = "2.0.0"
DEBUG_MODE   = os.getenv("DEBUG", "true").lower() == "true"

# Upload restrictions
MAX_UPLOAD_MB       = int(os.getenv("MAX_UPLOAD_MB", "5"))
ALLOWED_EXTENSIONS  = {".tex", ".txt"}

# Default model (used by internal APIs)
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gpt-5-mini")

# Base API URL (for internal calls)
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


# ============================================================
# 🔐 Security & Secrets
# ============================================================

SECRET_KEY     = os.getenv("HIREX_SECRET", "hirex-dev-secret")
JWT_ALGORITHM  = "HS256"


# ============================================================
# 🤖 API Keys (OpenAI + Humanize)
# ============================================================

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
HUMANIZE_API_KEY = os.getenv("HUMANIZE_API_KEY", "")

if DEBUG_MODE:
    if not OPENAI_API_KEY:
        print("[HIREX] ⚠️ OPENAI_API_KEY not found in environment.")
    if not HUMANIZE_API_KEY:
        print("[HIREX] ⚠️ HUMANIZE_API_KEY not found in environment.")


# ============================================================
# 🧷 Helpers
# ============================================================

def _resolve_env_path(var_name: str, default_path: Path) -> Path:
    """
    Resolve a path from ENV if set; otherwise use default.
    Relative ENV paths are treated as relative to BASE_DIR.
    """
    raw = os.getenv(var_name, "").strip()
    if not raw:
        return default_path
    p = Path(os.path.expanduser(raw))
    if not p.is_absolute():
        p = BASE_DIR / p
    return p


def _ensure_file(path: Path, content: str) -> None:
    """
    Create file with content if it doesn't exist. Parent dirs are ensured above.
    """
    if not path.exists():
        path.write_text(content, encoding="utf-8")
        if DEBUG_MODE:
            print(f"[HIREX] 📄 Created default: {path}")


# ============================================================
# 🧠 Feature Module Paths & Settings (v2.0.0)
# ============================================================

# ---- Base templates (ENV overrides supported) ----
BASE_COVERLETTER_PATH = _resolve_env_path("BASE_COVERLETTER_PATH", SAMPLES_DIR / "base_coverletter.tex")
BASE_RESUME_PATH      = _resolve_env_path("BASE_RESUME_PATH",      SAMPLES_DIR / "base_resume.tex")

# ---- Logs & history ----
LOG_PATH      = LOGS_DIR / "events.jsonl"
HISTORY_PATH  = HISTORY_DIR / "history.jsonl"

# ---- MasterMind ----
MASTERMINDS_PATH  = MASTERMINDS_DIR
MASTERMINDS_MODEL = os.getenv("MASTERMINDS_MODEL", DEFAULT_MODEL)

# ---- SuperHuman (local rewrite) ----
SUPERHUMAN_LOCAL_ENABLED = os.getenv("SUPERHUMAN_LOCAL_ENABLED", "true").lower() == "true"
SUPERHUMAN_MODEL         = os.getenv("SUPERHUMAN_MODEL", DEFAULT_MODEL)

# ---- Other modules ----
COVERLETTER_MODEL = os.getenv("COVERLETTER_MODEL", DEFAULT_MODEL)
TALK_MODEL        = os.getenv("TALK_MODEL", DEFAULT_MODEL)


# ============================================================
# ✨ Portable Defaults — generate templates if missing
# ============================================================

_DEFAULT_RESUME_TEX = r"""% HIREX default base_resume.tex (portable)
\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\usepackage{enumitem}
\pagenumbering{gobble}
\begin{document}
\begin{center}
    {\LARGE Your Name}\\
    \vspace{2pt}
    your.email@example.com \quad | \quad (123) 456-7890 \quad |\quad \url{https://example.com}
\end{center}
\vspace{8pt}
\section*{Summary}
Results-oriented professional with experience in software engineering and AI.
\section*{Experience}
\textbf{Company} \hfill City, ST \\
\emph{Role} \hfill 2023--Present
\begin{itemize}[leftmargin=*]
    \item Bullet 1 describing impact.
    \item Bullet 2 describing impact.
\end{itemize}
\section*{Education}
\textbf{University}, Degree, Year
\end{document}
"""

_DEFAULT_COVERLETTER_TEX = r"""% HIREX default base_coverletter.tex (portable)
\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\usepackage{hyperref}
\pagenumbering{gobble}
\begin{document}
\noindent Date: \today

\vspace{10pt}
Hiring Manager \\
Company \\
City, ST

\vspace{10pt}
Dear Hiring Manager,

I am excited to apply for the role. My background in software and AI aligns with your needs.

Sincerely, \\
Your Name
\end{document}
"""

# Create defaults if they don't exist (works on any computer)
_ensure_file(BASE_RESUME_PATH, _DEFAULT_RESUME_TEX)
_ensure_file(BASE_COVERLETTER_PATH, _DEFAULT_COVERLETTER_TEX)

# Also expose these as ENV for code that reads os.getenv directly
os.environ.setdefault("BASE_RESUME_PATH", str(BASE_RESUME_PATH))
os.environ.setdefault("BASE_COVERLETTER_PATH", str(BASE_COVERLETTER_PATH))


# ============================================================
# 🧾 Model Catalog (for UI) — IDs and pricing
#   Price units are USD per 1,000,000 tokens unless noted.
#   Override any dict via env JSON (see *_OVERRIDE below).
# ============================================================

# OpenAI model IDs (current API names)
OPENAI_MODELS = [
    "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5-chat-latest",
    "gpt-5-thinking", "gpt-5-thinking-mini", "gpt-5-thinking-nano",
    "gpt-5-pro",
    # legacy
    "gpt-4o", "gpt-4.1", "gpt-4o-mini", "o3", "o3-mini",
]

# Aliases the frontend can show in pickers
MODEL_ALIASES = {
    "GPT-5 (Auto)": "gpt-5",
    "GPT-5 Fast / Instant": "gpt-5-chat-latest",
    "GPT-5 Thinking": "gpt-5-thinking",
    "GPT-5 Pro": "gpt-5-pro",
    "GPT-5 Mini": "gpt-5-mini",
    "GPT-5 Nano": "gpt-5-nano",
    # legacy labels (optional)
    "GPT-4o": "gpt-4o",
    "o3": "o3",
}

# Pricing (per 1M tokens). Cached input = prompt caching rates.
OPENAI_MODEL_PRICING = {
    "gpt-5": {"input": 1.25, "output": 10.00, "cached_input": 0.125},
    "gpt-5-mini": {"input": 0.25, "output": 2.00, "cached_input": 0.025},
    "gpt-5-nano": {"input": 0.05, "output": 0.40, "cached_input": 0.005},
    "gpt-5-chat-latest": {"input": 1.25, "output": 10.00, "cached_input": 0.125},
    "gpt-5-thinking": {"input": 1.25, "output": 10.00, "cached_input": 0.125},
    "gpt-5-thinking-mini": {"input": 0.25, "output": 2.00, "cached_input": 0.025},
    "gpt-5-thinking-nano": {"input": 0.05, "output": 0.40, "cached_input": 0.005},
    "gpt-5-pro": {"input": 15.00, "output": 120.00},
    # legacy
    "gpt-4o": {"input": 5.00, "output": 15.00},
    "gpt-4.1": {"input": 5.00, "output": 15.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "o3": {"input": 1.10, "output": 4.40},
    "o3-mini": {"input": 0.60, "output": 2.50},
}

AVAILABLE_MODELS = {
    "openai": OPENAI_MODELS,
    "aihumanize": ["quality", "balance", "enhanced", "private"],
}

AIHUMANIZE_PLANS = {
    "basic":   {"price_month": 6,  "words_per_request": 500,  "notes": "Annual billing shown in UI"},
    "starter": {"price_month": 15, "words_per_request": 500,  "notes": "Plan naming varies; site shows multiple tiers"},
    "pro":     {"price_month": 25, "words_per_request": 1500},
    "premium": {"price_month": 40, "words_per_request": 3000},
}

MODEL_PRICING = {
    "openai": OPENAI_MODEL_PRICING,
    "aihumanize": {
        "modes": AVAILABLE_MODELS["aihumanize"],
        "plans": AIHUMANIZE_PLANS,
        "unit": "subscription",
    },
}

OPENAI_MODEL_PRICING_OVERRIDE = os.getenv("OPENAI_MODEL_PRICING_JSON", "")
AIHUMANIZE_PLANS_OVERRIDE     = os.getenv("AIHUMANIZE_PLANS_JSON", "")

def _apply_overrides():
    global OPENAI_MODEL_PRICING, AIHUMANIZE_PLANS, MODEL_PRICING
    if OPENAI_MODEL_PRICING_OVERRIDE:
        try:
            override = json.loads(OPENAI_MODEL_PRICING_OVERRIDE)
            OPENAI_MODEL_PRICING.update(override)
        except Exception as e:
            print(f"[HIREX] ⚠️ OPENAI_MODEL_PRICING_JSON invalid: {e}")
    if AIHUMANIZE_PLANS_OVERRIDE:
        try:
            override = json.loads(AIHUMANIZE_PLANS_OVERRIDE)
            AIHUMANIZE_PLANS.update(override)
        except Exception as e:
            print(f"[HIREX] ⚠️ AIHUMANIZE_PLANS_JSON invalid: {e}")
    MODEL_PRICING["openai"] = OPENAI_MODEL_PRICING
    MODEL_PRICING["aihumanize"]["plans"] = AIHUMANIZE_PLANS

_apply_overrides()


# ============================================================
# 🧩 Path Utilities
# ============================================================

def get_tex_build_path(filename: str) -> Path:
    """Return absolute path for a temporary LaTeX build artifact."""
    return TEMP_LATEX_DIR / filename

def get_output_pdf_path(filename: str) -> Path:
    """Return absolute path for saving final compiled PDFs."""
    return OUTPUT_DIR / filename

def get_contexts_dir() -> Path:
    """Directory where JD+Resume contexts are saved as JSON."""
    return CONTEXTS_DIR

def is_allowed_upload(filename: str) -> bool:
    """Check if a filename has an allowed extension."""
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# ============================================================
# 📊 Diagnostics (Local CLI)
# ============================================================

if __name__ == "__main__":
    print("=========== HIREX CONFIG ===========")
    print(f"APP_NAME              : {APP_NAME}")
    print(f"APP_VERSION           : {APP_VERSION}")
    print(f"DEBUG_MODE            : {DEBUG_MODE}")
    print(f"DEFAULT_MODEL         : {DEFAULT_MODEL}")
    print(f"SUPERHUMAN_MODEL      : {SUPERHUMAN_MODEL}")
    print(f"MASTERMINDS_MODEL     : {MASTERMINDS_MODEL}")
    print(f"SUPERHUMAN_LOCAL      : {SUPERHUMAN_LOCAL_ENABLED}")
    print(f"BASE_COVERLETTER_PATH : {BASE_COVERLETTER_PATH}")
    print(f"BASE_RESUME_PATH      : {BASE_RESUME_PATH}")
    print(f"OUTPUT_DIR            : {OUTPUT_DIR}")
    print(f"LOG_PATH              : {LOG_PATH}")
    print(f"HISTORY_PATH          : {HISTORY_PATH}")
    print(f"MASTERMINDS_PATH      : {MASTERMINDS_PATH}")
    print(f"CONTEXTS_DIR          : {CONTEXTS_DIR}")
    print(f"OPENAI_API_KEY        : {'set' if OPENAI_API_KEY else 'missing'}")
    print(f"HUMANIZE_API_KEY      : {'set' if HUMANIZE_API_KEY else 'missing'}")
    print(f"OpenAI Models (n)     : {len(OPENAI_MODELS)}")
    print(f"AIHumanize Modes      : {', '.join(AVAILABLE_MODELS['aihumanize'])}")
    print("OpenAI pricing sample : gpt-5 =", OPENAI_MODEL_PRICING.get('gpt-5'))
