"""
HIREX • api/humanize.py (v2.0.0)
Integrates with AIHumanize.io for tone-only rewriting of Experience & Project bullets.
Targets only \resumeItem{...} entries, with strong LaTeX sanitization to avoid
preamble duplication or document corruption. Concurrency + retry hardened.

Author: Sri Akash Kadali
"""

from __future__ import annotations

import os
import re
import json
import asyncio
from dataclasses import dataclass
from typing import List, Tuple, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core import config
from backend.core.utils import log_event

# ============================================================
# ⚙️ Configuration
# ============================================================

AIHUMANIZE_API_URL = "https://aihumanize.io/api/v1/rewrite"

# UI modes → API numeric model ids
AIHUMANIZE_MODE_MAP = {
    "quality": "0",   # default
    "balance": "1",
    "enhanced": "2",
}

# Defaults (can be overridden per-request or via env)
AIHUMANIZE_DEFAULT_MODE = os.getenv("AIHUMANIZE_MODE", "quality").lower().strip()
AIHUMANIZE_DEFAULT_EMAIL = os.getenv("AIHUMANIZE_EMAIL", "kadali18@terpmail.umd.edu")

MAX_CONCURRENT = int(os.getenv("AIHUMANIZE_MAX_CONCURRENT", "5"))
TIMEOUT_SEC = float(os.getenv("AIHUMANIZE_TIMEOUT_SEC", "15.0"))
RETRIES = int(os.getenv("AIHUMANIZE_RETRIES", "2"))

# FastAPI router (optional for direct API usage)
router = APIRouter(prefix="/api/humanize", tags=["humanize"])


# ============================================================
# 🧽 LaTeX Sanitizer
# ============================================================

_BAD_PREAMBLE_PATTERNS = [
    r"(?i)\\documentclass(\[[^\]]*\])?\{[^}]*\}",
    r"(?i)\\usepackage(\[[^\]]*\])?\{[^}]*\}",
    r"(?i)\\begin\{document\}",
    r"(?i)\\end\{document\}",
    r"(?i)\\(new|renew)command\*?\{[^}]*\}\{[^}]*\}",
    r"(?i)\\input\{[^}]*\}",
]

def _escape_unescaped_percent(s: str) -> str:
    # Turn bare % into \% to avoid commenting out the remainder of the line
    return re.sub(r"(?<!\\)%", r"\\%", s)

def _strip_md_fences(s: str) -> str:
    s = s.replace("```latex", "").replace("```", "")
    return s

def clean_humanized_text(text: str) -> str:
    """
    Remove dangerous LaTeX preamble/commands and markdown fences.
    Keep content characters intact; do NOT strip braces globally.
    """
    cleaned = text or ""
    cleaned = _strip_md_fences(cleaned)

    for pat in _BAD_PREAMBLE_PATTERNS:
        cleaned = re.sub(pat, "", cleaned)

    # Remove leading LaTeX comments or decorative headers commonly injected
    cleaned = re.sub(r"(?m)^\s*%.*$", "", cleaned)

    # Normalize whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    # Escape stray %
    cleaned = _escape_unescaped_percent(cleaned)

    # Final safety check
    if re.search(r"\\documentclass|\\usepackage|\\begin\{document\}|\\end\{document\}", cleaned, re.I):
        # If we still see preamble markers, reject to avoid corrupting the .tex
        log_event("humanize_sanitizer_reject", {"reason": "preamble_detected"})
        return ""

    return cleaned


# ============================================================
# 🔎 Bullet Extraction (brace-aware)
# ============================================================

@dataclass
class BulletSpan:
    start: int
    end: int
    content: str

def _find_resume_items(tex: str) -> List[BulletSpan]:
    """
    Find \resumeItem{...} ranges with a simple brace-depth scan,
    so nested braces within the bullet are tolerated.
    """
    key = r"\resumeItem{"
    spans: List[BulletSpan] = []
    i = 0
    n = len(tex)
    while i < n:
        j = tex.find(key, i)
        if j == -1:
            break
        # position of opening brace content
        k = j + len(key)
        depth = 1
        p = k
        while p < n and depth > 0:
            ch = tex[p]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            p += 1
        if depth == 0:
            content = tex[k : p - 1]
            spans.append(BulletSpan(start=k, end=p - 1, content=content))
            i = p
        else:
            # Unbalanced; bail from loop
            break
    return spans


# ============================================================
# 🌐 AIHumanize Client
# ============================================================

