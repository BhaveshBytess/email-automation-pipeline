"""Tests for Module 6 — Reply Tracker (contracts.md Section 6.6)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.db.schema import get_follow_ups_due, init_db, insert_contact, mark_bounced, mark_opted_out
from src.tracker.classifier import classify_reply
from src.tracker.imap import is_bounce, is_opt_out


@pytest.fixture()
def conn(tmp_path):
    db_path = str(tmp_path / "tracker_state.db")
    c = init_db(db_path)
    yield c
    c.close()


def _make_contact(**overrides) -> dict:
    base = {
        "company": "Acme Corp",
        "domain": "acme.com",
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


def test_bounce_detects_mailer_daemon():
    assert is_bounce("mailer-daemon@googlemail.com", "Delivery Status Notification") is True


def test_bounce_detects_delivery_failure_subject():
    assert is_bounce("noreply@example.com", "delivery failure: recipient unknown") is True


def test_opt_out_detects_stop():
    assert is_opt_out("Please stop emailing me.") is True


def test_opt_out_detects_unsubscribe():
    assert is_opt_out("unsubscribe me from this list") is True


def test_opt_out_detects_remove():
    assert is_opt_out("remove me from future outreach") is True


def test_reply_classifier_non_bounce_non_optout():
    label = classify_reply("Thanks for reaching out. Happy to connect next week.")
    assert label in {"positive", "neutral", "negative"}


def test_follow_up_query_excludes_bounced(conn):
    insert_contact(conn, _make_contact())
    conn.execute(
        "UPDATE companies_contacted SET follow_up_date = ? WHERE email = ?",
        (datetime.now(timezone.utc).date().isoformat(), "jane@acme.com"),
    )
    conn.commit()

    mark_bounced(conn, "jane@acme.com")
    due = get_follow_ups_due(conn)

    assert all(row["email"] != "jane@acme.com" for row in due)


def test_follow_up_query_excludes_opted_out(conn):
    insert_contact(conn, _make_contact(email="alex@acme.com", person_name="Alex Roe"))
    conn.execute(
        "UPDATE companies_contacted SET follow_up_date = ? WHERE email = ?",
        (datetime.now(timezone.utc).date().isoformat(), "alex@acme.com"),
    )
    conn.commit()

    mark_opted_out(conn, "alex@acme.com")
    due = get_follow_ups_due(conn)

    assert all(row["email"] != "alex@acme.com" for row in due)
