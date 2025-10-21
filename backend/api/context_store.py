# ============================================================
#  HIREX v2.1.0 — context_store.py
#  Store & retrieve JD + (optimized/humanized) resume context.
#  Title = company_role_YYYYMMDD-HHMMSS (for memory only).
# ============================================================

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Form
from backend.core import config
from backend.core.utils import safe_filename, log_event

router = APIRouter(prefix="/api/context", tags=["context"])

CONTEXT_DIR: Path = config.get_contexts_dir()


# ---------------------- internal helpers ----------------------

def _nowstamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S")


def _ctx_path(id_or_title: str) -> Path:
    """
    Map an arbitrary id/title to a safe JSON file path.
    Accepts raw 'company_role_YYYYMMDD-HHMMSS' strings.
    """
    return CONTEXT_DIR / f"{safe_filename(id_or_title)}.json"


def _latest_path() -> Optional[Path]:
    files = sorted(
        CONTEXT_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    return files[0] if files else None


def _read(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _compact_meta(d: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": d.get("id"),
        "title": d.get("title"),
        "company": d.get("company"),
        "role": d.get("role"),
        "saved_at": d.get("saved_at"),
        "model": d.get("model"),
        "fit_score": d.get("fit_score"),
    }


# -------------------------- routes ----------------------------

@router.post("/save")
async def save_context(
    company: str = Form(...),
    role: str = Form(...),
    jd_text: str = Form(...),
    resume_tex: str = Form(""),
    humanized_tex: str = Form(""),
    pdf_base64: str = Form(""),
    pdf_base64_humanized: str = Form(""),
    model: str = Form(""),
    fit_score: str = Form(""),
):
    """
    Persist a context blob so Talk-to-HIREX can answer later
    without resending JD/Resume. The title is for memory only;
    it does NOT alter the actual filenames of your generated PDFs.
    """
    title = f"{company}_{role}_{_nowstamp()}"
    ctx_id = title  # simple id; retrieval uses same string

    payload = {
        "id": ctx_id,
        "title": title,
        "company": company,
        "role": role,
        "jd_text": jd_text,
        "resume_tex": resume_tex,
        "humanized_tex": humanized_tex or resume_tex,
        "pdf_base64": pdf_base64,
        "pdf_base64_humanized": pdf_base64_humanized,
        "model": model or getattr(config, "DEFAULT_MODEL", "gpt-4o-mini"),
        "fit_score": fit_score,
        "saved_at": datetime.utcnow().isoformat(),
        "app_version": getattr(config, "APP_VERSION", "2.x"),
    }

    path = _ctx_path(ctx_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    log_event("context_saved", {"title": title, "company": company, "role": role})

    return {"ok": True, "context_id": ctx_id, "title": title}


@router.get("/list")
async def list_contexts(limit: int = 50):
    """
    Return recent contexts (newest first) with compact metadata.
    """
    files = sorted(
        CONTEXT_DIR.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )[: max(1, min(limit, 500))]

    out = [_compact_meta(_read(p)) for p in files]
    return {"items": out}


@router.get("/get")
async def get_context(id_or_title: str = "", latest: bool = False):
    """
    Fetch a full saved context by id/title, or the latest one.
    """
    path = _latest_path() if (latest or not id_or_title.strip()) else _ctx_path(id_or_title)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Context not found")
    return _read(path)


@router.delete("/delete")
async def delete_context(id_or_title: str):
    """
    Delete a single context by id/title.
    """
    path = _ctx_path(id_or_title)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Context not found")
    path.unlink()
    log_event("context_deleted", {"id": id_or_title})
    return {"deleted": True}
