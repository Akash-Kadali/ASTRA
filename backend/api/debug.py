"""
============================================================
 HIREX v2.1.0 — api/debug.py
 ------------------------------------------------------------
 Lightweight diagnostic endpoint for frontend → backend logs.

  • Accepts any POSTed JSON payload (dict or list) or raw text
  • Prints to console in readable, truncated format
  • Persists structured event via log_event()
  • Auto-tags origin, page, level, and timestamps
  • Never crashes on malformed or non-JSON payloads

 Author: Sri Akash Kadali
============================================================
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.core.utils import log_event

router = APIRouter(prefix="/api/debug", tags=["debug"])


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _truncate(obj: Any, limit: int = 800) -> str:
    """
    Truncate a JSON-serialized preview to avoid spammy console logs.
    """
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        s = str(obj)
    return (s[:limit] + "…") if len(s) > limit else s


@router.get("/ping")
async def debug_ping():
    """Simple liveness check for the debug router."""
    return {"ok": True, "router": "debug", "time": _now_iso()}


# ============================================================
# 🧠  FE → BE Debug / Analytics Logger
# ============================================================
@router.post("/log")
async def debug_log(request: Request):
    """
    Receives arbitrary frontend debug or analytics payloads
    and logs them both to console and persistent JSONL.

    Example Payload:
    {
        "msg": "UI LOADED",
        "version": "v2.1.0",
        "page": "master.html",
        "origin": "http://127.0.0.1:8000",
        "timestamp": "2025-10-17T18:30:00Z",
        "extra": {...}
    }
    """
    # ---------- 1️⃣ Try JSON Parse (dict OR list); fall back to raw text ----------
    payload: Dict[str, Any]
    try:
        body = await request.json()
        if isinstance(body, dict):
            payload = body
        else:
            # Wrap non-dict JSON (e.g., list) so we can enrich with metadata
            payload = {"data": body, "non_dict_json": True}
    except Exception:
        # Malformed or non-JSON body; capture raw text safely
        raw = (await request.body()).decode("utf-8", "ignore")
        payload = {"raw": raw, "format_error": True}

    # ---------- 2️⃣ Inject Metadata ----------
    headers = request.headers
    client_ip = request.client.host if request.client else "unknown"

    payload.setdefault("received_at", _now_iso())
    payload.setdefault("origin", client_ip)
    payload.setdefault("page", payload.get("page", "unknown"))
    payload.setdefault("level", payload.get("level", "debug"))
    payload.setdefault("user_agent", headers.get("user-agent", ""))
    payload.setdefault("referer", headers.get("referer", ""))

    # Maintain an explicit event timestamp if provided by FE
    payload.setdefault("timestamp", payload.get("received_at"))

    # ---------- 3️⃣ Console Print (truncated preview) ----------
    msg = payload.get("msg", "(no message)")
    page = payload.get("page", "?")
    print(f"[FE DEBUG] ({page}) {msg}")
    preview = {k: payload[k] for k in payload if k not in {"raw"}}
    print("  └─", _truncate(preview))

    # ---------- 4️⃣ Persist via log_event ----------
    try:
        log_event("frontend_debug", payload)
    except Exception as e:
        # Never crash
        print(f"[WARN] Failed to log debug event: {e}")

    # ---------- 5️⃣ Response ----------
    return JSONResponse(
        {
            "ok": True,
            "logged": True,
            "timestamp": payload.get("received_at"),
        }
    )
