"""
Tests for src/db/schema.py — per contracts.md Section 6.1.
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from src.db.schema import (
    backup_db,
    init_db,
    insert_contact,
    insert_job,
    insert_not_found,
    is_company_contacted,
    is_email_not_found,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_path(tmp_path):
    """Return a temporary db file path and clean up after."""
    path = str(tmp_path / "test_state.db")
    yield path


@pytest.fixture()
def conn(db_path):
    """Return an initialised connection to a fresh temp database."""
    c = init_db(db_path)
    yield c
    c.close()


def _make_job(job_id: str = "abc123", **overrides) -> dict:
    """Return a minimal valid job dict."""
    base = {
        "job_id": job_id,
        "title": "Backend Engineer",
        "company": "Acme Corp",
        "domain": "acme.com",
        "url": "https://acme.com/jobs/1",
        "source": "rss_remoteok",
        "jd_summary": "Build APIs",
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }
    base.update(overrides)
    return base


def _make_contact(domain: str = "acme.com", **overrides) -> dict:
    """Return a minimal valid contact dict."""
    base = {
        "company": "Acme Corp",
        "domain": domain,
        "person_name": "Jane Doe",
        "person_title": "CTO",
        "email": "jane@acme.com",
        "email_source": "team_page",
        "email_confidence": "direct_find",
        "subject": "Quick question about your backend stack",
        "subject_variant": 1,
        "email_body": "Hi Jane, ...",
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "job_id": "abc123",
        "relevance_score": 0.85,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests — contracts.md Section 6.1
# ---------------------------------------------------------------------------

class TestInsertAndRetrieveJob:
    """Insert a job into jobs_seen, retrieve it by job_id."""

    def test_insert_and_retrieve(self, conn):
        job = _make_job()
        insert_job(conn, job)

        row = conn.execute(
            "SELECT * FROM jobs_seen WHERE job_id = ?", (job["job_id"],)
        ).fetchone()

        assert row is not None
        assert row["job_id"] == "abc123"
        assert row["title"] == "Backend Engineer"
        assert row["company"] == "Acme Corp"
        assert row["source"] == "rss_remoteok"


class TestDuplicateJobSilentIgnore:
    """Insert duplicate job_id — verify silent ignore, no crash."""

    def test_duplicate_is_ignored(self, conn):
        job = _make_job()
        insert_job(conn, job)
        insert_job(conn, job)  # duplicate — must not crash

        count = conn.execute(
            "SELECT COUNT(*) FROM jobs_seen WHERE job_id = ?", (job["job_id"],)
        ).fetchone()[0]

        assert count == 1


class TestSixtyDayDedup:
    """Insert into companies_contacted — verify 60-day dedup blocks re-insert."""

    def test_recent_contact_blocked(self, conn):
        contact = _make_contact()
        insert_contact(conn, contact)

        assert is_company_contacted(conn, "acme.com", days=60) is True

    def test_old_contact_allowed(self, conn):
        old_date = (datetime.now(timezone.utc) - timedelta(days=61)).isoformat()
        contact = _make_contact(sent_at=old_date)
        insert_contact(conn, contact)

        assert is_company_contacted(conn, "acme.com", days=60) is False


class TestThirtyDayRetryWindow:
    """Insert into email_not_found — verify 30-day retry window."""

    def test_recent_not_found_blocked(self, conn):
        nf = {
            "company": "Acme Corp",
            "domain": "acme.com",
            "job_id": "abc123",
            "reason": "no_team_page",
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        insert_not_found(conn, nf)

        # retry_after is failed_at + 30 days, which is in the future
        assert is_email_not_found(conn, "acme.com", days=30) is True

    def test_expired_not_found_allowed(self, conn):
        old_date = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        nf = {
            "company": "Acme Corp",
            "domain": "acme.com",
            "job_id": "abc123",
            "reason": "no_team_page",
            "failed_at": old_date,
        }
        insert_not_found(conn, nf)

        # retry_after = old_date + 30 days = yesterday → should be allowed
        assert is_email_not_found(conn, "acme.com", days=30) is False


class TestBackupCreatesValidSQLite:
    """Create backup — verify backup file exists and is valid SQLite."""

    def test_backup(self, conn, db_path):
        # Insert a row so backup has data
        insert_job(conn, _make_job())

        backup_db(db_path)
        backup_path = db_path + ".backup"

        assert os.path.exists(backup_path)

        # Verify it's valid SQLite by opening and querying
        backup_conn = sqlite3.connect(backup_path)
        backup_conn.row_factory = sqlite3.Row
        row = backup_conn.execute(
            "SELECT * FROM jobs_seen WHERE job_id = ?", ("abc123",)
        ).fetchone()
        assert row is not None
        assert row["job_id"] == "abc123"
        backup_conn.close()


class TestIdempotentTableCreation:
    """Run all table creations twice — verify idempotent (no crash on second run)."""

    def test_double_init(self, db_path):
        conn1 = init_db(db_path)
        insert_job(conn1, _make_job())
        conn1.close()

        # Second init on same db — must not crash, must preserve data
        conn2 = init_db(db_path)
        row = conn2.execute(
            "SELECT * FROM jobs_seen WHERE job_id = ?", ("abc123",)
        ).fetchone()
        assert row is not None
        assert row["title"] == "Backend Engineer"
        conn2.close()
