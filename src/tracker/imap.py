"""IMAP reply tracker for Module 6.

Processes inbox messages for replies, bounces, and opt-outs and updates
companies_contacted state through schema helpers.
"""

from __future__ import annotations

import email
import logging
import re
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import parseaddr
from typing import Optional

from src.db.schema import mark_bounced, mark_opted_out, mark_reply
from src.tracker.classifier import classify_reply

logger = logging.getLogger(__name__)

_BOUNCE_KEYWORDS = [
    "mailer-daemon",
    "postmaster",
    "delivery failure",
    "undeliverable",
    "failed delivery",
    "returned mail",
]

_OPT_OUT_KEYWORDS = [
    "stop",
    "unsubscribe",
    "remove",
    "opt out",
    "not interested",
    "take me off",
]


def is_bounce(sender: str, subject: str) -> bool:
    """Detect bounce notifications from sender and subject."""
    joined = f"{sender or ''} {subject or ''}".lower()
    return any(keyword in joined for keyword in _BOUNCE_KEYWORDS)


def is_opt_out(body_text: str) -> bool:
    """Detect explicit opt-out language in message body."""
    text = (body_text or "").lower()
    return any(keyword in text for keyword in _OPT_OUT_KEYWORDS)


def extract_bounced_address(msg_body: str) -> Optional[str]:
    """Extract failed recipient address from bounce body text."""
    if not msg_body:
        return None

    patterns = [
        r"(?:final-recipient:\s*rfc822;\s*)([a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+)",
        r"(?:original-recipient:\s*rfc822;\s*)([a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+)",
        r"(?:to:\s*)([a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+)",
        r"([a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, msg_body, flags=re.IGNORECASE)
        if match:
            return match.group(1).lower()
    return None


def _extract_text_body(msg: Message) -> str:
    """Extract plain text body from email message."""
    if msg.is_multipart():
        parts: list[str] = []
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type != "text/plain":
                continue
            if part.get("Content-Disposition", "").lower().startswith("attachment"):
                continue
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            try:
                parts.append(payload.decode(charset, errors="replace"))
            except LookupError:
                parts.append(payload.decode("utf-8", errors="replace"))
        return "\n".join(parts).strip()

    payload = msg.get_payload(decode=True)
    if payload is None:
        raw = msg.get_payload()
        return raw if isinstance(raw, str) else ""

    charset = msg.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace").strip()
    except LookupError:
        return payload.decode("utf-8", errors="replace").strip()


def _extract_sender_email(from_header: str) -> str:
    """Parse sender address from RFC822 From header."""
    _, addr = parseaddr(from_header or "")
    return addr.lower().strip()


def _extract_sender_domain(from_header: str) -> str:
    sender_email = _extract_sender_email(from_header)
    if "@" not in sender_email:
        return ""
    return sender_email.split("@", 1)[1]


def _match_reply_contact(db_conn, sender_domain: str, subject: str) -> Optional[dict]:
    """Match inbound Re: subject + sender domain to a sent contact row."""
    if not subject:
        return None

    match = re.match(r"^\s*re:\s*(.+)$", subject, flags=re.IGNORECASE)
    if not match:
        return None

    base_subject = match.group(1).strip()
    row = db_conn.execute(
        """
        SELECT email, domain, subject
        FROM companies_contacted
        WHERE lower(subject) = lower(?)
          AND lower(domain) = lower(?)
        ORDER BY id DESC
        LIMIT 1
        """,
        (base_subject, sender_domain),
    ).fetchone()

    return dict(row) if row else None


def _bounce_rate_last_7_days(db_conn) -> float:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    sent_count = db_conn.execute(
        "SELECT COUNT(*) FROM companies_contacted WHERE sent_at >= ?",
        (cutoff,),
    ).fetchone()[0]

    if sent_count == 0:
        return 0.0

    bounced_count = db_conn.execute(
        "SELECT COUNT(*) FROM companies_contacted WHERE bounced = 1 AND bounced_at >= ?",
        (cutoff,),
    ).fetchone()[0]

    return float(bounced_count) / float(sent_count)


def check_inbox(imap_conn, db_conn) -> dict:
    """Poll inbox and update reply/bounce/opt-out states.

    Returns stats dict containing:
    {replies, bounces, opt_outs, bounce_rate_exceeded}
    """
    stats = {
        "replies": 0,
        "bounces": 0,
        "opt_outs": 0,
        "bounce_rate_exceeded": False,
    }

    status, _ = imap_conn.select("INBOX")
    if status != "OK":
        logger.warning("Unable to select inbox")
        return stats

    status, data = imap_conn.search(None, "ALL")
    if status != "OK" or not data:
        bounce_rate = _bounce_rate_last_7_days(db_conn)
        stats["bounce_rate_exceeded"] = bounce_rate > 0.05
        if stats["bounce_rate_exceeded"]:
            logger.critical("Bounce rate exceeded 5%% threshold: %.2f", bounce_rate)
        return stats

    message_ids = data[0].split()

    for msg_id in message_ids:
        fetch_status, msg_data = imap_conn.fetch(msg_id, "(RFC822)")
        if fetch_status != "OK" or not msg_data:
            continue

        raw_bytes = None
        for part in msg_data:
            if isinstance(part, tuple) and len(part) >= 2:
                raw_bytes = part[1]
                break
        if not raw_bytes:
            continue

        msg = email.message_from_bytes(raw_bytes)
        sender = _extract_sender_email(msg.get("From", ""))
        sender_domain = _extract_sender_domain(msg.get("From", ""))
        subject = msg.get("Subject", "") or ""
        body = _extract_text_body(msg)

        if is_bounce(sender, subject):
            bounced_email = extract_bounced_address(body)
            if bounced_email:
                mark_bounced(db_conn, bounced_email)
                stats["bounces"] += 1
            continue

        matched_contact = _match_reply_contact(db_conn, sender_domain, subject)
        if not matched_contact:
            continue

        matched_email = matched_contact["email"]

        if is_opt_out(body):
            mark_opted_out(db_conn, matched_email)
            stats["opt_outs"] += 1
            continue

        reply_type = classify_reply(body)
        mark_reply(db_conn, matched_email, reply_type, body)
        stats["replies"] += 1

    bounce_rate = _bounce_rate_last_7_days(db_conn)
    stats["bounce_rate_exceeded"] = bounce_rate > 0.05
    if stats["bounce_rate_exceeded"]:
        logger.critical("Bounce rate exceeded 5%% threshold: %.2f", bounce_rate)

    return stats
