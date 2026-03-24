# build_plan.md — Build Plan & Module Specifications

## 1. Purpose

This document defines the build dependency graph and module-level
specifications for the Cold Email Pipeline.

Unlike a strict phase-lock, modules can be built in parallel
where dependencies allow. The rule is:
**Do not start a module until its upstream dependencies are verified.**

---

## 2. Dependency Graph

```
                    ┌─────────────────┐
                    │  SQLite Schema   │
                    │   (db/schema)    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
     ┌────────────┐  ┌─────────────┐  ┌──────────┐
     │ RSS Scraper │  │ Gmail SMTP  │  │  Gemini  │
     │  + Manual   │  │   Setup     │  │  Writer  │
     │   Queue     │  │             │  │+Fallback │
     └──────┬─────┘  └──────┬──────┘  └────┬─────┘
            │               │              │
            ▼               │              │
     ┌─────────────┐        │              │
     │ MiniLM      │        │              │
     │ Ranker      │        │              │
     └──────┬──────┘        │              │
            │               │              │
            ▼               │              │
     ┌─────────────┐        │              │
     │   Finder    │        │              │
     │ Waterfall   │        │              │
     │ +Role Match │        │              │
     └──────┬──────┘        │              │
            │               │              │
            └───────┬───────┘──────────────┘
                    ▼
           ┌────────────────┐
           │  Main Pipeline │
           │   (main.py)    │
           └───────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │  Reply Tracker  │
          │  (after first   │
          │  emails sent)   │
          └───────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │  GitHub Actions  │
         │   Workflow       │
         │ (after pipeline  │
         │  works locally)  │
         └──────────────────┘
```

---

## 3. Module Specifications

### Module 0: SQLite Schema (`src/db/schema.py`)

**Upstream deps:** None
**Objective:** Create all tables, provide helper functions for common queries.

**Deliverables:**
- `init_db(db_path) -> Connection` — creates all tables if not exist
- `backup_db(db_path)` — copies state.db to state.db.backup
- `is_company_contacted(domain, days=60) -> bool`
- `is_email_not_found(domain, days=30) -> bool`
- `insert_job(job_dict)` — INSERT OR IGNORE
- `insert_contact(contact_dict)` — inserts into companies_contacted
- `insert_queue(queue_dict)` — inserts into email_queue
- `insert_not_found(not_found_dict)`
- `get_pending_queue(limit) -> list` — ordered by relevance_score DESC
- `mark_queue_sent(queue_id)`
- `mark_queue_failed(queue_id)`
- `get_follow_ups_due() -> list`
- `mark_follow_up_sent(contact_id)`
- `mark_bounced(email)`
- `mark_opted_out(email)`
- `mark_reply(email, reply_type, reply_text)`
- `insert_run_log(stats_dict)`

**Exit criteria:**
- All tables created without error on fresh db.
- All tables created without error on existing db (idempotent).
- All helper functions pass unit tests per contracts.md Section 6.1.

---

### Module 1: RSS Scraper + Manual Queue (`src/scraper/rss.py`, `src/scraper/manual.py`)

**Upstream deps:** Module 0 (SQLite)
**Objective:** Fetch jobs from RSS feeds and manual queue, deduplicate, insert into jobs_seen.

**Deliverables:**
- `fetch_rss(feed_url, source_name) -> list[dict]`
- `fetch_all_rss() -> list[dict]` — calls fetch_rss for each configured feed
- `load_manual_queue(filepath) -> list[dict]`
- `merge_and_deduplicate(jobs, db_conn) -> list[dict]` — filters out known job_ids

**RSS feeds (V1):**
- RemoteOK: `https://remoteok.com/remote-jobs.rss`
- We Work Remotely: `https://weworkremotely.com/categories/remote-programming-jobs.rss`
- Jobspresso: `https://jobspresso.co/remotework/feed/`

