# ============================================================
#  HIREX v2.0.0 — Dashboard Analytics & History Endpoint
#  ------------------------------------------------------------
#  Provides:
#   • Aggregated event summaries
#   • Tone/mode analytics
#   • Weekly trend data (Mon..Sun)
#   • Recent history listing
#   • Event type registry
#   • Robust log reading & safe JSONL parsing
#  Author: Sri Akash Kadali
# ============================================================

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.core import config

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# ============================================================
# 📁 Paths
# ============================================================
LOG_PATH = Path(getattr(config, "LOG_PATH", "backend/data/logs/events.jsonl"))
HISTORY_PATH = Path(getattr(config, "HISTORY_PATH", "backend/data/history/history.jsonl"))

for p in [LOG_PATH.parent, HISTORY_PATH.parent]:
    p.mkdir(parents=True, exist_ok=True)


# ============================================================
# 🧩 Helpers: Safe JSONL Reader + Utilities
# ============================================================

def _read_jsonl(path: Path, limit: int = 500) -> List[Dict[str, Any]]:
    """Safely read the last N lines of a JSONL file (newest first)."""
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        records: List[Dict[str, Any]] = []
        # Reverse so newest is first
        for line in reversed(lines):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    records.append(obj)
            except json.JSONDecodeError:
                continue
        return records
    except Exception:
        return []


def _iso(ts: Optional[str]) -> str:
    """Coerce to ISO timestamp string (safe fallback to now)."""
    if not ts:
        return datetime.utcnow().isoformat()
    try:
        # Validate/normalize
        _ = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return ts
    except Exception:
        return datetime.utcnow().isoformat()


def _event_name(e: Dict[str, Any]) -> str:
    """Normalize event/type name."""
    return (e.get("event") or e.get("type") or "unknown").lower()


# ============================================================
# 📊 Aggregations
# ============================================================

def summarize_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate analytic aggregates for dashboard visualizations."""
    summary: Dict[str, Any] = {
        "total_events": len(events),
        "optimize_runs": 0,
        "coverletters": 0,
        "superhuman_calls": 0,
        "talk_queries": 0,
        "mastermind_chats": 0,
        "tones": Counter(),
        "modes": Counter(),
        "avg_resume_length": 0.0,
    }

    total_len = 0
    for e in events:
        evt = _event_name(e)
        meta = e.get("meta", {}) or {}

        if "optimize" in evt:
            summary["optimize_runs"] += 1
        if "coverletter" in evt:
            summary["coverletters"] += 1
        if "superhuman" in evt or "humanize" in evt:
            summary["superhuman_calls"] += 1
        if "talk" in evt:
            summary["talk_queries"] += 1
        if "mastermind" in evt:
            summary["mastermind_chats"] += 1

        tone = str(meta.get("tone", "balanced")).lower()
        mode = str(meta.get("mode", "general")).lower()
        if tone:
            summary["tones"][tone] += 1
        if mode:
            summary["modes"][mode] += 1

        try:
            total_len += int(meta.get("resume_len") or 0)
        except Exception:
            pass

    total = max(summary["total_events"], 1)
    summary["avg_resume_length"] = round(total_len / total, 2)

    # Convert counters to plain dicts for JSON
    summary["tones"] = dict(summary["tones"])
    summary["modes"] = dict(summary["modes"])
    return summary


def summarize_history(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract recent high-level activity (for dashboard table)."""
    out: List[Dict[str, Any]] = []
    for h in records:
        meta = h.get("meta", {}) or {}
        ts = _iso(h.get("timestamp") or h.get("time"))
        evt = _event_name(h)
        out.append(
            {
                "timestamp": ts,
                "event": evt,
                "company": meta.get("company", ""),
                "role": meta.get("role", ""),
                "tone": meta.get("tone", "balanced"),
                "score": meta.get("fit_score", None),
                "length": meta.get("resume_len", None),
                "source": h.get("origin", "system"),
            }
        )
    return out


