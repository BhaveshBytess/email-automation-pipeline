# active_context.md — Session Super Prompt

## Instructions

Paste this file at the start of every AI coding session.
Update the "Current Focus" section before pasting.
This is the ONLY governance file you paste in full.
Reference other docs by name — the AI has seen them before
or you paste only the relevant section.

---

## Role

You are a professional engineer implementing a pre-designed system.
You follow the governance defined in:

1. **agent_core.md** — How you think and work (reusable rules).
2. **agent_project.md** — Project-specific constraints and domain rules.
3. **contracts.md** — Schemas, failure contracts, test specs. This is law.
4. **build_plan.md** — Dependency graph and module specifications.

Conflict resolution: **contracts.md > agent_project.md > agent_core.md > build_plan.md > code**

---

## Project Summary (Do NOT Restate — Just Internalize)

Automated cold email pipeline. Discovers jobs, finds CTO emails,
generates personalized outreach via Gemini, sends via Gmail SMTP,
tracks replies via IMAP. Runs daily on GitHub Actions. Zero budget.
SQLite state. 5 emails/day max.

---

## Current State (from state.md)

**Current Module:** Module 0 — SQLite Schema
**Completed:** None
**Known Issues:** None

---

## Current Focus

[EDIT THIS SECTION BEFORE EACH SESSION]

**Task:** Build Module 3 — Gmail SMTP Sender

**What exists:**
- src/db/schema.py — 17 helper functions, 8/8 tests
- src/scraper/rss.py + manual.py — 5/5 tests
- src/writer/gemini.py + fallback.py — 6/6 tests
- Full suite: 19/19 passing

**What needs to happen this session:**
- Create src/sender/smtp.py:
  - `should_skip_today() -> bool`
    True on Saturday and Sunday
  - `get_warmup_limit(first_send_date: date) -> int`
    wk1-2=1, wk3-4=2, wk5-6=3, wk7+=5
  - `send_email(to_addr, subject, body, 
    from_addr, app_password) -> bool`
    Plain text only. Appends unsubscribe line.
    Returns True on success, False on failure.
  - `process_queue(db_conn, daily_limit) -> dict`
    Pulls from email_queue WHERE status='pending'
    ORDER BY relevance_score DESC
    Sends up to daily_limit, returns stats dict:
    {sent, failed, skipped}
  - `send_follow_ups(db_conn) -> dict`
    Processes follow_ups_due BEFORE new emails
    Hardcoded template — NO Gemini call
    Returns {sent, skipped}
  - `send_summary(stats: dict, 
    to_primary: str, from_addr: str, 
    app_password: str) -> None`
    Sends daily heartbeat to primary Gmail
    Sent even if zero emails were sent
    Never crashes pipeline if it fails

- Create src/sender/__init__.py — empty package marker

- Create tests/test_sender.py with tests per
  contracts.md Section 6.5

**Implementation rules (non-negotiable):**
- Unsubscribe line appended to EVERY outgoing body:
  P.S. Not relevant? Reply "stop" and I'll make 
  sure you never hear from me again.
- Follow-ups processed BEFORE new emails
- Summary sent even if nothing was sent today
- SMTP credentials via env vars:
  OUTREACH_EMAIL and OUTREACH_APP_PASSWORD
- No credentials hardcoded anywhere
- All timestamps: datetime.now(timezone.utc).isoformat()
  NOT datetime.utcnow()

**Relevant contract sections:**
- contracts.md Section 6.5 (test specifications)
- contracts.md Section 4 (data flow — sender pulls 
  from email_queue, moves to companies_contacted)
- contracts.md FC-04 (SMTP failure contract)
- agent_project.md Section 2.3 (sending rules)

**Constraints:**
- smtplib + imaplib — stdlib only, no new dependencies
- Plain text emails only, no HTML
- Weekend skip must be tested with mocked datetime
- Warmup limit must be tested per week number
- Queue processing must respect daily limit

---

## Session Rules

1. Work ONLY on what is described in "Current Focus" above.
2. Do not refactor, optimize, or add features beyond the current task.
3. Output complete files. No fragments unless explicitly asked.
4. If you encounter ambiguity, ask. Do not assume.
5. When done, output a state.md update block I can paste in.

---

## After Session Checklist (For Human)

- [ ] Copy code into project files
- [ ] Run tests locally
- [ ] Fix any issues (paste errors back to AI if needed)
- [ ] Update `state.md` with session results
- [ ] Update `decisions.md` if any new decisions were made
- [ ] Git commit: `feat(module-N): description`
- [ ] Push to private repo