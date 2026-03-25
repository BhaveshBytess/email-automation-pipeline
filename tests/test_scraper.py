"""
Tests for the RSS scraper and manual queue loader.

Covers contracts.md Section 6.2 — five required test cases.
All RSS tests mock feedparser.parse to avoid network calls.
"""

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.scraper.manual import load_manual_queue
from src.scraper.rss import fetch_rss, merge_and_deduplicate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    with tempfile.TemporaryDirectory() as d:
        yield d


# ---------------------------------------------------------------------------
# RSS helpers
# ---------------------------------------------------------------------------


def _make_feed(entries: list[dict]) -> SimpleNamespace:
    """Build a fake feedparser result with the given entries."""
    parsed_entries = []
    for e in entries:
        entry = SimpleNamespace(
            title=e.get("title", ""),
            summary=e.get("summary", ""),
            link=e.get("link", ""),
            tags=[{"term": e["company"]}] if "company" in e else [],
        )
        parsed_entries.append(entry)
    return SimpleNamespace(entries=parsed_entries)


# ---------------------------------------------------------------------------
# 6.2.1 — RSS parser returns list of dicts with required keys
# ---------------------------------------------------------------------------


def test_rss_returns_required_keys():
    """Parsed output must have title, company, url, source keys."""
    fake_feed = _make_feed([
        {
            "title": "Backend Python Engineer",
            "summary": "Looking for a python backend developer.",
            "link": "https://example.com/job/1",
            "company": "Acme Corp",
        },
    ])

    with patch("src.scraper.rss.feedparser.parse", return_value=fake_feed):
        results = fetch_rss("https://fake.feed/rss", "rss_test")

    assert len(results) == 1
    job = results[0]
    for key in ("title", "company", "url", "source", "job_id", "jd_summary", "discovered_at"):
        assert key in job, f"Missing key: {key}"
    assert job["source"] == "rss_test"
    assert job["title"] == "Backend Python Engineer"
    assert job["company"] == "Acme Corp"
    assert job["url"] == "https://example.com/job/1"
    # job_id should be SHA-256 of the URL
    expected_id = hashlib.sha256("https://example.com/job/1".encode()).hexdigest()
    assert job["job_id"] == expected_id


# ---------------------------------------------------------------------------
# 6.2.2 — RSS parser handles malformed XML without crashing
# ---------------------------------------------------------------------------


def test_rss_malformed_xml():
    """Malformed XML → empty list, no crash."""
    # feedparser.parse with garbage returns a feed with 0 entries
    malformed = SimpleNamespace(entries=[])
    with patch("src.scraper.rss.feedparser.parse", return_value=malformed):
        results = fetch_rss("https://bad.feed/rss", "rss_broken")

    assert results == []


# ---------------------------------------------------------------------------
# 6.2.3 — Manual queue parser reads valid JSON and returns expected format
# ---------------------------------------------------------------------------


def test_manual_valid_json(tmp_dir):
    """Valid JSON → returns expected format with corrected schema."""
    filepath = os.path.join(tmp_dir, "queue.json")
    payload = [
        {
            "company": "CloudAI Inc",
            "domain": "cloudai.io",
            "jd_summary": "Looking for ML engineer to build NLP pipelines.",
            "url": "https://cloudai.io/careers/ml",
        },
        {
            "company": "DataWorks",
            "domain": "dataworks.dev",
            "jd_summary": "Backend Python role focused on data engineering.",
            # no url — should use company+domain for job_id
            # no title — should use company as fallback
        },
    ]
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f)

    results = load_manual_queue(filepath)

    assert len(results) == 2

    # First entry — has URL
    j0 = results[0]
    assert j0["company"] == "CloudAI Inc"
    assert j0["domain"] == "cloudai.io"
    assert j0["url"] == "https://cloudai.io/careers/ml"
    assert j0["source"] == "manual"
    assert j0["job_id"] == hashlib.sha256("https://cloudai.io/careers/ml".encode()).hexdigest()
    assert j0["title"] == "CloudAI Inc"  # no explicit title → company fallback

    # Second entry — no URL, no title
    j1 = results[1]
    assert j1["company"] == "DataWorks"
    assert j1["domain"] == "dataworks.dev"
    assert j1["url"] == ""
    assert j1["source"] == "manual"
    assert j1["title"] == "DataWorks"  # fallback
    assert j1["job_id"] == hashlib.sha256("DataWorksdataworks.dev".encode()).hexdigest()


# ---------------------------------------------------------------------------
# 6.2.4 — Manual queue parser handles empty file
# ---------------------------------------------------------------------------


def test_manual_empty_file(tmp_dir):
    """Empty file → empty list."""
    filepath = os.path.join(tmp_dir, "empty.json")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("")

    results = load_manual_queue(filepath)
    assert results == []


# ---------------------------------------------------------------------------
# 6.2.5 — Manual queue parser handles missing file
# ---------------------------------------------------------------------------


def test_manual_missing_file(caplog):
    """Missing file → empty list, logs warning."""
    with caplog.at_level(logging.WARNING):
        results = load_manual_queue("/nonexistent/path/queue.json")

    assert results == []
    assert any("not found" in r.message.lower() for r in caplog.records)
