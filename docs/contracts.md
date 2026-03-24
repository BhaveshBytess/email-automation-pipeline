# contracts.md — System Contracts & Invariants

## 1. Purpose

This document defines the schemas, failure contracts, and test
specifications for the Cold Email Pipeline.

Any module that reads or writes data MUST conform to these contracts.
Any AI agent working on this project MUST validate its output against
this document.

---

## 2. Versioning

- **Current Version:** V1
- All changes require:
  1. Version bump (V1 → V2)
  2. Date of change
  3. One-line rationale
  4. List of affected modules

---

## 3. Database Schema Contracts (SQLite — state.db)

### 3.1 Table: jobs_seen

Stores every job posting discovered by any source.

```sql
CREATE TABLE IF NOT EXISTS jobs_seen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,          -- deterministic hash of url or title+company
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    domain TEXT,                          -- company website domain (e.g., "acme.com")
    url TEXT,
    source TEXT NOT NULL,                 -- "rss_remoteok", "rss_wwr", "manual", "duckduckgo", etc.
    jd_summary TEXT,                      -- job description or summary text
    relevance_score REAL,                 -- cosine similarity from MiniLM (0.0 to 1.0)
    discovered_at TEXT NOT NULL,          -- ISO-8601 UTC
    processed INTEGER DEFAULT 0           -- 0=pending, 1=processed (sent to finder)
);
```

**Rules:**
- `job_id` is a SHA-256 hash of `url` if url exists, else hash of `title + company`.
- Duplicate `job_id` inserts are silently ignored (INSERT OR IGNORE).
- `relevance_score` is NULL until the ranker processes the row.
- `source` must be one of the enumerated values defined in Section 3.6.

### 3.2 Table: companies_contacted

Stores every company/person pair that received an email.

```sql
CREATE TABLE IF NOT EXISTS companies_contacted (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    domain TEXT NOT NULL,
    person_name TEXT NOT NULL,
    person_title TEXT,                    -- "CTO", "Co-founder", "VP Engineering", etc.
    email TEXT NOT NULL,
    email_source TEXT NOT NULL,           -- "team_page", "github", "duckduckgo", "permutation"
    email_confidence TEXT NOT NULL,       -- "direct_find", "gravatar_verified", "default_pattern"
    
    subject TEXT NOT NULL,
    subject_variant INTEGER NOT NULL,     -- which of 3 generated subjects was picked (1, 2, or 3)
    email_body TEXT NOT NULL,
    
    sent_at TEXT NOT NULL,                -- ISO-8601 UTC
    
    reply INTEGER DEFAULT 0,             -- 0=no reply, 1=replied
    reply_type TEXT,                      -- "positive", "neutral", "negative", "opted_out"
    reply_text TEXT,
    reply_at TEXT,                        -- ISO-8601 UTC
    
    bounced INTEGER DEFAULT 0,           -- 0=delivered, 1=bounced
    bounced_at TEXT,
    
    follow_up_date TEXT,                  -- ISO-8601 date when follow-up should be sent
    follow_up_sent INTEGER DEFAULT 0,    -- 0=not sent, 1=sent
    
    opted_out INTEGER DEFAULT 0,         -- 0=active, 1=opted out
    
    job_id TEXT,                          -- FK reference to jobs_seen.job_id
    relevance_score REAL                  -- copied from jobs_seen at send time
);
```

**Rules:**
- A company+domain pair must not appear again within 60 days of `sent_at`.
- `follow_up_date` is set to `sent_at + 5 business days` at insert time.
- Follow-up is NEVER sent if `bounced=1` OR `opted_out=1` OR `reply=1`.
- `email_body` stores the full email text exactly as sent. No truncation.

### 3.3 Table: email_queue

Stores emails ready to send but not yet sent (buffer for warmup limits).

```sql
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
    queued_at TEXT NOT NULL,              -- ISO-8601 UTC
    status TEXT DEFAULT 'pending'         -- "pending", "sent", "failed"
);
```

**Rules:**
- The sender pulls from this queue up to the daily warmup limit.
- Status transitions: pending → sent (moved to companies_contacted) or pending → failed (logged, stays in queue for retry next run).
- Queue is processed in order of `relevance_score DESC`.

### 3.4 Table: email_not_found

Stores companies where the finder waterfall failed entirely.

```sql
CREATE TABLE IF NOT EXISTS email_not_found (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    domain TEXT NOT NULL,
    job_id TEXT,
    reason TEXT NOT NULL,                 -- "no_team_page", "no_github", "no_ddg_result", "verification_failed"
    failed_at TEXT NOT NULL,              -- ISO-8601 UTC
    retry_after TEXT NOT NULL             -- ISO-8601 date (failed_at + 30 days)
);
```

**Rules:**
- Same domain must not be retried before `retry_after` date.
- `reason` must be one of the enumerated values. No freeform text.

### 3.5 Table: run_log

Stores metadata about each daily pipeline run.

```sql
CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,               -- ISO-8601 date
    jobs_found INTEGER DEFAULT 0,
    jobs_relevant INTEGER DEFAULT 0,
    emails_found INTEGER DEFAULT 0,
    emails_sent INTEGER DEFAULT 0,
    follow_ups_sent INTEGER DEFAULT 0,
    bounces_detected INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    duration_seconds REAL,
    started_at TEXT NOT NULL,             -- ISO-8601 UTC
    finished_at TEXT                      -- ISO-8601 UTC
);
```

### 3.6 Enumerated Values

**source (jobs_seen):**
`rss_remoteok`, `rss_wwr`, `rss_jobspresso`, `scraper_yc`, `scraper_greenhouse`,
`scraper_lever`, `scraper_ashby`, `scraper_internshala`, `scraper_unstop`,
`duckduckgo`, `manual`

