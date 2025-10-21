# ============================================================
#  HIREX v2.1.0 — Utility & Diagnostics API
#  ------------------------------------------------------------
#  Endpoints:
#   • Health / version / config
#   • Logging (frontend analytics)
#   • Text helpers (escape/unescape)
#   • Base64 encode/decode utilities
#   • Safe filename & slug helpers
#   • History + status dashboard support
#  Author: Sri Akash Kadali
# ============================================================

from __future__ import annotations

import os
import base64
import json
import re
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Form, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.core import config
from backend.core.utils import log_event, safe_filename
from backend.core.security import secure_tex_input

router = APIRouter(prefix="/api/utils", tags=["utils"])


# ============================================================
# ⚙️ 1) HEALTH / VERSION / CONFIG
# ============================================================
@router.get("/ping")
async def ping():
    """Health check — verifies backend uptime and environment."""
    return {
        "status": "ok",
        "service": "HIREX Core API",
        "time": datetime.utcnow().isoformat(),
        "platform": platform.system(),
        "python": platform.python_version(),
    }


@router.get("/version")
async def get_version():
    """Return the current HIREX version and model defaults."""
    return {
        "version": getattr(config, "APP_VERSION", "2.1.0"),
        "default_model": getattr(config, "DEFAULT_MODEL", "gpt-4o-mini"),
        "superhuman_local": getattr(config, "SUPERHUMAN_LOCAL_ENABLED", True),
        "build_time": datetime.utcnow().isoformat(),
    }


@router.get("/config")
async def get_config():
    """Expose a safe subset of configuration variables for frontend diagnostics."""
    safe_keys = [
        "APP_VERSION",
        "DEFAULT_MODEL",
        "SUPERHUMAN_LOCAL_ENABLED",
        "BASE_COVERLETTER_PATH",
        "MASTERMINDS_PATH",
        "LOG_PATH",
        "HISTORY_PATH",
        "API_BASE_URL",
    ]
    safe_data: Dict[str, Any] = {}
    for k in safe_keys:
        v = getattr(config, k, None)
        # Path objects → string for JSON
        if isinstance(v, Path):
            safe_data[k] = str(v)
        else:
            safe_data[k] = v
    return {"config": safe_data}


# ============================================================
# 🧾 2) FRONTEND LOGGING & ANALYTICS
# ============================================================
@router.post("/log")
async def log_frontend_event(
    msg: str = Form(...),
    page: str = Form("unknown"),
    version: str = Form("unknown"),
    origin: str = Form("client"),
    level: str = Form("info"),
):
    """Receives debug or analytic events from the frontend (UI telemetry)."""
    meta = {
        "msg": msg,
        "page": page,
        "version": version,
        "origin": origin,
        "level": level,
        "timestamp": datetime.utcnow().isoformat(),
    }
    log_event("frontend_log", meta)
    return {"logged": True, "time": meta["timestamp"]}


# ============================================================
# 🧩 3) TEXT UTILITIES
# ============================================================
@router.post("/escape")
async def escape_latex(text: str = Form(...)):
    """Return LaTeX-safe escaped string."""
    try:
        escaped = secure_tex_input(text)
        return {"escaped": escaped}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Escape failed: {e}")


@router.post("/unescape")
async def unescape_latex(text: str = Form(...)):
    """Reverse minimal LaTeX escapes for readability."""
    try:
        unescaped = (
            text.replace(r"\#", "#")
            .replace(r"\%", "%")
            .replace(r"\$", "$")
            .replace(r"\&", "&")
            .replace(r"\_", "_")
            .replace(r"\{", "{")
            .replace(r"\}", "}")
        )
        return {"unescaped": unescaped}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Unescape failed: {e}")


# ============================================================
# 📦 4) ENCODING / DECODING HELPERS
# ============================================================
@router.post("/b64encode")
async def b64encode_data(raw: str = Form(...)):
    """Base64 encode a plain string."""
    try:
        encoded = base64.b64encode(raw.encode("utf-8")).decode("utf-8")
        return {"base64": encoded, "len": len(encoded)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Encode failed: {e}")


@router.post("/b64decode")
async def b64decode_data(encoded: str = Form(...)):
    """Base64 decode a string."""
    try:
        decoded = base64.b64decode(encoded.encode("utf-8")).decode("utf-8", errors="ignore")
        return {"decoded": decoded, "len": len(decoded)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Decode failed: {e}")


# ============================================================
# 🗂️ 5) FILENAME + SANITIZATION HELPERS
# ============================================================
@router.post("/safe_filename")
async def make_safe_filename(name: str = Form(...)):
    """Return a filesystem-safe version of the given filename."""
    safe = safe_filename(name)
    return {"input": name, "safe_name": safe}


@router.post("/slugify")
async def slugify_string(name: str = Form(...)):
    """Return a lowercase slugified string safe for URLs or filenames."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return {"slug": slug}


# ============================================================
# 🧭 6) HISTORY / LOG RETRIEVAL
# ============================================================
def _read_jsonl(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        out: List[Dict[str, Any]] = []
        for line in reversed(lines):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
        return out
    except Exception:
        return []


@router.get("/history")
async def get_history(limit: int = Query(100, ge=1, le=1000)):
    """Return the most recent event logs for diagnostics or dashboard."""
    log_path = Path(getattr(config, "LOG_PATH", "backend/data/logs/events.jsonl"))
    events = _read_jsonl(log_path, limit)
    return {"count": len(events), "events": events}


# ============================================================
# 🧠 7) SYSTEM STATUS SUMMARY (Mini Dashboard)
# ============================================================
@router.get("/status")
async def get_status():
    """
    Lightweight system snapshot used by the dashboard sidebar.
    Provides event totals, last log timestamp, and environment details.
    """
    log_path = Path(getattr(config, "LOG_PATH", "backend/data/logs/events.jsonl"))
    total, last_event = 0, None

    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                total = len(lines)
                if lines:
                    try:
                        last_event = json.loads(lines[-1])
                    except Exception:
                        last_event = None
        except Exception:
            last_event = None

    return {
        "status": "ok",
        "total_events": total,
        "last_event": last_event,
        "app_version": getattr(config, "APP_VERSION", "2.1.0"),
        "timestamp": datetime.utcnow().isoformat(),
        "platform": platform.system(),
    }


# ============================================================
# 🧪 8) SELF-TEST: ENCODE-DECODE ROUNDTRIP
# ============================================================
@router.post("/selftest")
async def self_test(text: str = Form(...)):
    """Perform a simple base64 encode-decode validation."""
    try:
        encoded = base64.b64encode(text.encode("utf-8")).decode("utf-8")
        decoded = base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
        return {
            "input": text,
            "encoded": encoded[:50] + ("..." if len(encoded) > 50 else ""),
            "decoded_match": decoded == text,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Self-test failed: {e}")
