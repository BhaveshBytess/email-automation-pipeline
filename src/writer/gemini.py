"""
Gemini-powered email writer for the Cold Email Pipeline.

Generates personalized cold emails via Google Gemini API with
post-generation validation and automatic fallback.

Conforms to:
- contracts.md Section 6.4
- agent_project.md Section 5.2 (email content rules)
- build_plan.md Module 2 (exit criteria)
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import google.generativeai as genai

from src.writer.fallback import generate_fallback

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resume bullets — single source of truth from agent_project.md Section 6
# ---------------------------------------------------------------------------

_RESUME_BULLETS: list[str] = [
    (
        "Built a temporal GNN (TRDGNN) achieving 0.58 PR-AUC on a 203K-node "
        "fraud detection graph with strict zero-leakage temporal constraints "
        "and 100% test coverage — PyTorch Geometric, XGBoost."
    ),
    (
        "Engineered a PDF-to-JSON extraction pipeline with 100% JSON validity "
        "and 81% evidence precision using LLMs, Pydantic validation, and "
        "multi-backend API integration (Gemma, DeepSeek) — Python, Streamlit."
    ),
    (
        "Optimized GNN architecture 10x parameter reduction (500K to 50K) "
        "with +108% performance gain — production deployment on "
        "resource-constrained systems."
    ),
    (
        "Python, PyTorch, PyTorch Geometric, TensorFlow, scikit-learn, "
        "Docker, Git, Linux, Streamlit, Pydantic, NumPy, Pandas."
    ),
    (
        "CS undergrad at IIIT Kota specializing in GNNs and unstructured "
        "data pipelines — building production-ready ML systems with clean "
        "engineering principles, full test coverage, and reproducible research."
    ),
]

# ---------------------------------------------------------------------------
# Banned words / phrases — validated post-generation
# ---------------------------------------------------------------------------

_BANNED_PHRASES: list[str] = [
    "i hope this email finds you well",
    "passionate",
    "synergy",
    "leverage",
]

# ---------------------------------------------------------------------------
# Gemini prompt
# ---------------------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are writing a cold outreach email from Bhavesh, a CS undergrad at IIIT Kota, \
to {person_name} ({person_title}) at {company}.

Context about their company/role:
{jd_summary}

Bhavesh's resume highlights (pick ONE to reference naturally):
{resume_text}

STRICT RULES — violating any of these means the email fails:
1. Plain text only. No markdown, no bullet points, no asterisks, no bold.
2. Maximum 150 words in the body. Shorter is better.
3. Do NOT use: "I hope this email finds you well", "passionate", "synergy", "leverage".
4. MUST mention "{company}" by name in the body.
5. MUST reference exactly one resume project naturally (not copy-pasted).
6. Tone: direct, competent, human. Like a peer reaching out. Not a student begging.
7. Vary sentence length. Mix short and medium sentences.
8. Include one casual phrase (e.g., "cool stuff", "no pressure", "figured I'd reach out").
9. Sign off as "Bhavesh" (no last name).

OUTPUT FORMAT (follow exactly):
SUBJECT_1: [first subject line — question format]
SUBJECT_2: [second subject line — statement format]
SUBJECT_3: [third subject line — name drop format]
BODY:
[email body here]
"""

_RETRY_SUFFIX = "\n\nIMPORTANT: Your previous attempt was too long. Keep it under 120 words this time."


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def _parse_gemini_response(text: str) -> Optional[dict]:
    """Parse the structured Gemini response into subject_options + body.

    Returns None if the response doesn't match expected format.
    """
    lines = text.strip().split("\n")
    subjects: list[str] = []
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        if line.startswith("SUBJECT_1:"):
            subjects.append(line.split(":", 1)[1].strip())
        elif line.startswith("SUBJECT_2:"):
            subjects.append(line.split(":", 1)[1].strip())
        elif line.startswith("SUBJECT_3:"):
            subjects.append(line.split(":", 1)[1].strip())
        elif line.strip() == "BODY:":
            in_body = True
        elif in_body:
            body_lines.append(line)

    if len(subjects) != 3:
        return None

    body = "\n".join(body_lines).strip()
    if not body:
        return None

    return {"subject_options": subjects, "body": body}


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _word_count(text: str) -> int:
    """Return the number of words in *text*."""
    return len(text.split())