**email_source (companies_contacted):**
`team_page`, `github`, `duckduckgo`, `permutation`

**email_confidence (companies_contacted):**
`direct_find`, `gravatar_verified`, `default_pattern`

**reason (email_not_found):**
`no_team_page`, `no_github`, `no_ddg_result`, `verification_failed`, `no_role_match`

**reply_type (companies_contacted):**
`positive`, `neutral`, `negative`, `opted_out`

---

## 4. Data Flow Contract

```
[Job Sources] → jobs_seen (deduplicated)
     ↓
[MiniLM Ranker] → updates relevance_score, selects top-N
     ↓
[Finder Waterfall] → either email_queue OR email_not_found
     ↓
[Gemini Writer] → generates subject + body, stores in email_queue
     ↓
[SMTP Sender] → sends from queue, moves to companies_contacted
     ↓
[IMAP Tracker] → updates reply/bounce/opt-out in companies_contacted
     ↓
[Summary Email] → sent to primary Gmail with run_log stats
```

**Invariants:**
- Every row in `companies_contacted` must have a corresponding `job_id` in `jobs_seen`.
- Every email sent must pass through `email_queue` first. No direct sending.
- The sender NEVER decides email content. It only transmits what the writer produced.
- The tracker NEVER modifies `email_body` or `subject`. It only updates reply/bounce fields.

---

## 5. Failure Contracts

### FC-01: Gemini API Unavailable
- **Behavior:** Use fallback template from `writer/fallback.py`. Log warning.
- **NOT acceptable:** Skip the email. Crash the pipeline. Send empty body.

### FC-02: Email Bounces
- **Behavior:** Mark `bounced=1`. Set `bounced_at`. Block follow-up. Log the failed email pattern.
- **NOT acceptable:** Retry sending. Send follow-up anyway. Ignore the bounce.

### FC-03: Scraper Returns Zero Results
- **Behavior:** Process `manual_queue.json` only. Log warning. Send summary noting zero scraper results.
- **NOT acceptable:** Skip the entire run. Crash. Send no summary.

### FC-04: SMTP Connection Fails
- **Behavior:** All queued emails stay as `status='pending'`. Log error. Send summary via fallback (print to stdout if SMTP is fully dead). Retry next run.
- **NOT acceptable:** Mark emails as sent. Crash. Lose queue state.

### FC-05: SQLite Database Locked / Corrupted
- **Behavior:** Restore from `state.db.backup`. Log critical error. Send summary noting restore event.
- **NOT acceptable:** Create a new empty database. Continue with corrupted data.

### FC-06: GitHub Actions Budget Approaching Limit
- **Behavior:** At 80% usage (1600 min), log warning in summary. At 90% (1800 min), skip scraping and process manual queue only.
- **NOT acceptable:** Exceed budget silently. Skip runs without logging.

### FC-07: Bounce Rate Exceeds 5%
- **Behavior:** Pause all sending. Log critical alert. Summary email flags this explicitly.
- **NOT acceptable:** Continue sending. Ignore bounce rate.

---

## 6. Test Specifications

### 6.1 SQLite State Manager (test_db.py)
- Insert a job into `jobs_seen`, retrieve it by `job_id`.
- Insert duplicate `job_id` — verify silent ignore, no crash.
- Insert into `companies_contacted` — verify 60-day dedup blocks re-insert.
- Insert into `email_not_found` — verify 30-day retry window.
- Create backup — verify backup file exists and is valid SQLite.
- Run all table creations twice — verify idempotent (no crash on second run).

### 6.2 Scraper (test_scraper.py)
- RSS parser returns list of dicts with required keys (title, company, url, source).
- RSS parser handles malformed XML without crashing (returns empty list).
- Manual queue parser reads valid JSON and returns expected format.
- Manual queue parser handles empty file (returns empty list).
- Manual queue parser handles missing file (returns empty list, logs warning).

### 6.3 Finder (test_finder.py)
- Role matcher identifies "CTO" from surrounding text.
- Role matcher identifies "Co-founder" from surrounding text.
- Role matcher returns None when no technical role is found.
- Role matcher prefers CTO over generic "Co-founder" when both exist.
- Email permutation generator produces expected patterns for known input.
- Gravatar check returns True for known-existing hash (test with a real one).
- Gravatar check returns False for random hash.

### 6.4 Writer (test_writer.py)
- Gemini writer returns string under 150 words (mock API response).
- Gemini writer includes company name in output.
- Gemini writer includes at least one resume project reference.
- Fallback template fills all placeholders without KeyError.
- Fallback template is under 150 words.
- Subject generator returns exactly 3 options.

### 6.5 Sender (test_sender.py)
- Weekend check returns True for Saturday/Sunday (mock datetime).
- Weekend check returns False for weekday.
- Warmup counter returns correct limit for each week number.
- Unsubscribe line is present in every outgoing email body.
- Queue processing respects daily limit (mock: set limit to 2, queue 5, verify 2 sent).

### 6.6 Tracker (test_tracker.py)
- Bounce detector identifies mailer-daemon sender.
- Bounce detector identifies "delivery failure" subject.
- Opt-out detector catches "stop", "unsubscribe", "remove me".
- Reply classifier marks non-bounce, non-optout reply as needing classification.
- Follow-up query returns only contacts with: no reply, no bounce, no opt-out, follow_up_date <= today, follow_up_sent = 0.

---

## 7. Final Statement

This document is authoritative for the Cold Email Pipeline.
If implementation conflicts with this file, this file wins.