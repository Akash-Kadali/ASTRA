# ============================================================
#  HIREX v2.0.0 — Cover Letter Generation Endpoint
#  ------------------------------------------------------------
#  Features:
#   • Extracts company & role from JD
#   • Drafts contextual body paragraphs from JD + Resume
#   • Optionally humanizes tone via /api/superhuman
#   • Injects body into LaTeX base template and compiles PDF
#   • Returns both .tex source & base64-encoded PDF
#  Author: Sri Akash Kadali
# ============================================================

from __future__ import annotations

import base64
import json
import re
from typing import Tuple

import httpx
from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI

from backend.core import config
from backend.core.utils import log_event
from backend.core.compiler import compile_latex_safely
from backend.core.security import secure_tex_input
from api.render_tex import render_final_tex  # keep your existing import path

router = APIRouter(prefix="/api", tags=["coverletter"])
openai_client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# Prefer configured models; fall back safely
_EXTRACT_MODEL = getattr(config, "COVERLETTER_MODEL", getattr(config, "DEFAULT_MODEL", "gpt-4o-mini"))
_DRAFT_MODEL = getattr(config, "COVERLETTER_MODEL", getattr(config, "DEFAULT_MODEL", "gpt-4o-mini"))


# ============================================================
# 🧩 Common: robust text extractor for Responses API
# ============================================================
def _resp_text(resp) -> str:
    """
    Try several shapes of the OpenAI Responses API to get text.
    """
    try:
        # Some SDK builds expose .output_text
        t = getattr(resp, "output_text", None)
        if t:
            return str(t).strip()
    except Exception:
        pass
    try:
        # Canonical: resp.output[0].content[0].text
        return str(resp.output[0].content[0].text).strip()
    except Exception:
        return ""


# ============================================================
# 🔍 Extract Company + Role from JD
# ============================================================
async def extract_company_role(jd_text: str) -> Tuple[str, str]:
    """Parse company and role name using GPT (fallback-safe)."""
    jd_excerpt = (jd_text or "").strip()[:3500]
    prompt = (
        "Extract company name and role title from the job description below.\n"
        "Respond strictly as JSON: {\"company\": \"...\", \"role\": \"...\"}\n\n"
        f"{jd_excerpt}"
    )
    try:
        resp = await openai_client.responses.create(
            model=_EXTRACT_MODEL,
            input=prompt,
            temperature=0.2,
            max_output_tokens=120,
        )
        raw = _resp_text(resp)
        # Try strict JSON parse
        try:
            data = json.loads(raw)
            company = (data.get("company") or "Company").strip()
            role = (data.get("role") or "Role").strip()
            return company, role
        except Exception:
            # Fallback: regex probe
            m = re.search(r'"company"\s*:\s*"([^"]+)"[^}]*"role"\s*:\s*"([^"]+)"', raw)
            if m:
                return m.group(1).strip(), m.group(2).strip()
            return "Company", "Role"
    except Exception as e:
        log_event("coverletter_extract_fail", {"error": str(e)})
        return "Company", "Role"


