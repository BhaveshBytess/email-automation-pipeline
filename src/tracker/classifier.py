"""Reply classifier for Module 6 (tracker).

Uses Gemini when available and falls back to deterministic keyword matching.
Returns exactly one of: positive, neutral, negative.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _keyword_classify(body_text: str) -> str:
    """Deterministic fallback classifier.

    Returns exactly one of: positive, neutral, negative.
    """
    text = (body_text or "").lower()

    positive_markers = [
        "yes",
        "interested",
        "sounds good",
        "let's talk",
        "let us talk",
        "schedule",
        "share your resume",
        "next week",
        "great",
    ]
    negative_markers = [
        "not interested",
        "no thanks",
        "do not contact",
        "stop",
        "unsubscribe",
        "remove me",
        "take me off",
        "decline",
    ]

    if any(k in text for k in negative_markers):
        return "negative"
    if any(k in text for k in positive_markers):
        return "positive"
    return "neutral"


def classify_reply(body_text: str) -> str:
    """Classify a reply as positive, neutral, or negative.

    Attempts Gemini first when GEMINI_API_KEY is set; on any failure,
    falls back to keyword matching and never raises.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _keyword_classify(body_text)

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = (
            "Classify this email reply into exactly one label: "
            "positive, neutral, or negative. "
            "Return only the label.\n\n"
            f"Reply:\n{body_text}"
        )
        response = model.generate_content(prompt)
        label = (response.text or "").strip().lower()

        if label in {"positive", "neutral", "negative"}:
            return label

        # Defensive parsing if model includes extra text.
        for expected in ("positive", "neutral", "negative"):
            if expected in label:
                return expected

        return _keyword_classify(body_text)
    except Exception:
        logger.warning("Gemini classification failed; using keyword fallback", exc_info=True)
        return _keyword_classify(body_text)