def weekly_trend(records: List[Dict[str, Any]]) -> Dict[str, List[int]]:
    """
    Build Mon..Sun trend counts per category.
    """
    buckets = {
        "optimizations": [0] * 7,
        "coverletters": [0] * 7,
        "superhuman": [0] * 7,
        "mastermind": [0] * 7,
        "talk": [0] * 7,
    }

    def _dow(ts: str) -> int:
        try:
            d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            # Monday=0
            return d.weekday()
        except Exception:
            return 0

    for r in records:
        evt = _event_name(r)
        ts = _iso(r.get("timestamp") or r.get("time"))
        i = _dow(ts)
        if "optimize" in evt:
            buckets["optimizations"][i] += 1
        elif "coverletter" in evt:
            buckets["coverletters"][i] += 1
        elif "superhuman" in evt or "humanize" in evt:
            buckets["superhuman"][i] += 1
        elif "mastermind" in evt:
            buckets["mastermind"][i] += 1
        elif "talk" in evt:
            buckets["talk"][i] += 1

    return buckets


# ============================================================
# 🚀 Root: Combined payload (summary + trend + history)
# ============================================================
@router.get("")
async def dashboard_root(limit: int = Query(300, ge=1, le=2000)):
    events = _read_jsonl(LOG_PATH, limit)
    history = _read_jsonl(HISTORY_PATH, limit)
    records = history or events

    if not records:
        return {"summary": {}, "trend": {}, "history": [], "updated": datetime.utcnow().isoformat()}

    return {
        "summary": summarize_events(records),
        "trend": weekly_trend(records),
        "history": summarize_history(records)[:100],
        "updated": datetime.utcnow().isoformat(),
    }


# ============================================================
# 🚀 Endpoint: /summary
# ============================================================
@router.get("/summary")
async def get_summary(limit: int = Query(300, ge=1, le=2000)):
    """
    Aggregated dashboard summary used for top metrics and charts.
    Combines analytics from events.jsonl and history.jsonl.
    """
    events = _read_jsonl(LOG_PATH, limit)
    history = _read_jsonl(HISTORY_PATH, limit)

    if not events and not history:
        return JSONResponse({"message": "No analytics available.", "summary": {}, "recent": []})

    # Prefer history when present
    records = history or events
    summary = summarize_events(records)
    hist_data = summarize_history(records)

    return {"summary": summary, "recent": hist_data[:100], "updated": datetime.utcnow().isoformat()}


# ============================================================
# 🚀 Endpoint: /trend
# ============================================================
@router.get("/trend")
async def get_trend(limit: int = Query(300, ge=1, le=2000)):
    """Weekly Mon..Sun trend counts by category."""
    history = _read_jsonl(HISTORY_PATH, limit)
    if not history:
        history = _read_jsonl(LOG_PATH, limit)
    return {"trend": weekly_trend(history), "updated": datetime.utcnow().isoformat()}


# ============================================================
# 🚀 Endpoint: /recent
# ============================================================
@router.get("/recent")
async def get_recent(limit: int = Query(100, ge=1, le=1000)):
    """Returns a chronological list of recent user-visible actions."""
    history = _read_jsonl(HISTORY_PATH, limit)
    if not history:
        history = _read_jsonl(LOG_PATH, limit)
    return {"events": summarize_history(history)}


# ============================================================
# 🚀 Endpoint: /types
# ============================================================
@router.get("/types")
async def list_event_types():
    """Returns a deduplicated list of event types for frontend filters."""
    events = _read_jsonl(LOG_PATH, 1000)
    types = sorted({(e.get("event") or e.get("type") or "").lower() for e in events if (e.get("event") or e.get("type"))})
    return {"types": types}


# ============================================================
# 🧠 Endpoint: /metrics
# ============================================================
@router.get("/metrics")
async def metrics_summary():
    """Returns lightweight numeric insights (for quick dashboard cards)."""
    events = _read_jsonl(LOG_PATH, 500)
    if not events:
        return {
            "optimize": 0,
            "coverletters": 0,
            "superhuman": 0,
            "talk": 0,
            "mastermind": 0,
            "updated": datetime.utcnow().isoformat(),
        }

    summary = summarize_events(events)
    return {
        "optimize": summary["optimize_runs"],
        "coverletters": summary["coverletters"],
        "superhuman": summary["superhuman_calls"],
        "talk": summary["talk_queries"],
        "mastermind": summary["mastermind_chats"],
        "updated": datetime.utcnow().isoformat(),
    }


# ============================================================
# 🧾 Endpoint: /raw
# ============================================================
@router.get("/raw")
async def raw_dump(limit: int = Query(100, ge=1, le=2000)):
    """
    Developer-only diagnostic endpoint: returns raw JSON lines.
    Use for backend debugging or analytics export.
    """
    events = _read_jsonl(LOG_PATH, limit)
    return {"count": len(events), "events": events}
