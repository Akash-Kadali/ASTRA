"""
HIREX • core/utils.py (v2.0.0)
Common utility functions shared across backend modules.
For this version: No LaTeX escaping or text cleaning — passes LaTeX as-is.
Author: Sri Akash Kadali
"""

from __future__ import annotations

import re
import html
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# ============================================================
# 📁 Logging path (honor config if available)
# ============================================================
try:
    from backend.core import config as _cfg  # type: ignore
    _DEFAULT_LOG_PATH = Path(getattr(_cfg, "LOG_PATH", "backend/data/logs/events.jsonl"))
except Exception:
    _DEFAULT_LOG_PATH = Path("backend/data/logs/events.jsonl")

LOG_PATH = _DEFAULT_LOG_PATH
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


# ============================================================
# 🔐 HASHING UTILITIES
# ============================================================
def sha256_str(data: Optional[str]) -> str:
    """Generate a full SHA256 hash of a string."""
    if data is None:
        data = ""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def simple_hash(data: Optional[str], length: int = 8) -> str:
    """Generate a short deterministic hash (used for cache keys or content IDs)."""
    return sha256_str(data or "")[:max(1, int(length))]


# ============================================================
# 📜 TEXT HELPERS (NO LATEX ESCAPING)
# ============================================================
def tex_escape(text: Optional[str]) -> str:
    """
    Passthrough for LaTeX text (no escaping).
    Used when sending LaTeX to or receiving from OpenAI/Humanize.
    """
    return text or ""


def html_escape(text: Optional[str]) -> str:
    """HTML-escape text for safe display inside web UIs (not LaTeX)."""
    return html.escape(text or "")


def clean_text(text: Optional[str]) -> str:
    """
    Lightweight text cleaner (no normalization, no space compression).
    Keeps LaTeX intact.
    """
    if not text:
        return ""
    return str(text)


def safe_filename(name: Optional[str]) -> str:
    """Convert a string into a safe, cross-platform filename."""
    if not name:
        return "file"
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    # Avoid leading/trailing dots or underscores; trim length
    name = name.strip("._") or "file"
    return name[:64]


# ============================================================
# 🧠 LOGGING & DIAGNOSTIC HELPERS
# ============================================================
def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.utcnow().isoformat()


def log_event(event: str, meta: Optional[Dict[str, Any]] = None) -> None:
    """
    Append a JSON line to the global event log and print to console.
    Used by all backend modules for analytics and dashboard.

    Accepts:
      • event: short event string
      • meta : optional dict payload (anything JSON-serializable; non-serializable values coerced to str)
    """
    record = {
        "timestamp": utc_now_iso(),
        "event": str(event),
        "meta": meta or {},
    }

    # Console log (truncate very large metas for readability)
    try:
        preview = json.dumps(record["meta"], ensure_ascii=False)
        if len(preview) > 800:
            preview = preview[:800] + "…"
        print(f"[{record['timestamp']}] {record['event']} :: {preview}")
    except Exception:
        print(f"[{record['timestamp']}] {record['event']} :: (unserializable meta)")

    # Persistent log (append JSONL)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"[HIREX] ⚠️ Failed to write event log: {e}")


def benchmark(name: str):
    """
    Context manager for timing code blocks.

    Example:
        with benchmark("Optimize Resume"):
            run_some_code()
    """
    import time

    class _Timer:
        def __enter__(self):
            self._start = time.time()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            duration_ms = (time.time() - self._start) * 1000.0
            log_event("⏱️ benchmark", {"name": name, "duration_ms": round(duration_ms, 1)})

    return _Timer()


# ============================================================
# 🧪 Local Test
# ============================================================
if __name__ == "__main__":
    sample = r"""
    \documentclass{article}
    \begin{document}
    Hello \textbf{World!} $E = mc^2$
    \end{document}
    """
    print("Original LaTeX (unchanged):")
    print(sample)
    print("SHA256:", sha256_str(sample))
    print("Short Hash:", simple_hash(sample))
    print("Safe File:", safe_filename("My Resume (final).tex"))

    with benchmark("Hash Generation"):
        for _ in range(10000):
            sha256_str(sample)