def _contains_banned(text: str) -> bool:
    """Return True if *text* contains any banned phrase."""
    lower = text.lower()
    return any(phrase in lower for phrase in _BANNED_PHRASES)


def _contains_company(text: str, company: str) -> bool:
    """Return True if company name appears in text (case-insensitive)."""
    return company.lower() in text.lower()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_email(
    person_name: str,
    person_title: str,
    company: str,
    jd_summary: str,
    resume_bullets: Optional[list[str]] = None,
) -> dict:
    """Generate a personalized email via Gemini API.

    Returns ``{"subject_options": [str, str, str], "body": str}``.

    Post-generation validation:
    - body > 150 words → retry once, then fallback
    - banned phrases detected → fallback
    - company name missing from body → fallback
    - subject_options ≠ 3 → fallback
    - any API/parse error → fallback

    Falls back to ``generate_fallback()`` on any failure.
    """
    if resume_bullets is None:
        resume_bullets = _RESUME_BULLETS

    resume_text = "\n".join(f"- {b}" for b in resume_bullets)

    prompt = _PROMPT_TEMPLATE.format(
        person_name=person_name,
        person_title=person_title,
        company=company,
        jd_summary=jd_summary or "No specific details available.",
        resume_text=resume_text,
    )

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — using fallback template")
        return _fallback_for(person_name, company, resume_bullets)

    try:
        genai.configure(api_key=api_key)
        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
        model = genai.GenerativeModel(model_name)

        # First attempt
        response = model.generate_content(prompt)
        result = _parse_gemini_response(response.text)

        if result is None:
            logger.warning("Gemini response parse failed — using fallback")
            return _fallback_for(person_name, company, resume_bullets)

        # Validate word count — retry once if over
        if _word_count(result["body"]) > 150:
            logger.info("Body over 150 words (%d), retrying", _word_count(result["body"]))
            retry_response = model.generate_content(prompt + _RETRY_SUFFIX)
            retry_result = _parse_gemini_response(retry_response.text)

            if retry_result is None or _word_count(retry_result["body"]) > 150:
                logger.warning("Retry still over 150 words — using fallback")
                return _fallback_for(person_name, company, resume_bullets)
            result = retry_result

        # Validate subject count
        if len(result["subject_options"]) != 3:
            logger.warning("Subject options ≠ 3 — using fallback")
            return _fallback_for(person_name, company, resume_bullets)

        # Validate banned phrases
        if _contains_banned(result["body"]):
            logger.warning("Banned phrase detected — using fallback")
            return _fallback_for(person_name, company, resume_bullets)

        # Validate company name present
        if not _contains_company(result["body"], company):
            logger.warning("Company name missing from body — using fallback")
            return _fallback_for(person_name, company, resume_bullets)

        logger.info("Gemini email generated for %s at %s (%d words)",
                     person_name, company, _word_count(result["body"]))
        return result

    except Exception:
        logger.warning("Gemini API error — using fallback", exc_info=True)
        return _fallback_for(person_name, company, resume_bullets)


def _fallback_for(person_name: str, company: str, resume_bullets: list[str]) -> dict:
    """Build a fallback email using the first resume bullet."""
    # Pick the most impressive project bullet (index 0)
    return generate_fallback(
        person_name=person_name,
        company=company,
        relevant_skill="ML/AI",
        project_name="TRDGNN fraud detection system",
        project_desc=resume_bullets[0] if resume_bullets else "ML engineering project",
    )