**Exit criteria:**
- RSS parser returns expected structure for each feed.
- Malformed XML returns empty list, no crash.
- Manual queue handles missing/empty file gracefully.
- Deduplication blocks known job_ids.

---

### Module 2: Email Writer (`src/writer/gemini.py`, `src/writer/fallback.py`)

**Upstream deps:** Module 0 (SQLite, for schema awareness)
**Objective:** Generate personalized email + 3 subject options via Gemini, with fallback templates.

**Deliverables:**
- `generate_email(person_name, person_title, company, jd_summary, resume_bullets) -> dict`
  Returns: `{"subject_options": [str, str, str], "body": str}`
- `generate_fallback(person_name, company, relevant_skill, project_name, project_desc) -> dict`
  Returns: same structure, from hardcoded templates
- 3-4 hardcoded fallback templates in `fallback.py`

**Gemini prompt constraints (enforced in code):**
- Max 150 words in body
- Plain text only
- Must reference company name
- Must reference one resume project
- No buzzwords, no "passionate", no "synergy"
- Vary sentence length, alternate openings
- Include one casual phrase for human tone

**Exit criteria:**
- Gemini output is under 150 words (validated post-generation, retry once if over).
- Gemini failure triggers fallback without crash.
- Fallback templates fill all placeholders without KeyError.
- Subject options list has exactly 3 items.

---

### Module 3: Gmail SMTP Sender (`src/sender/smtp.py`)

**Upstream deps:** Module 0 (SQLite)
**Objective:** Send emails from queue via SMTP, respect warmup limits, skip weekends.

**Deliverables:**
- `should_skip_today() -> bool` — True on weekends
- `get_warmup_limit(first_send_date) -> int` — returns daily limit based on week number
- `send_email(to_addr, subject, body, from_addr, app_password) -> bool`
- `process_queue(db_conn, daily_limit) -> dict` — sends up to limit, returns stats
- `send_follow_ups(db_conn) -> dict` — sends due follow-ups, returns stats
- `send_summary(stats, to_primary_email)` — sends daily summary to personal inbox

**Implementation rules:**
- Unsubscribe line appended to every outgoing body.
- Follow-ups use hardcoded template (no Gemini call).
- Follow-ups processed BEFORE new emails (priority).
- Summary email sent even if zero emails were sent (heartbeat).

**Exit criteria:**
- Weekend skip works correctly (mocked datetime tests).
- Warmup limits match schedule per week.
- Queue respects daily limit.
- Unsubscribe line present in every sent email.

---

### Module 4: Finder Waterfall (`src/finder/waterfall.py`, `src/finder/role_match.py`)

**Upstream deps:** Module 0 (SQLite)
**Objective:** Given a company + domain, find the CTO/technical lead's name and email.

**Waterfall levels:**
1. Scrape `/about`, `/team`, `/leadership` pages → spaCy NER extracts names → role_match identifies technical leader → look for email on page → if found, STOP
2. GitHub API: search org members, extract names from bios, check email in profile → if found, STOP
3. DuckDuckGo search: `"CTO" site:{domain}` or `"{company}" CTO email` → extract name from snippet (max 5 queries, 5-10s delays) → if name found, continue
4. Email permutation: generate 8-10 patterns (`first@domain`, `first.last@domain`, etc.)
5. Verification: Gravatar MD5 check → if hit, accept. Else, use `firstname@domain.com` as default pattern.

**Deliverables:**
- `find_contact(company, domain, db_conn) -> Optional[dict]`
  Returns: `{"name": str, "title": str, "email": str, "source": str, "confidence": str}` or None
- `extract_roles(text, names) -> Optional[tuple[str, str]]` — returns (name, title) or None
- `generate_permutations(first, last, domain) -> list[str]`
- `check_gravatar(email) -> bool`

**Exit criteria:**
- Role matcher correctly identifies CTO from context text.
- Role matcher returns None when no technical role found.
- Permutation generator produces expected patterns.
- Gravatar returns True for known hash, False for random.
- Full waterfall returns None (not crash) when all levels fail.

