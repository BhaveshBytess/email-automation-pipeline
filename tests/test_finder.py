"""
Tests for Module 4 — Finder Waterfall + Role Match.

Per contracts.md Section 6.3:
 1. Role matcher identifies "CTO" from surrounding text.
 2. Role matcher identifies "Co-founder" from surrounding text.
 3. Role matcher returns None when no technical role is found.
 4. Role matcher prefers CTO over "Co-founder" when both exist.
 5. Email permutation generator produces expected patterns.
 6. Gravatar check returns True for known-existing hash (mocked).
 7. Gravatar check returns False for random hash (mocked).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.finder.role_match import find_technical_lead
from src.finder.waterfall import check_gravatar, generate_permutations


# -----------------------------------------------------------------------
# 1. Role matcher — CTO
# -----------------------------------------------------------------------


def test_role_match_cto():
    text = (
        "Meet our leadership team. "
        "Alice Johnson is our Senior Designer. "
        "She has been with the company for over ten years and leads all brand and creative efforts across the organisation. "
        "Bob Smith is the CTO and co-leads the engineering organisation. "
        "Carol Lee manages operations."
    )
    names = ["Alice Johnson", "Bob Smith", "Carol Lee"]
    result = find_technical_lead(text, names)
    assert result is not None
    name, title = result
    assert name == "Bob Smith"
    assert title == "CTO"


# -----------------------------------------------------------------------
# 2. Role matcher — Co-founder
# -----------------------------------------------------------------------


def test_role_match_cofounder():
    text = (
        "About Us. "
        "David Park, Co-founder, started the company in his garage. "
        "Eve Torres handles marketing."
    )
    names = ["David Park", "Eve Torres"]
    result = find_technical_lead(text, names)
    assert result is not None
    name, title = result
    assert name == "David Park"
    assert title == "Co-founder"


# -----------------------------------------------------------------------
# 3. Role matcher — no technical role
# -----------------------------------------------------------------------


def test_role_match_none():
    text = (
        "Our team includes a Head of Sales, Marketing Director, "
        "and Chief Financial Officer."
    )
    names = ["Frank Wu", "Grace Kim"]
    result = find_technical_lead(text, names)
    assert result is None


# -----------------------------------------------------------------------
# 4. Role matcher — prefers CTO over Co-founder
# -----------------------------------------------------------------------


def test_role_match_priority():
    """CTO must win over Co-founder even if Co-founder appears first."""
    text = (
        "Alice Johnson is a Co-founder who leads product. "
        "Bob Smith is the CTO."
    )
    names = ["Alice Johnson", "Bob Smith"]
    result = find_technical_lead(text, names)
    assert result is not None
    name, title = result
    assert name == "Bob Smith"
    assert title == "CTO"


# -----------------------------------------------------------------------
# 5. Email permutation generator
# -----------------------------------------------------------------------


def test_generate_permutations():
    perms = generate_permutations("John", "Doe", "acme.com")
    assert isinstance(perms, list)
    assert len(perms) == 8

    expected = {
        "john@acme.com",
        "john.doe@acme.com",
        "jdoe@acme.com",
        "j.doe@acme.com",
        "johndoe@acme.com",
        "doe@acme.com",
        "john_doe@acme.com",
        "doej@acme.com",
    }
    assert set(perms) == expected


# -----------------------------------------------------------------------
# 6. Gravatar — returns True (mocked 200)
# -----------------------------------------------------------------------


@patch("src.finder.waterfall.requests.get")
def test_gravatar_true(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp

    assert check_gravatar("known@example.com") is True
    mock_get.assert_called_once()


# -----------------------------------------------------------------------
# 7. Gravatar — returns False (mocked 404)
# -----------------------------------------------------------------------


@patch("src.finder.waterfall.requests.get")
def test_gravatar_false(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp

    assert check_gravatar("random_nonexistent_xyz@example.com") is False
    mock_get.assert_called_once()
