"""
Gmail SMTP sender for the Cold Email Pipeline.
Conforms to contracts.md Section 6.5 and FC-04.

Credentials via env vars: OUTREACH_EMAIL, OUTREACH_APP_PASSWORD.
"""

import logging
import os
import smtplib
import sqlite3
from datetime import date, datetime, timezone
from email.mime.text import MIMEText

from src.db.schema import (
    get_follow_ups_due,
    get_pending_queue,
    mark_follow_up_sent,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_UNSUBSCRIBE_LINE = (
    '\n\nP.S. Not relevant? Reply "stop" and I\'ll make sure '
    "you never hear from me again."
)

_FOLLOW_UP_TEMPLATE = (
    "Hi {person_name},\n\n"
    "I reached out last week about a role at {company}. "
    "I know things get buried — just wanted to bump this "
    "in case it's still relevant.\n\n"
    "Happy to chat whenever works for you.\n\n"
    "Best,\nBhavesh"
)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def should_skip_today() -> bool:
    """Return True on Saturday (5) and Sunday (6)."""
    return datetime.now(timezone.utc).weekday() >= 5


def get_warmup_limit(first_send_date: date) -> int:
    """Return daily sending limit based on weeks since *first_send_date*.

    Schedule (from agent_project.md 2.4):
        Week 1-2: 1 email/day
        Week 3-4: 2 emails/day
        Week 5-6: 3 emails/day
        Week 7+:  5 emails/day
    """
    days_elapsed = (datetime.now(timezone.utc).date() - first_send_date).days
    week = max(days_elapsed // 7 + 1, 1)  # 1-indexed week number

    if week <= 2:
        return 1
    if week <= 4:
        return 2
    if week <= 6:
        return 3
    return 5


# ---------------------------------------------------------------------------
# Core send function
# ---------------------------------------------------------------------------

def send_email(
    to_addr: str,
    subject: str,
    body: str,
    from_addr: str,
    app_password: str,
) -> bool:
    """Send a plain-text email via Gmail SMTP.

    Appends the unsubscribe line to *body* before sending.
    Returns True on success, False on any SMTP/network error.
    """
    full_body = body + _UNSUBSCRIBE_LINE

    msg = MIMEText(full_body, "plain")
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(from_addr, app_password)
            server.sendmail(from_addr, [to_addr], msg.as_string())
        logger.info("Email sent to %s — subject: %s", to_addr, subject)
        return True
    except Exception:
        logger.exception("SMTP send failed for %s", to_addr)
        return False


# ---------------------------------------------------------------------------
# Queue processing
# ---------------------------------------------------------------------------

def process_queue(db_conn: sqlite3.Connection, daily_limit: int) -> dict:
    """Send up to *daily_limit* pending emails from the queue.

    On successful send, atomically:
      1. UPDATE email_queue SET status='sent'
      2. INSERT INTO companies_contacted
    Both wrapped in a single transaction — if either fails, neither commits.

    On SMTP failure (FC-04): email stays as 'pending', logged, retried next run.

    Returns dict: {sent: int, failed: int, skipped: int}
    """
    from_addr = os.environ.get("OUTREACH_EMAIL", "")
    app_password = os.environ.get("OUTREACH_APP_PASSWORD", "")

    stats = {"sent": 0, "failed": 0, "skipped": 0}

    items = get_pending_queue(db_conn, daily_limit)
    if not items:
        logger.info("Queue empty — nothing to send.")
        return stats

    for item in items:
        success = send_email(
            to_addr=item["email"],
            subject=item["subject"],
            body=item["email_body"],
            from_addr=from_addr,
            app_password=app_password,
        )

        if success:
            # Atomic: mark sent + insert contact in one transaction
            sent_at = datetime.now(timezone.utc).isoformat()
            try:
                db_conn.execute("BEGIN")
                db_conn.execute(
                    "UPDATE email_queue SET status = 'sent' WHERE id = ?",
                    (item["id"],),
                )
                # Compute follow_up_date = sent_at + 5 business days
                sent_date = datetime.fromisoformat(sent_at).date()
                from src.db.schema import _business_days_ahead
                follow_up_date = _business_days_ahead(sent_date, 5).isoformat()

                db_conn.execute(
                    """
                    INSERT INTO companies_contacted
                        (company, domain, person_name, person_title, email,
                         email_source, email_confidence, subject, subject_variant,
                         email_body, sent_at, follow_up_date, job_id, relevance_score)
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
                        sent_at,
                        follow_up_date,
                        item.get("job_id"),
                        item.get("relevance_score"),
                    ),
                )
                db_conn.commit()
                stats["sent"] += 1
            except Exception:
                db_conn.rollback()
                logger.exception(
                    "Transaction failed for queue id %s — rolled back", item["id"]
                )
                stats["failed"] += 1
        else:
            # FC-04: stays pending, will retry next run
            stats["failed"] += 1

    return stats


# ---------------------------------------------------------------------------
# Follow-up processing
# ---------------------------------------------------------------------------

def send_follow_ups(db_conn: sqlite3.Connection) -> dict:
    """Send follow-ups for contacts whose follow_up_date <= today.

    Uses a hardcoded template — NO Gemini call.
    Follow-ups are processed BEFORE new emails.

    Returns dict: {sent: int, skipped: int}
    """
    from_addr = os.environ.get("OUTREACH_EMAIL", "")
    app_password = os.environ.get("OUTREACH_APP_PASSWORD", "")

    stats = {"sent": 0, "skipped": 0}

    contacts = get_follow_ups_due(db_conn)
    if not contacts:
        logger.info("No follow-ups due today.")
        return stats

    for contact in contacts:
        body = _FOLLOW_UP_TEMPLATE.format(
            person_name=contact["person_name"],
            company=contact["company"],
        )
        subject = f"Re: {contact['subject']}"

        success = send_email(
            to_addr=contact["email"],
            subject=subject,
            body=body,
            from_addr=from_addr,
            app_password=app_password,
        )

        if success:
            mark_follow_up_sent(db_conn, contact["id"])
            stats["sent"] += 1
        else:
            stats["skipped"] += 1

    return stats


# ---------------------------------------------------------------------------
# Summary email
# ---------------------------------------------------------------------------

def send_summary(
    stats: dict,
    to_primary: str,
    from_addr: str,
    app_password: str,
) -> None:
    """Send daily heartbeat summary to primary Gmail.

    Sent even if zero emails were sent today.
    Never crashes the pipeline — any error is logged and swallowed.
    """
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        lines = [
            f"Cold Email Pipeline — Daily Summary ({today})",
            "=" * 50,
            "",
        ]
        for key, value in stats.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        lines.append("— Automated Pipeline")

        body = "\n".join(lines)

        msg = MIMEText(body, "plain")
        msg["From"] = from_addr
        msg["To"] = to_primary
        msg["Subject"] = f"Pipeline Summary — {today}"

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(from_addr, app_password)
            server.sendmail(from_addr, [to_primary], msg.as_string())

        logger.info("Summary email sent to %s", to_primary)
    except Exception:
        # FC-04 fallback: print to stdout if SMTP is fully dead
        logger.exception("Failed to send summary email — printing to stdout")
        print(f"[SUMMARY {today}] {stats}")