# ============================================================
# ✍️ Draft Cover-Letter Body
# ============================================================
async def draft_cover_body(jd_text: str, resume_text: str, company: str, role: str, tone: str, length: str) -> str:
    """
    Create 2–4 concise, factual paragraphs grounded in JD + resume.
    The 'length' hint can be: short | standard | long
    """
    length = (length or "standard").lower().strip()
    if length not in {"short", "standard", "long"}:
        length = "standard"

    length_hint = {
        "short": "Limit to ~120–180 words (1–2 compact paragraphs).",
        "standard": "Target ~180–280 words (2–3 concise paragraphs).",
        "long": "Allow up to ~300–400 words (3–4 tight paragraphs).",
    }[length]

    sys_prompt = (
        f"You are an expert technical writer creating the **BODY** of a cover letter "
        f"for a candidate applying to {role} at {company}. "
        "Ground strictly in the candidate’s resume and the job description. "
        "Do NOT include greeting or closing lines. "
        f"{length_hint} Keep the tone {tone} and professional. Avoid fluff."
    )

    user_prompt = f"Job Description:\n{(jd_text or '')[:3500]}\n\nCandidate Resume:\n{(resume_text or '')[:3500]}"

    try:
        resp = await openai_client.responses.create(
            model=_DRAFT_MODEL,
            input=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}],
            temperature=0.55,
            max_output_tokens=800,
        )
        body = _resp_text(resp)
        # Sanitize for LaTeX early
        return secure_tex_input(body)
    except Exception as e:
        log_event("coverletter_draft_fail", {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Body generation failed: {e}")


# ============================================================
# 🧠 Humanize Text (via internal /api/superhuman)
# ============================================================
async def humanize_text(body_text: str, tone: str) -> str:
    url = f"{config.API_BASE_URL}/api/superhuman/rewrite"
    payload = {"text": body_text, "mode": "coverletter", "tone": tone, "latex_safe": True}
    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            r = await client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
        return data.get("rewritten") or data.get("text") or body_text
    except Exception as e:
        log_event("superhuman_handoff_fail", {"error": str(e)})
        return body_text  # fallback gracefully


# ============================================================
# 🧩 Inject Body into LaTeX Template
# ============================================================
def inject_body_into_template(base_tex: str, body_tex: str) -> str:
    """
    Insert the generated body between BODY-START / BODY-END anchors.
    If anchors are missing, append a marked body section.
    """
    safe_body = secure_tex_input(body_tex)
    pattern = r"(%-+BODY-START-+%)(.*?)(%-+BODY-END-+%)"
    if re.search(pattern, base_tex, flags=re.S):
        return re.sub(pattern, f"\\1\n{safe_body}\n\\3", base_tex, flags=re.S)
    # anchors missing — append
    return (
        base_tex
        + "\n\n%-----------BODY-START-----------\n"
        + safe_body
        + "\n%-----------BODY-END-------------\n"
    )


# ============================================================
# 🚀 Main Endpoint: /api/coverletter
# ============================================================
@router.post("/coverletter")
async def generate_coverletter(
    jd_text: str = Form(...),
    resume_tex: str = Form(""),
    use_humanize: bool = Form(True),
    tone: str = Form("balanced"),
    length: str = Form("standard"),
):
    """
    Generate an AI-optimized cover letter body, inject into LaTeX base,
    compile to PDF, and return {company, role, tex_string, pdf_base64}.
    """
    if not config.OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY missing in environment.")

    if not (jd_text or "").strip():
        raise HTTPException(status_code=400, detail="jd_text is required.")

    # 1) Extract company + role
    company, role = await extract_company_role(jd_text)

    # 2) Draft initial body
    body_text = await draft_cover_body(jd_text, resume_tex, company, role, tone, length)

    # 3) Optional humanization
    if use_humanize:
        body_text = await humanize_text(body_text, tone)

    # 4) Load base template
    base_path = config.BASE_COVERLETTER_PATH
    try:
        with open(base_path, encoding="utf-8") as f:
            base_tex = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Base cover-letter template not found")

    # 5) Render + compile
    final_tex = render_final_tex(inject_body_into_template(base_tex, body_text))
    pdf_bytes = compile_latex_safely(final_tex) or b""
    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

    # 6) Log generation event
    log_event(
        "coverletter_generated",
        {
            "company": company,
            "role": role,
            "tone": tone,
            "use_humanize": use_humanize,
            "length": length,
            "chars": len(body_text or ""),
        },
    )

    # 7) Respond with assets
    return JSONResponse(
        {
            "company": company,
            "role": role,
            "tone": tone,
            "use_humanize": use_humanize,
            "tex_string": final_tex,
            "pdf_base64": pdf_b64,
        }
    )
