"""Main pipeline entry point for the Cold Email Pipeline.

Implements contracts.md Section 4 data flow with graceful degradation:
log errors and continue whenever possible.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.db.schema import (
    backup_db,
    init_db,
    insert_job,
    insert_not_found,
    insert_queue,
    insert_run_log,
)
from src.finder.waterfall import find_contact
from src.ranker.minilm import DEFAULT_RESUME_TEXT, get_resume_embedding, load_model, rank_jobs, select_top_n
from src.scraper.manual import load_manual_queue
from src.scraper.rss import fetch_all_rss, merge_and_deduplicate
from src.sender.smtp import get_warmup_limit, process_queue, send_follow_ups, send_summary, should_skip_today
from src.tracker.imap import check_inbox
from src.writer.gemini import generate_email

import imaplib

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = Path("db/state.db")
MANUAL_QUEUE_PATH = Path("data/manual_queue.json")


def _domain_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _safe_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid int env %s=%r, using default=%d", name, raw, default)
        return default


def _check_actions_budget() -> dict[str, Any]:
    """Return budget signals from env vars when available.

    Env vars (optional):
      GHA_MINUTES_USED
      GHA_MINUTES_BUDGET (defaults to 2000)
    """
    used = _safe_int_env("GHA_MINUTES_USED", 0)
    budget = max(_safe_int_env("GHA_MINUTES_BUDGET", 2000), 1)
    ratio = float(used) / float(budget)

    warn_80 = ratio >= 0.80
    skip_scraping_90 = ratio >= 0.90

    if warn_80:
        logger.warning("GitHub Actions budget >=80%% (%d/%d)", used, budget)
    if skip_scraping_90:
        logger.warning("GitHub Actions budget >=90%% (%d/%d) — skipping scraping", used, budget)

    return {
        "budget_used_minutes": used,
        "budget_total_minutes": budget,
        "budget_ratio": ratio,
        "budget_warn_80": warn_80,
        "budget_skip_scraping_90": skip_scraping_90,
    }


def _open_imap_connection() -> imaplib.IMAP4_SSL | None:
    outreach_email = os.environ.get("OUTREACH_EMAIL", "").strip()
    app_password = os.environ.get("OUTREACH_APP_PASSWORD", "").strip()

    if not outreach_email or not app_password:
        logger.warning("IMAP credentials missing; skipping inbox check")
        return None

    try:
        conn = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        conn.login(outreach_email, app_password)
        return conn
    except Exception:
        logger.exception("Failed to open IMAP connection; skipping inbox check")
        return None


def _ensure_db_ready() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = init_db(str(DB_PATH))
    conn.close()


def _warmup_first_send_date(db_conn) -> date:
    row = db_conn.execute("SELECT MIN(sent_at) AS first_sent_at FROM companies_contacted").fetchone()
    first_sent_at = row["first_sent_at"] if row and row["first_sent_at"] else None

    if first_sent_at:
        try:
            return datetime.fromisoformat(first_sent_at).date()
        except ValueError:
            logger.warning("Invalid sent_at in DB: %r", first_sent_at)

    env_first_send = os.environ.get("FIRST_SEND_DATE", "").strip()
    if env_first_send:
        try:
            return date.fromisoformat(env_first_send)
        except ValueError:
            logger.warning("Invalid FIRST_SEND_DATE=%r, using today", env_first_send)

    return datetime.now(timezone.utc).date()


def main() -> int:
    started = datetime.now(timezone.utc)

    run_stats: dict[str, Any] = {
        "jobs_found": 0,
        "jobs_relevant": 0,
        "emails_found": 0,
        "emails_sent": 0,
        "follow_ups_sent": 0,
        "bounces_detected": 0,
        "replies": 0,
        "opt_outs": 0,
        "errors": 0,
        "bounce_rate_exceeded": False,
        "budget_warn_80": False,
        "budget_skip_scraping_90": False,
    }

    db_conn = None
    try:
        _ensure_db_ready()

        # Step 1: backup_db()
        try:
            backup_db(str(DB_PATH))
        except Exception:
            logger.exception("backup_db failed")
            run_stats["errors"] += 1

        # Open DB connection for the rest of the run.
        db_conn = init_db(str(DB_PATH))

        # Step 2: should_skip_today() -> exit 0 if weekend
        if should_skip_today():
            logger.info("Weekend detected; skipping pipeline run")
            return 0

        budget_info = _check_actions_budget()
        run_stats["budget_warn_80"] = budget_info["budget_warn_80"]
        run_stats["budget_skip_scraping_90"] = budget_info["budget_skip_scraping_90"]

        # Step 3: fetch_all_rss() + load_manual_queue()
        rss_jobs: list[dict[str, Any]] = []
        if not budget_info["budget_skip_scraping_90"]:
            try:
                rss_jobs = fetch_all_rss()
            except Exception:
                logger.exception("fetch_all_rss failed")
                run_stats["errors"] += 1
        else:
            logger.info("Skipping RSS scrape due to budget guard (FC-06)")

        manual_jobs: list[dict[str, Any]] = []
        try:
            manual_jobs = load_manual_queue(str(MANUAL_QUEUE_PATH))
        except Exception:
            logger.exception("load_manual_queue failed")
            run_stats["errors"] += 1

        all_jobs = rss_jobs + manual_jobs
        run_stats["jobs_found"] = len(all_jobs)

        # Step 4: merge_and_deduplicate()
        new_jobs: list[dict[str, Any]] = []
        try:
            new_jobs = merge_and_deduplicate(all_jobs, db_conn)
        except Exception:
            logger.exception("merge_and_deduplicate failed")
            run_stats["errors"] += 1

        for job in new_jobs:
            try:
                insert_job(db_conn, job)
            except Exception:
                logger.exception("insert_job failed for job_id=%s", job.get("job_id"))
                run_stats["errors"] += 1

        # Step 5: rank_jobs() -> select_top_n(n=25)
        selected_jobs: list[dict[str, Any]] = []
        if new_jobs:
            try:
                model = load_model()
                resume_embedding = get_resume_embedding(DEFAULT_RESUME_TEXT, model)
                ranked = rank_jobs(new_jobs, resume_embedding, model)
                selected_jobs = select_top_n(ranked, n=25)
                run_stats["jobs_relevant"] = len(selected_jobs)

                # Persist ranker score back into jobs_seen.relevance_score
                for job in ranked:
                    db_conn.execute(
                        "UPDATE jobs_seen SET relevance_score = ? WHERE job_id = ?",
                        (job.get("relevance_score"), job.get("job_id")),
                    )
                db_conn.commit()
            except Exception:
                logger.exception("ranking/select_top_n failed")
                run_stats["errors"] += 1

        # Steps 6 and 7: find_contact() -> generate_email() -> insert_queue()
        for job in selected_jobs:
            company = job.get("company", "").strip()
            domain = (job.get("domain") or _domain_from_url(job.get("url", "")) or "").strip().lower()

            if not company or not domain:
                try:
                    insert_not_found(
                        db_conn,
                        {
                            "company": company or "unknown",
                            "domain": domain or "unknown",
                            "job_id": job.get("job_id"),
                            "reason": "no_role_match",
                        },
                    )
                except Exception:
                    logger.exception("insert_not_found failed for missing company/domain")
                    run_stats["errors"] += 1
                continue

            try:
                contact = find_contact(company, domain, db_conn)
            except Exception:
                logger.exception("find_contact failed for %s", domain)
                run_stats["errors"] += 1
                contact = None

            if not contact:
                try:
                    insert_not_found(
                        db_conn,
                        {
                            "company": company,
                            "domain": domain,
                            "job_id": job.get("job_id"),
                            "reason": "no_role_match",
                        },
                    )
                except Exception:
                    logger.exception("insert_not_found failed for %s", domain)
                    run_stats["errors"] += 1
                continue

            try:
                email_payload = generate_email(
                    person_name=contact["name"],
                    person_title=contact.get("title", ""),
                    company=company,
                    jd_summary=job.get("jd_summary", ""),
                )
                subjects = email_payload.get("subject_options", [])
                subject = subjects[0] if subjects else f"Quick question about {company}"
                subject_variant = 1

                insert_queue(
                    db_conn,
                    {
                        "company": company,
                        "domain": domain,
                        "person_name": contact["name"],
                        "person_title": contact.get("title", ""),
                        "email": contact["email"],
                        "email_source": contact["source"],
                        "email_confidence": contact["confidence"],
                        "subject": subject,
                        "subject_variant": subject_variant,
                        "email_body": email_payload["body"],
                        "job_id": job.get("job_id"),
                        "relevance_score": job.get("relevance_score"),
                    },
                )
                run_stats["emails_found"] += 1
            except Exception:
                logger.exception("generate_email/insert_queue failed for company=%s", company)
                run_stats["errors"] += 1

        # Step 8: check_inbox() -> process replies/bounces
        tracker_stats: dict[str, Any] = {
            "replies": 0,
            "bounces": 0,
            "opt_outs": 0,
            "bounce_rate_exceeded": False,
        }
        imap_conn = _open_imap_connection()
        if imap_conn is not None:
            try:
                tracker_stats = check_inbox(imap_conn, db_conn)
            except Exception:
                logger.exception("check_inbox failed")
                run_stats["errors"] += 1
            finally:
                try:
                    imap_conn.logout()
                except Exception:
                    logger.warning("IMAP logout failed", exc_info=True)

        run_stats["replies"] = tracker_stats.get("replies", 0)
        run_stats["bounces_detected"] = tracker_stats.get("bounces", 0)
        run_stats["opt_outs"] = tracker_stats.get("opt_outs", 0)
        run_stats["bounce_rate_exceeded"] = tracker_stats.get("bounce_rate_exceeded", False)

        # FC-07: pause all sending when bounce rate exceeds 5%.
        if run_stats["bounce_rate_exceeded"]:
            logger.critical("Bounce rate exceeded threshold; pausing follow-ups and queue sending")
        else:
            # Step 9: send_follow_ups()
            try:
                follow_stats = send_follow_ups(db_conn)
                run_stats["follow_ups_sent"] = int(follow_stats.get("sent", 0))
            except Exception:
                logger.exception("send_follow_ups failed")
                run_stats["errors"] += 1

            # Step 10: process_queue(daily_limit)
            try:
                first_send_date = _warmup_first_send_date(db_conn)
                daily_limit = get_warmup_limit(first_send_date)
                queue_stats = process_queue(db_conn, daily_limit=daily_limit)
                run_stats["emails_sent"] = int(queue_stats.get("sent", 0))
            except Exception:
                logger.exception("process_queue failed")
                run_stats["errors"] += 1

    finally:
        finished = datetime.now(timezone.utc)
        duration_seconds = (finished - started).total_seconds()

        if db_conn is not None:
            try:
                # Always write run_log, even if prior steps had errors.
                insert_run_log(
                    db_conn,
                    {
                        "run_date": started.date().isoformat(),
                        "jobs_found": run_stats["jobs_found"],
                        "jobs_relevant": run_stats["jobs_relevant"],
                        "emails_found": run_stats["emails_found"],
                        "emails_sent": run_stats["emails_sent"],
                        "follow_ups_sent": run_stats["follow_ups_sent"],
                        "bounces_detected": run_stats["bounces_detected"],
                        "errors": run_stats["errors"],
                        "duration_seconds": duration_seconds,
                        "started_at": started.isoformat(),
                        "finished_at": finished.isoformat(),
                    },
                )
            except Exception:
                logger.exception("insert_run_log failed")

            try:
                db_conn.close()
            except Exception:
                logger.warning("db_conn.close failed", exc_info=True)

        # Step 11: send_summary(stats)
        outreach_email = os.environ.get("OUTREACH_EMAIL", "")
        outreach_password = os.environ.get("OUTREACH_APP_PASSWORD", "")
        primary_email = os.environ.get("PRIMARY_EMAIL", outreach_email)

        summary_stats = {
            "jobs_found": run_stats["jobs_found"],
            "jobs_relevant": run_stats["jobs_relevant"],
            "emails_found": run_stats["emails_found"],
            "emails_sent": run_stats["emails_sent"],
            "follow_ups_sent": run_stats["follow_ups_sent"],
            "replies": run_stats["replies"],
            "bounces_detected": run_stats["bounces_detected"],
            "opt_outs": run_stats["opt_outs"],
            "errors": run_stats["errors"],
            "bounce_rate_exceeded": run_stats["bounce_rate_exceeded"],
            "budget_warn_80": run_stats["budget_warn_80"],
            "budget_skip_scraping_90": run_stats["budget_skip_scraping_90"],
            "duration_seconds": duration_seconds,
        }
        try:
            send_summary(
                summary_stats,
                to_primary=primary_email,
                from_addr=outreach_email,
                app_password=outreach_password,
            )
        except Exception:
            # send_summary already swallows and prints fallback; keep guard anyway.
            logger.exception("send_summary wrapper failed")

    # Step 12 (state.db commit) is handled by GitHub Actions workflow.
    return 0


if __name__ == "__main__":
    sys.exit(main())
