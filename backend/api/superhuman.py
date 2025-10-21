"""
============================================================
 HIREX v2.1.0 — superhuman.py
 ------------------------------------------------------------
 SuperHuman Humanizer API
  • Rewrites text for clarity, flow, and tone
  • Preserves factual integrity and metrics
  • Supports resume, coverletter, paragraph, sentence modes
  • LaTeX-safe output for integration with HIREX optimizer

 Author: Sri Akash Kadali
============================================================
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import List, Union, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from openai import AsyncOpenAI

from backend.core import config
from backend.core.utils import log_event
from backend.core.security import secure_tex_input

router = APIRouter(prefix="/api/superhuman", tags=["superhuman"])
openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# ---------------------------------------------
# Defaults (can be overridden in request.model)
# ---------------------------------------------
_DEFAULT_MODEL = getattr(config, "SUPERHUMAN_MODEL", getattr(config, "DEFAULT_MODEL", "gpt-4o-mini"))
_MAX_ITEMS = 25


# ============================================================
# 🧠 REQUEST MODEL
# ============================================================
class RewriteRequest(BaseModel):
    text: Union[str, List[str]] = Field(..., description="Text or list of texts to rewrite.")
    mode: str = Field("paragraph", description="sentence | paragraph | resume | coverletter | custom")
    tone: str = Field("balanced", description="formal | balanced | conversational | confident | academic")
    latex_safe: bool = Field(True, description="If true, escapes LaTeX control chars safely.")
    constraints: Dict[str, Any] = Field(
        default_factory=lambda: {"no_fabrication": True, "keep_metrics": True},
        description="Behavior guards, e.g., no_fabrication, keep_metrics",
    )
    max_len: int = Field(1600, description="Max input chars per item (truncate beyond).")
    model: str = Field(_DEFAULT_MODEL, description="OpenAI model id to use.")


# ============================================================
# 🧩 PROMPT BUILDER
# ============================================================
def build_system_prompt(mode: str, tone: str, constraints: dict) -> str:
    """Generate adaptive rewrite instructions based on mode, tone, and constraints."""
    tone = (tone or "balanced").lower().strip()
    mode = (mode or "custom").lower().strip()

    tone_desc = {
        "formal": "clear, precise, and professional",
        "balanced": "natural and confident — a blend of formal and casual",
        "conversational": "friendly, easy to read, and simple",
        "confident": "assertive, concise, and motivational",
        "academic": "structured, objective, and technically articulate",
    }.get(tone, "neutral and professional")

    base = (
        f"You are SuperHuman — an advanced rewriting engine that enhances clarity, flow, "
        f"and tone while preserving meaning and truth. Use a {tone_desc} tone. "
        "Never invent or exaggerate facts."
    )

    mode_map = {
        "resume": (
            "Rewrite as crisp resume bullet text with strong action verbs. "
            "Keep technical terms intact and preserve metrics (%, $, numbers). "
            "Output a single line per bullet without leading symbols."
        ),
        "coverletter": (
            "Rewrite as persuasive yet sincere paragraphs suitable for a cover letter body. "
            "Prefer 2–4 sentences per paragraph, smooth transitions, and no clichés."
        ),
        "sentence": "Refine each sentence for fluency and correctness.",
        "paragraph": "Improve paragraph flow and readability, maintaining structure and intent.",
        "custom": "Rewrite text naturally for clarity and correctness.",
    }
    base += " " + mode_map.get(mode, mode_map["custom"])

    if constraints.get("no_fabrication", True):
        base += " Never add information not found in the original."
    if constraints.get("keep_metrics", True):
        base += " Retain all numbers, metrics, and proper nouns verbatim."

    base += " Output plain rewritten text only — no commentary, lists, or prefixes."
    return base


# ============================================================
# 🧼 POST-PROCESSING
# ============================================================
def _resp_text(resp) -> str:
    """Robustly extract text from OpenAI Responses API object."""
    try:
        t = getattr(resp, "output_text", None)
        if t:
            return str(t).strip()
    except Exception:
        pass
    try:
        return str(resp.output[0].content[0].text).strip()
    except Exception:
        return ""


def _strip_md_fences(s: str) -> str:
    return s.replace("```latex", "").replace("```", "").strip()


def _postprocess(mode: str, text: str, latex_safe: bool) -> str:
    t = _strip_md_fences(text)
    # normalize whitespace
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s+\n", "\n", t).strip()

    if mode.lower().strip() == "resume":
        # resume bullets should be single-line; remove trailing period if redundant
        t = re.sub(r"\s*\n\s*", " ", t).strip()
        t = t.rstrip(".")
    if latex_safe:
        t = secure_tex_input(t)
    return t


# ============================================================
# ⚙️ CORE REWRITE OPERATION
# ============================================================
async def rewrite_single(
    text: str,
    mode: str,
    tone: str,
    constraints: dict,
    latex_safe: bool,
    max_len: int,
    model: str,
) -> str:
    """Rewrite a single text unit via OpenAI."""
    if not config.OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY missing in environment.")

    system_prompt = build_system_prompt(mode, tone, constraints)
    text = (text or "").strip()[: max(1, max_len)]

    if not text:
        return ""

    start_time = time.time()
    try:
        resp = await openai_client.responses.create(
            model=model,
            input=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
            temperature=0.45,
            max_output_tokens=600,
        )
        rewritten_raw = _resp_text(resp) or text
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SuperHuman rewrite failed: {e}")

    latency = round(time.time() - start_time, 2)
    rewritten = _postprocess(mode, rewritten_raw, latex_safe)

    log_event(
        "superhuman_rewrite_single",
        {"mode": mode, "tone": tone, "model": model, "chars": len(text), "latency": latency},
    )
    return rewritten


# ============================================================
# 🚀 MAIN ENDPOINT
# ============================================================
@router.post("/rewrite")
async def rewrite_text(req: RewriteRequest):
    """
    SuperHuman rewrite engine — transforms one or more text inputs.
    Returns enhanced, optionally LaTeX-safe versions.
    """
    if not req.text:
        raise HTTPException(status_code=400, detail="No text provided.")

    items = req.text if isinstance(req.text, list) else [req.text]
    if len(items) > _MAX_ITEMS:
        raise HTTPException(status_code=413, detail=f"Too many items (max {_MAX_ITEMS}).")

    tasks = [
        rewrite_single(t, req.mode, req.tone, req.constraints, req.latex_safe, req.max_len, req.model)
        for t in items
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    # Log aggregate summary
    log_event(
        "superhuman_batch",
        {
            "count": len(items),
            "mode": req.mode,
            "tone": req.tone,
            "model": req.model,
            "latex_safe": req.latex_safe,
        },
    )

    return {"rewritten": results if isinstance(req.text, list) else results[0]}
