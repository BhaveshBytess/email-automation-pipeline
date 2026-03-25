"""
Tests for the email writer (Gemini + fallback templates).

Covers contracts.md Section 6.4 — six required test cases.
All Gemini tests mock the API call — no real API key needed.
"""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.writer.fallback import generate_fallback
from src.writer.gemini import generate_email


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A well-formed Gemini response (under 150 words, contains company, references resume)
_GOOD_RESPONSE_TEXT = """\
SUBJECT_1: Quick question about Acme Corp's ML stack?
SUBJECT_2: Fraud detection GNN work relevant to Acme Corp
SUBJECT_3: Bhavesh — ML engineer, built TRDGNN
BODY:
Hi Alex,

Saw Acme Corp is scaling its ML pipeline — cool problem space. I recently built a temporal GNN for fraud detection that hit 0.58 PR-AUC on a 203K-node graph with zero data leakage. The architecture tricks I used for 10x parameter reduction might translate well to what your team is tackling.

Would a quick chat make sense? No pressure either way.

Cheers,
Bhavesh
"""


def _mock_model_response(text: str):
    """Build a mock Gemini model that returns *text*."""
    mock_response = MagicMock()
    mock_response.text = text

    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response
    return mock_model


# ---------------------------------------------------------------------------
# 6.4.1 — Gemini writer returns string under 150 words
# ---------------------------------------------------------------------------


def test_gemini_under_150_words():
    """Mock Gemini API → body under 150 words."""
    mock_model = _mock_model_response(_GOOD_RESPONSE_TEXT)

    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
         patch("src.writer.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = mock_model

        result = generate_email(
            person_name="Alex",
            person_title="CTO",
            company="Acme Corp",
            jd_summary="Building ML pipelines for fraud detection.",
        )

    assert len(result["body"].split()) <= 150


# ---------------------------------------------------------------------------
# 6.4.2 — Gemini writer includes company name in output
# ---------------------------------------------------------------------------


def test_gemini_includes_company():
    """Mock Gemini API → body contains company name."""
    mock_model = _mock_model_response(_GOOD_RESPONSE_TEXT)

    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
         patch("src.writer.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = mock_model

        result = generate_email(
            person_name="Alex",
            person_title="CTO",
            company="Acme Corp",
            jd_summary="Building ML pipelines.",
        )

    assert "Acme Corp" in result["body"]


# ---------------------------------------------------------------------------
# 6.4.3 — Gemini writer includes at least one resume project reference
# ---------------------------------------------------------------------------


def test_gemini_includes_resume_ref():
    """Mock Gemini API → body contains resume project reference."""
    mock_model = _mock_model_response(_GOOD_RESPONSE_TEXT)

    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
         patch("src.writer.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = mock_model

        result = generate_email(
            person_name="Alex",
            person_title="CTO",
            company="Acme Corp",
            jd_summary="Building ML pipelines.",
        )

    body_lower = result["body"].lower()
    # Should reference at least one project keyword
    project_refs = ["gnn", "trdgnn", "fraud detection", "pdf-to-json", "parameter reduction"]
    assert any(ref in body_lower for ref in project_refs), \
        f"Body should reference a resume project: {result['body']}"


# ---------------------------------------------------------------------------
# 6.4.4 — Fallback template fills all placeholders without KeyError
# ---------------------------------------------------------------------------


def test_fallback_no_keyerror():
    """Fallback fills all placeholders without KeyError."""
    # Should not raise
    result = generate_fallback(
        person_name="Dana",
        company="TechStartup Inc",
        relevant_skill="deep learning",
        project_name="TRDGNN",
        project_desc="Temporal GNN for fraud detection with 0.58 PR-AUC.",
    )

    assert isinstance(result, dict)
    assert "subject_options" in result
    assert "body" in result
    assert "Dana" in result["body"]
    assert "TechStartup Inc" in result["body"]
    assert "TRDGNN" in result["body"]


# ---------------------------------------------------------------------------
# 6.4.5 — Fallback template is under 150 words
# ---------------------------------------------------------------------------


def test_fallback_under_150_words():
    """Fallback body under 150 words."""
    result = generate_fallback(
        person_name="Sam",
        company="CloudAI",
        relevant_skill="NLP",
        project_name="PDF-to-JSON pipeline",
        project_desc="100% JSON validity, 81% evidence precision.",
    )

    word_count = len(result["body"].split())
    assert word_count <= 150, f"Fallback body is {word_count} words (max 150)"


# ---------------------------------------------------------------------------
# 6.4.6 — Subject generator returns exactly 3 options
# ---------------------------------------------------------------------------


def test_subject_returns_3_options():
    """Subject options list has exactly 3 items."""
    # Test via Gemini mock
    mock_model = _mock_model_response(_GOOD_RESPONSE_TEXT)

    with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}), \
         patch("src.writer.gemini.genai") as mock_genai:
        mock_genai.GenerativeModel.return_value = mock_model

        result = generate_email(
            person_name="Alex",
            person_title="CTO",
            company="Acme Corp",
            jd_summary="Building ML pipelines.",
        )

    assert len(result["subject_options"]) == 3

    # Also test via fallback
    fallback = generate_fallback(
        person_name="Alex",
        company="Acme Corp",
        relevant_skill="ML",
        project_name="TRDGNN",
        project_desc="Fraud detection GNN.",
    )
    assert len(fallback["subject_options"]) == 3
