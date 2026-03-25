"""
Tests for src/sender/smtp.py
Conforms to contracts.md Section 6.5.

1. Weekend check → True for Saturday/Sunday (mock datetime)
2. Weekend check → False for weekday
3. Warmup counter → correct limit per week number
4. Unsubscribe line present in every outgoing body (mock SMTP)
5. Queue processing respects daily limit (mock SMTP)
"""

import os
import sqlite3
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.db.schema import init_db, insert_queue
from src.sender.smtp import (
    _UNSUBSCRIBE_LINE,
    get_warmup_limit,
    process_queue,
    send_email,
    should_skip_today,
)


# ---------------------------------------------------------------------------
# Test 1 & 2: Weekend check
# ---------------------------------------------------------------------------

class TestWeekendSkip:
    """should_skip_today returns True on Sat/Sun, False on weekdays."""

    def test_saturday_returns_true(self):
        # Saturday = weekday 5
        fake_sat = datetime(2026, 3, 28, 12, 0, 0, tzinfo=timezone.utc)
        with patch("src.sender.smtp.datetime") as mock_dt:
            mock_dt.now.return_value = fake_sat
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert should_skip_today() is True

    def test_sunday_returns_true(self):
        # Sunday = weekday 6
        fake_sun = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)
        with patch("src.sender.smtp.datetime") as mock_dt:
            mock_dt.now.return_value = fake_sun
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert should_skip_today() is True

    def test_weekday_returns_false(self):
        # Wednesday = weekday 2
        fake_wed = datetime(2026, 3, 25, 12, 0, 0, tzinfo=timezone.utc)
        with patch("src.sender.smtp.datetime") as mock_dt:
            mock_dt.now.return_value = fake_wed
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert should_skip_today() is False


# ---------------------------------------------------------------------------
# Test 3: Warmup limit per week
# ---------------------------------------------------------------------------

class TestWarmupLimit:
    """get_warmup_limit returns correct daily cap per week number."""

    @pytest.mark.parametrize(
        "days_elapsed, expected_limit",
        [
            (0, 1),    # day 0 → week 1
            (6, 1),    # day 6 → week 1
            (7, 1),    # day 7 → week 2
            (13, 1),   # day 13 → week 2
            (14, 2),   # day 14 → week 3
            (27, 2),   # day 27 → week 4
            (28, 3),   # day 28 → week 5
            (41, 3),   # day 41 → week 6
            (42, 5),   # day 42 → week 7
            (100, 5),  # day 100 → week 15
        ],
    )
    def test_warmup_schedule(self, days_elapsed, expected_limit):
        # Fix "today" so we can compute first_send_date
        fake_today = date(2026, 6, 1)
        first_send = date.fromordinal(fake_today.toordinal() - days_elapsed)

        with patch("src.sender.smtp.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(
                2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc
            )
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            assert get_warmup_limit(first_send) == expected_limit


# ---------------------------------------------------------------------------
# Test 4: Unsubscribe line in every outgoing body
# ---------------------------------------------------------------------------

class TestUnsubscribeLine:
    """send_email appends the unsubscribe line to the body."""

    @patch("src.sender.smtp.smtplib.SMTP")
    def test_unsubscribe_present(self, mock_smtp_cls):
        """The body received by sendmail must contain the unsubscribe line."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = send_email(
            to_addr="test@example.com",
            subject="Hello",
            body="Short body.",
            from_addr="outreach@gmail.com",
            app_password="fake-password",
        )

        assert result is True
        # Extract the raw message passed to sendmail
        call_args = mock_server.sendmail.call_args
        raw_msg = call_args[0][2]  # third positional arg
        assert 'Reply "stop"' in raw_msg
        assert "never hear from me again" in raw_msg


# ---------------------------------------------------------------------------
# Test 5: Queue processing respects daily limit
# ---------------------------------------------------------------------------

class TestQueueLimit:
    """process_queue sends at most daily_limit emails even if queue has more."""

    @patch("src.sender.smtp.send_email", return_value=True)
    def test_limit_respected(self, mock_send):
        # In-memory DB with 5 queued emails
        conn = init_db(":memory:")

        for i in range(5):
            insert_queue(conn, {
                "company": f"Co{i}",
                "domain": f"co{i}.com",
                "person_name": f"Person {i}",
                "person_title": "CTO",
                "email": f"cto@co{i}.com",
                "email_source": "team_page",
                "email_confidence": "direct_find",
                "subject": f"Subject {i}",
                "subject_variant": 1,
                "email_body": f"Body for person {i}.",
                "job_id": f"job_{i}",
                "relevance_score": 0.9 - i * 0.1,
            })

        # Set env vars for process_queue
        with patch.dict(os.environ, {
            "OUTREACH_EMAIL": "outreach@gmail.com",
            "OUTREACH_APP_PASSWORD": "fake",
        }):
            stats = process_queue(conn, daily_limit=2)

        assert stats["sent"] == 2
        assert mock_send.call_count == 2

        # Verify only 2 marked as sent in DB
        sent_rows = conn.execute(
            "SELECT COUNT(*) FROM email_queue WHERE status = 'sent'"
        ).fetchone()[0]
        assert sent_rows == 2

        # Verify 2 rows inserted into companies_contacted
        contact_rows = conn.execute(
            "SELECT COUNT(*) FROM companies_contacted"
        ).fetchone()[0]
        assert contact_rows == 2

        # Verify remaining 3 are still pending
        pending = conn.execute(
            "SELECT COUNT(*) FROM email_queue WHERE status = 'pending'"
        ).fetchone()[0]
        assert pending == 3

        conn.close()
