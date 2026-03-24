"""
SQLite schema and helper functions for the Cold Email Pipeline.
Conforms to contracts.md Section 3 — V1.
"""

import logging
import shutil
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _today_utc() -> str:
    """Return current UTC date as ISO-8601 string (date only)."""
    return datetime.now(timezone.utc).date().isoformat()


def _business_days_ahead(start: date, n: int) -> date:
    """Return the date that is *n* business days after *start*."""
    current = start
    added = 0
    while added < n:
        current += timedelta(days=1)
        if current.weekday() < 5:  # Mon-Fri
            added += 1
    return current


# ---------------------------------------------------------------------------
# Table DDL — exact SQL from contracts.md Section 3
# ---------------------------------------------------------------------------

_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS jobs_seen (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        domain TEXT,
        url TEXT,
        source TEXT NOT NULL,
        jd_summary TEXT,
        relevance_score REAL,
        discovered_at TEXT NOT NULL,
        processed INTEGER DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS companies_contacted (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL,
        domain TEXT NOT NULL,
        person_name TEXT NOT NULL,
        person_title TEXT,
        email TEXT NOT NULL,
        email_source TEXT NOT NULL,
        email_confidence TEXT NOT NULL,
        subject TEXT NOT NULL,
        subject_variant INTEGER NOT NULL,
        email_body TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        reply INTEGER DEFAULT 0,
        reply_type TEXT,
        reply_text TEXT,
        reply_at TEXT,
        bounced INTEGER DEFAULT 0,
        bounced_at TEXT,
        follow_up_date TEXT,
        follow_up_sent INTEGER DEFAULT 0,
        opted_out INTEGER DEFAULT 0,
        job_id TEXT,
        relevance_score REAL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS email_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL,
        domain TEXT NOT NULL,
        person_name TEXT NOT NULL,
        person_title TEXT,
        email TEXT NOT NULL,
        email_source TEXT NOT NULL,
        email_confidence TEXT NOT NULL,
        subject TEXT NOT NULL,
        subject_variant INTEGER NOT NULL,
        email_body TEXT NOT NULL,
        job_id TEXT,
        relevance_score REAL,
        queued_at TEXT NOT NULL,
        status TEXT DEFAULT 'pending'
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS email_not_found (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL,
        domain TEXT NOT NULL,
        job_id TEXT,
        reason TEXT NOT NULL,
        failed_at TEXT NOT NULL,
        retry_after TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS run_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date TEXT NOT NULL,
        jobs_found INTEGER DEFAULT 0,
        jobs_relevant INTEGER DEFAULT 0,
        emails_found INTEGER DEFAULT 0,
        emails_sent INTEGER DEFAULT 0,
        follow_ups_sent INTEGER DEFAULT 0,
        bounces_detected INTEGER DEFAULT 0,
        errors INTEGER DEFAULT 0,
        duration_seconds REAL,
        started_at TEXT NOT NULL,
        finished_at TEXT
    );
    """,
]


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> sqlite3.Connection:
    """Create all tables if they don't exist and return a connection."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    for ddl in _TABLES:
        conn.execute(ddl)
    conn.commit()
    logger.info("Database initialised: %s", db_path)
    return conn


def backup_db(db_path: str) -> None:
    """Create a consistent backup using SQLite's online backup API.

    This handles WAL mode correctly — shutil.copy2 would miss
    unflushed WAL data.
    """
    backup_path = db_path + ".backup"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    src.backup(dst)
    dst.close()
    src.close()
    logger.info("Backup created: %s", backup_path)


# ---------------------------------------------------------------------------
# Dedup checkers
# ---------------------------------------------------------------------------

def is_company_contacted(conn: sqlite3.Connection, domain: str, days: int = 60) -> bool:
    """Return True if *domain* was contacted within the last *days* days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    row = conn.execute(
        "SELECT 1 FROM companies_contacted WHERE domain = ? AND sent_at >= ? LIMIT 1",
        (domain, cutoff),
    ).fetchone()
    return row is not None


def is_email_not_found(conn: sqlite3.Connection, domain: str, days: int = 30) -> bool:
    """Return True if *domain* is in email_not_found with retry_after still in the future."""
    today = _today_utc()
    row = conn.execute(
        "SELECT 1 FROM email_not_found WHERE domain = ? AND retry_after > ? LIMIT 1",
        (domain, today),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Insert functions
# ---------------------------------------------------------------------------

def insert_job(conn: sqlite3.Connection, job: dict) -> None:
    """INSERT OR IGNORE a job into jobs_seen."""
    conn.execute(
        """
        INSERT OR IGNORE INTO jobs_seen
            (job_id, title, company, domain, url, source, jd_summary,
             relevance_score, discovered_at, processed)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job["job_id"],
            job["title"],
            job["company"],
            job.get("domain"),
            job.get("url"),
            job["source"],
            job.get("jd_summary"),
            job.get("relevance_score"),
            job.get("discovered_at", _utcnow()),
            job.get("processed", 0),
        ),
    )
    conn.commit()