async def _rewrite_bullet(
    client: httpx.AsyncClient,
    bullet_text: str,
    idx: int,
    mode_id: str,
    email: str,
) -> str:
    """
    Call AIHumanize for a single bullet with retry + sanitize.
    """
    headers = {
        "Authorization": config.HUMANIZE_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {"model": mode_id, "mail": email, "data": bullet_text}

    for attempt in range(RETRIES + 1):
        try:
            r = await client.post(AIHUMANIZE_API_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("code") == 200 and data.get("data"):
                candidate = clean_humanized_text(str(data["data"]).strip())
                if candidate:
                    log_event("aihumanize_bullet_ok", {"idx": idx, "len": len(candidate), "attempt": attempt})
                    return candidate
                else:
                    log_event("aihumanize_bullet_revert_unsafe", {"idx": idx, "attempt": attempt})
                    return bullet_text
            else:
                # Unexpected response shape — retry
                log_event("aihumanize_bad_response", {"idx": idx, "attempt": attempt, "resp": data})
        except Exception as e:
            log_event("aihumanize_bullet_error", {"idx": idx, "attempt": attempt, "error": str(e)})
        # backoff
        await asyncio.sleep(0.5 * (2 ** attempt))

    log_event("aihumanize_bullet_fallback", {"idx": idx})
    return bullet_text


# ============================================================
# 🧠 Public Core: Humanize all \resumeItem bullets
# ============================================================

async def humanize_resume_items(
    tex_content: str,
    mode: str = AIHUMANIZE_DEFAULT_MODE,
    email: Optional[str] = None,
) -> Tuple[str, int, int]:
    """
    Humanize all \resumeItem{...} bullets concurrently.

    Returns:
        (new_tex, total_found, total_rewritten)
    """
    if not config.HUMANIZE_API_KEY:
        raise RuntimeError("HUMANIZE_API_KEY missing in environment.")

    spans = _find_resume_items(tex_content or "")
    total_found = len(spans)
    if total_found == 0:
        log_event("aihumanize_no_bullets", {})
        return tex_content, 0, 0

    mode_id = AIHUMANIZE_MODE_MAP.get(mode.lower().strip(), AIHUMANIZE_MODE_MAP["quality"])
    mail = (email or AIHUMANIZE_DEFAULT_EMAIL).strip()

    limits = httpx.Limits(max_keepalive_connections=MAX_CONCURRENT, max_connections=MAX_CONCURRENT)
    timeout = httpx.Timeout(TIMEOUT_SEC)
    rewritten_texts: List[str] = []

    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        async def _task(idx: int, content: str) -> str:
            async with sem:
                content_stripped = content.strip()
                if not content_stripped:
                    return content
                return await _rewrite_bullet(client, content_stripped, idx, mode_id, mail)

        rewritten_texts = await asyncio.gather(
            *[_task(i + 1, b.content) for i, b in enumerate(spans)], return_exceptions=False
        )

    # Rebuild the LaTeX safely by slicing with recorded spans
    out_parts: List[str] = []
    last = 0
    total_rewritten = 0
    for (span, new_txt) in zip(spans, rewritten_texts):
        out_parts.append(tex_content[last:span.start])
        # ensure single trailing period is not duplicated; bullets usually avoid ending '.'
        safe_new = new_txt.strip().rstrip(".")
        if safe_new != span.content.strip():
            total_rewritten += 1
        out_parts.append(safe_new)
        last = span.end
    out_parts.append(tex_content[last:])

    new_tex = "".join(out_parts)

    # Final safety: strip accidental preamble fragments
    for pat in _BAD_PREAMBLE_PATTERNS:
        new_tex = re.sub(pat, "", new_tex)
    new_tex = re.sub(r"\n{3,}", "\n\n", new_tex).strip()

    log_event("aihumanize_complete", {"found": total_found, "rewritten": total_rewritten, "mode": mode})
    return new_tex, total_found, total_rewritten


# ============================================================
# 🌐 FastAPI endpoints (optional, convenient for frontend)
# ============================================================

class BulletsReq(BaseModel):
    tex_content: str = Field(..., description="LaTeX content containing \\resumeItem{...} bullets.")
    mode: str = Field(AIHUMANIZE_DEFAULT_MODE, description="quality | balance | enhanced")
    email: Optional[str] = Field(None, description="Account email for AIHumanize (optional override).")

@router.post("/bullets")
async def api_humanize_bullets(req: BulletsReq):
    """
    Rewrites only \\resumeItem{...} bullets inside the provided LaTeX string.
    Returns sanitized LaTeX. Requires HUMANIZE_API_KEY in env.
    """
    if not config.HUMANIZE_API_KEY:
        raise HTTPException(status_code=400, detail="HUMANIZE_API_KEY missing in environment.")
    try:
        new_tex, found, rewritten = await humanize_resume_items(req.tex_content, mode=req.mode, email=req.email)
        return {
            "ok": True,
            "tex_content": new_tex,
            "found": found,
            "rewritten": rewritten,
            "mode": req.mode,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AIHumanize processing failed: {e}")


# ============================================================
# 🧪 Local CLI test
# ============================================================

if __name__ == "__main__":
    async def _run():
        sample_tex = r"""
        \resumeItem{worked on python scripts for data processing}
        \resumeItem{helped team with docker deployments}
        \resumeItem{deployed 3 APIs with 99\% uptime}
        """
        # Note: requires HUMANIZE_API_KEY in your env to actually call service.
        try:
            out, found, rewritten = await humanize_resume_items(sample_tex, mode="quality")
            print("\n=== Found:", found, "Rewritten:", rewritten, "===\n")
            print(out)
        except Exception as e:
            print("Local test (no key?) error:", e)

    asyncio.run(_run())
