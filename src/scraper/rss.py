"""
RSS feed scraper and deduplication for the Cold Email Pipeline.

Conforms to contracts.md Section 3.6 (source enums) and Section 6.2 (test spec).
"""

import hashlib
import logging
import re
import sqlite3
from datetime import datetime, timezone
from html import unescape
from typing import Optional

import feedparser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feed configuration
# ---------------------------------------------------------------------------

_FEEDS: list[tuple[str, str]] = [
    ("https://remoteok.com/remote-jobs.rss", "rss_remoteok"),
    ("https://weworkremotely.com/categories/remote-programming-jobs.rss", "rss_wwr"),
    ("https://jobspresso.co/remotework/feed/", "rss_jobspresso"),
]

_KEYWORDS: list[str] = [
    "ml", "ai", "machine learning", "backend", "python",
    "nlp", "deep learning", "data engineering",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(raw: str) -> str:
    """Remove HTML tags and unescape entities."""
    return unescape(_HTML_TAG_RE.sub("", raw)).strip()


def _matches_keyword(text: str) -> bool:
    """Return True if *text* contains at least one target keyword."""
    lower = text.lower()
    return any(kw in lower for kw in _KEYWORDS)


def _job_id_from_url(url: str) -> str:
    """SHA-256 hex digest of *url*."""
    return hashlib.sha256(url.encode()).hexdigest()


def _job_id_from_fields(company: str, domain: str) -> str:
    """SHA-256 hex digest of company + domain concatenation."""
    return hashlib.sha256(f"{company}{domain}".encode()).hexdigest()


def _extract_company(entry: feedparser.FeedParserDict, source_name: str) -> str:
    """Best-effort company name extraction from an RSS entry.

    * RemoteOK: stores company in ``entry.tags[0].term``.
    * WeWorkRemotely: title format "Company: Job Title".
    * Default: fall back to ``"Unknown"``.
    """
    # Try tags first (RemoteOK style)
    try:
        tags = getattr(entry, "tags", None)
        if tags and len(tags) > 0:
            company = tags[0].get("term", "").strip()
            if company:
                return company
    except (AttributeError, IndexError):
        pass

    # Try "Company: Title" pattern (WWR style)
    title = getattr(entry, "title", "") or ""
    if ":" in title:
        candidate = title.split(":")[0].strip()
        if candidate:
            return candidate

    return "Unknown"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_rss(feed_url: str, source_name: str) -> list[dict]:
    """Parse a single RSS feed and return keyword-filtered job dicts.

    Returns ``[]`` on any parse/network error (never crashes).
    Each dict has keys: ``job_id``, ``title``, ``company``, ``url``,
    ``source``, ``jd_summary``, ``discovered_at``.
    """
    try:
        feed = feedparser.parse(feed_url)
    except Exception:
        logger.warning("Failed to parse feed %s", feed_url, exc_info=True)
        return []

    jobs: list[dict] = []
    for entry in feed.entries:
        title = getattr(entry, "title", "") or ""
        summary_raw = getattr(entry, "summary", "") or ""
        summary = _strip_html(summary_raw)
        url = getattr(entry, "link", "") or ""
        company = _extract_company(entry, source_name)

        # Keyword filter
        if not _matches_keyword(f"{title} {summary}"):
            continue

        job_id = _job_id_from_url(url) if url else _job_id_from_fields(company, title)

        jobs.append({
            "job_id": job_id,
            "title": title,
            "company": company,
            "url": url,
            "source": source_name,
            "jd_summary": summary[:2000],  # cap summary length
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        })

    logger.info("Feed %s: %d entries, %d matched keywords", feed_url, len(feed.entries), len(jobs))
    return jobs


def fetch_all_rss() -> list[dict]:
    """Fetch and combine results from all configured feeds."""
    combined: list[dict] = []
    for url, name in _FEEDS:
        combined.extend(fetch_rss(url, name))
    return combined


def merge_and_deduplicate(jobs: list[dict], conn: sqlite3.Connection) -> list[dict]:
    """Return only jobs whose ``job_id`` is NOT already in ``jobs_seen``."""
    new_jobs: list[dict] = []
    for job in jobs:
        row = conn.execute(
            "SELECT 1 FROM jobs_seen WHERE job_id = ? LIMIT 1",
            (job["job_id"],),
        ).fetchone()
        if row is None:
            new_jobs.append(job)
    return new_jobs