def insert_contact(conn: sqlite3.Connection, contact: dict) -> None:
    """Insert a row into companies_contacted.

    Automatically sets follow_up_date to sent_at + 5 business days.
    """
    sent_at_str = contact.get("sent_at", _utcnow())
    sent_at_date = datetime.fromisoformat(sent_at_str).date()
    follow_up_date = _business_days_ahead(sent_at_date, 5).isoformat()

    conn.execute(
        """
        INSERT INTO companies_contacted
            (company, domain, person_name, person_title, email,
             email_source, email_confidence, subject, subject_variant,
             email_body, sent_at, follow_up_date, job_id, relevance_score)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            contact["company"],
            contact["domain"],
            contact["person_name"],
            contact.get("person_title"),
            contact["email"],
            contact["email_source"],
            contact["email_confidence"],
            contact["subject"],
            contact["subject_variant"],
            contact["email_body"],
            sent_at_str,
            follow_up_date,
            contact.get("job_id"),
            contact.get("relevance_score"),
        ),
    )
    conn.commit()


def insert_queue(conn: sqlite3.Connection, item: dict) -> None:
    """Insert an email into the email_queue."""
    conn.execute(
        """
        INSERT INTO email_queue
            (company, domain, person_name, person_title, email,
             email_source, email_confidence, subject, subject_variant,
             email_body, job_id, relevance_score, queued_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            item["company"],
            item["domain"],
            item["person_name"],
            item.get("person_title"),
            item["email"],
            item["email_source"],
            item["email_confidence"],
            item["subject"],
            item["subject_variant"],
            item["email_body"],
            item.get("job_id"),
            item.get("relevance_score"),
            item.get("queued_at", _utcnow()),
            item.get("status", "pending"),
        ),
    )
    conn.commit()


def insert_not_found(conn: sqlite3.Connection, nf: dict) -> None:
    """Insert into email_not_found. Sets retry_after = failed_at + 30 days."""
    failed_at_str = nf.get("failed_at", _utcnow())
    failed_at_date = datetime.fromisoformat(failed_at_str).date()
    retry_after = (failed_at_date + timedelta(days=30)).isoformat()

    conn.execute(
        """
        INSERT INTO email_not_found
            (company, domain, job_id, reason, failed_at, retry_after)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            nf["company"],
            nf["domain"],
            nf.get("job_id"),
            nf["reason"],
            failed_at_str,
            retry_after,
        ),
    )
    conn.commit()


def insert_run_log(conn: sqlite3.Connection, stats: dict) -> None:
    """Insert a run_log entry."""
    conn.execute(
        """
        INSERT INTO run_log
            (run_date, jobs_found, jobs_relevant, emails_found, emails_sent,
             follow_ups_sent, bounces_detected, errors, duration_seconds,
             started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            stats["run_date"],
            stats.get("jobs_found", 0),
            stats.get("jobs_relevant", 0),
            stats.get("emails_found", 0),
            stats.get("emails_sent", 0),
            stats.get("follow_ups_sent", 0),
            stats.get("bounces_detected", 0),
            stats.get("errors", 0),
            stats.get("duration_seconds"),
            stats["started_at"],
            stats.get("finished_at"),
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Queue operations
# ---------------------------------------------------------------------------

def get_pending_queue(conn: sqlite3.Connection, limit: int) -> list[dict]:
    """Return up to *limit* pending queue items, ordered by relevance_score DESC."""
    rows = conn.execute(
        """
        SELECT * FROM email_queue
        WHERE status = 'pending'
        ORDER BY relevance_score DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_queue_sent(conn: sqlite3.Connection, queue_id: int) -> None:
    """Mark a queue item as sent."""
    conn.execute(
        "UPDATE email_queue SET status = 'sent' WHERE id = ?",
        (queue_id,),
    )
    conn.commit()


def mark_queue_failed(conn: sqlite3.Connection, queue_id: int) -> None:
    """Mark a queue item as failed."""
    conn.execute(
        "UPDATE email_queue SET status = 'failed' WHERE id = ?",
        (queue_id,),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Tracking operations
# ---------------------------------------------------------------------------

def get_follow_ups_due(conn: sqlite3.Connection) -> list[dict]:
    """Return contacts eligible for follow-up today."""
    today = _today_utc()
    rows = conn.execute(
        """
        SELECT * FROM companies_contacted
        WHERE reply = 0
          AND bounced = 0
          AND opted_out = 0
          AND follow_up_sent = 0
          AND follow_up_date <= ?
        """,
        (today,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_follow_up_sent(conn: sqlite3.Connection, contact_id: int) -> None:
    """Mark follow-up as sent for a contact."""
    conn.execute(
        "UPDATE companies_contacted SET follow_up_sent = 1 WHERE id = ?",
        (contact_id,),
    )
    conn.commit()


def mark_bounced(conn: sqlite3.Connection, email: str) -> None:
    """Mark an email address as bounced."""
    now = _utcnow()
    conn.execute(
        "UPDATE companies_contacted SET bounced = 1, bounced_at = ? WHERE email = ?",
        (now, email),
    )
    conn.commit()


def mark_opted_out(conn: sqlite3.Connection, email: str) -> None:
    """Mark an email address as opted out."""
    conn.execute(
        "UPDATE companies_contacted SET opted_out = 1 WHERE email = ?",
        (email,),
    )
    conn.commit()


def mark_reply(conn: sqlite3.Connection, email: str, reply_type: str, reply_text: str) -> None:
    """Record a reply for the given email address."""
    now = _utcnow()
    conn.execute(
        """
        UPDATE companies_contacted
        SET reply = 1, reply_type = ?, reply_text = ?, reply_at = ?
        WHERE email = ?
        """,
        (reply_type, reply_text, now, email),
    )
    conn.commit()
