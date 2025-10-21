"""
============================================================
 HIREX v2.1.0 — talk.py
 ------------------------------------------------------------
 "Talk to HIREX" conversational endpoint.
 Answers job-application or interview questions using
 JD + resume context with optional SuperHuman humanization.

 Author: Sri Akash Kadali
============================================================
"""

import json
import time
from pathlib import Path
from typing import Optional, Dict, Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import AsyncOpenAI

from backend.core import config
from backend.core.utils import log_event, safe_filename
from backend.core.security import secure_tex_input

router = APIRouter(prefix="/api/talk", tags=["talk"])
openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# Where /api/context/save stores contexts
CONTEXT_DIR: Path = config.get_contexts_dir()

# Cheap, reliable summarizer model (override-able from env)
SUMMARIZER_MODEL = getattr(config, "TALK_SUMMARY_MODEL", "gpt-4o-mini")


# ============================================================
# 🧠 REQUEST MODEL
# ============================================================
class TalkReq(BaseModel):
    # If jd_text / resume are omitted, service will pull from saved context.
    jd_text: str = ""
    question: str
    resume_tex: Optional[str] = None
    resume_plain: Optional[str] = None
    tone: str = "balanced"
    humanize: bool = True
    model: str = getattr(config, "DEFAULT_MODEL", "gpt-4o-mini")

    # 🔁 Context fallback controls
    context_id: Optional[str] = None          # equals saved title/id
    title: Optional[str] = None               # alias of context_id
    use_latest: bool = True                   # if no id/title, use latest saved


# ============================================================
# 🧩 CONTEXT HELPERS
# ============================================================

def _ctx_path(id_or_title: str) -> Path:
    return CONTEXT_DIR / f"{safe_filename(id_or_title)}.json"


def _latest_path() -> Optional[Path]:
    files = sorted(CONTEXT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _read_json(path: Optional[Path]) -> Dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_context(context_id: Optional[str], title: Optional[str], use_latest: bool) -> Dict[str, Any]:
    path: Optional[Path] = None
    key = (context_id or title or "").strip()
    if key:
        path = _ctx_path(key)
    elif use_latest:
        path = _latest_path()
    ctx = _read_json(path)
    if ctx:
        log_event("talk_context_used", {"title": ctx.get("title"), "company": ctx.get("company")})
    return ctx


# ============================================================
# 🧩 MODEL CALL HELPERS
# ============================================================

async def extract_resume_summary(resume_tex: Optional[str], resume_plain: Optional[str]) -> str:
    """
    Compress resume content into factual bullet points.
    Strips formatting, avoids hallucination.
    """
    if not (resume_tex or resume_plain):
        return "No resume text provided."

    text_input = (resume_plain or resume_tex or "").strip()
    sys_prompt = (
        "Summarize this resume into 6–10 concise factual bullet points "
        "about key skills, technologies, and experiences. "
        "Do NOT fabricate or guess. Output plain-text bullets."
    )

    try:
        resp = await openai_client.responses.create(
            model=SUMMARIZER_MODEL,
            input=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text_input[:3500]},
            ],
            temperature=0.25,
            max_output_tokens=300,
        )
        # New Responses API shape
        summary_text = resp.output[0].content[0].text.strip()
        return secure_tex_input(summary_text)  # type: ignore
    except Exception as e:
        print(f"[WARN] Resume summarization failed: {e}")
        # Fallback to a truncated slice of the provided resume text
        return secure_tex_input(text_input[:1200])  # type: ignore


async def generate_answer(jd_text: str, resume_summary: str, question: str, model: str) -> str:
    """
    Produce factual, JD-aware short answers.
    Ensures truth alignment with resume.
    """
    sys_prompt = (
        "You are HIREX Assistant, an AI recruiter co-pilot. "
        "Use only information grounded in the job description and resume. "
        "Never fabricate or over-claim. "
        "Keep the tone professional, confident, and natural. "
        "Answer concisely in 1–3 sentences."
    )

    user_prompt = (
        f"Job Description:\n{jd_text[:3500]}\n\n"
        f"Resume Summary:\n{resume_summary}\n\n"
        f"Question:\n{question.strip()}"
    )

    start = time.time()
    try:
        resp = await openai_client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.55,
            max_output_tokens=300,
        )
        latency = round(time.time() - start, 2)
        answer = resp.output[0].content[0].text.strip()
        tokens = len(answer.split())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Answer generation failed: {e}")

    log_event("talk_answer_raw", {"latency": latency, "tokens": tokens, "model": model})
    return secure_tex_input(answer)  # type: ignore


async def humanize_text(answer_text: str, tone: str) -> str:
    """
    Refine the tone and flow via SuperHuman rewrite API.
    Falls back gracefully if unavailable.
    """
    url = f"{config.API_BASE_URL}/api/superhuman/rewrite"
    payload = {"text": answer_text, "mode": "paragraph", "tone": tone, "latex_safe": True}

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return secure_tex_input(data.get("rewritten", answer_text))  # type: ignore
    except Exception as e:
        print(f"[WARN] SuperHuman call failed: {e}")
        return answer_text


# ============================================================
# 🚀 MAIN ENDPOINT
# ============================================================
@router.post("/answer")
async def talk_to_hirex(req: TalkReq):
    """
    Generate a contextual, factual, optionally humanized answer for
    job-application or interview questions.

    Behavior:
      • If jd_text / resume not provided, pulls from the latest (or specified)
        saved context created by /api/context/save.
      • Returns both 'answer' (final) and 'draft_answer' (pre-humanize).
    """

    # Pull context if needed
    jd_text = (req.jd_text or "").strip()
    resume_tex = (req.resume_tex or "").strip()

    if not jd_text or not resume_tex:
        ctx = _load_context(req.context_id, req.title, req.use_latest)
        if ctx:
            jd_text = jd_text or (ctx.get("jd_text") or "")
            # Prefer humanized_tex; fall back to resume_tex
            resume_tex = resume_tex or (ctx.get("humanized_tex") or ctx.get("resume_tex") or "")
            ctx_title = ctx.get("title")
        else:
            ctx_title = None
    else:
        ctx_title = None

    if not jd_text.strip():
        raise HTTPException(status_code=400, detail="Job Description missing. Provide jd_text or save a context first.")
    if not (resume_tex or req.resume_plain):
        raise HTTPException(status_code=400, detail="Resume text missing. Provide resume_tex/plain or save a context first.")

    # 1) Resume summary
    resume_summary = await extract_resume_summary(resume_tex, req.resume_plain)

    # 2) Raw answer generation
    draft_answer = await generate_answer(jd_text, resume_summary, req.question, req.model)

    # 3) Optional humanization
    final_answer = await humanize_text(draft_answer, req.tone) if req.humanize else draft_answer

    # 4) Log metadata
    log_event(
        "talk_to_hirex",
        {
            "question": req.question,
            "tone": req.tone,
            "humanize": req.humanize,
            "jd_len": len(jd_text),
            "resume_len": len(resume_tex or req.resume_plain or ""),
            "model": req.model,
            "context_used": bool(ctx_title),
            "context_title": ctx_title,
        },
    )

    # 5) Structured return (include 'answer' alias for frontend)
    return {
        "question": req.question.strip(),
        "resume_summary": resume_summary,
        "draft_answer": draft_answer,
        "final_text": final_answer,
        "answer": final_answer,           # alias for UI compatibility
        "tone": req.tone,
        "humanized": req.humanize,
        "model": req.model,
        "context_title": ctx_title,
    }