---

### Module 5: MiniLM Ranker (`src/ranker/minilm.py`)

**Upstream deps:** Module 0 (SQLite), Module 1 (jobs exist in db)
**Objective:** Rank all unprocessed jobs by cosine similarity to resume, select top-N.

**Deliverables:**
- `load_model() -> SentenceTransformer` — loads all-MiniLM-L6-v2
- `get_resume_embedding(resume_text) -> ndarray` — computed once per run
- `rank_jobs(jobs, resume_embedding, model) -> list[dict]` — adds relevance_score, sorts descending
- `select_top_n(ranked_jobs, n=25) -> list[dict]`

**Resume text:** Concatenation of the 5 resume bullets from `agent_project.md` Section 6.
**Job text:** Concatenation of `title + " " + company + " " + jd_summary`.

**Exit criteria:**
- Ranking produces scores between 0.0 and 1.0.
- Top-N selection returns min(N, len(ranked_jobs)) items.
- Model loads without error on GitHub Actions (cached).

---

### Module 6: Reply Tracker (`src/tracker/imap.py`, `src/tracker/classifier.py`)

**Upstream deps:** Module 0 (SQLite), Module 3 (emails must have been sent)
**Objective:** Check inbox for replies and bounces, update database.

**Deliverables:**
- `check_inbox(imap_conn, db_conn) -> dict` — returns {replies: int, bounces: int, opt_outs: int}
- `is_bounce(sender, subject) -> bool`
- `is_opt_out(body_text) -> bool`
- `extract_bounced_address(msg_body) -> Optional[str]`
- `classify_reply(body_text) -> str` — uses Gemini if available, else keyword matching

**Bounce detection keywords:** `mailer-daemon`, `postmaster`, `delivery failure`, `undeliverable`
**Opt-out keywords:** `stop`, `unsubscribe`, `remove`, `opt out`, `not interested`

**Exit criteria:**
- Bounce detector catches mailer-daemon senders.
- Bounce detector catches delivery failure subjects.
- Opt-out detector catches all listed keywords.
- Reply with no bounce/optout markers is classified normally.
- Follow-up query excludes bounced, opted-out, and already-replied contacts.

---

### Module 7: GitHub Actions Workflow (`.github/workflows/daily.yml`)

**Upstream deps:** All modules working locally
**Objective:** Run pipeline daily on weekdays at ~9AM IST.

**Deliverables:**
- Cron schedule for ~9AM IST (3:30 AM UTC)
- Random jitter (0-45 min sleep)
- Dependency caching (pip, playwright, huggingface, spacy)
- state.db backup before run
- state.db commit after run
- Weekend skip (first step)

**Exit criteria:**
- Workflow runs without error on GitHub Actions.
- Cache hit on second run (no re-download of models).
- state.db is committed back to repo.
- Weekend trigger exits immediately with 0.

---

## 4. Build Order (Recommended)

```
Week 1:
  ✓ Module 0: SQLite schema + tests
  ✓ Module 1: RSS scraper + manual queue
  ✓ Create dedicated outreach Gmail + App Password

Week 2:
  ✓ Module 2: Gemini writer + fallback templates
  ✓ Module 3: SMTP sender + summary email
  → Manually find 3-5 targets, run writer + sender
  → FIRST REAL EMAILS SENT by end of week 2

Week 3:
  ✓ Module 4: Finder waterfall + role match
  ✓ Module 5: MiniLM ranker

Week 4:
  ✓ Module 6: Reply tracker
  ✓ Module 7: GitHub Actions workflow
  → Full automation live

Week 5+:
  Monitor, tune Gemini prompts, add manual targets weekly.
  After 100+ emails: Logistic Regression on reply data.
```

---

## 5. Final Statement

This build plan is a guide, not a cage. If a module is blocked,
work on a parallel-ready module. But never skip upstream verification.