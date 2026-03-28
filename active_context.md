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

**Task:** Build Module 7 — GitHub Actions Workflow

**What exists:**
- src/db/schema.py — 8/8 tests passing
- src/scraper/rss.py + manual.py — 5/5 tests passing
- src/writer/gemini.py + fallback.py — 6/6 tests passing
- src/sender/smtp.py — 15/15 tests passing
- src/finder/role_match.py + waterfall.py — 7/7 tests passing
- src/ranker/minilm.py — 5/5 tests passing
- src/tracker/imap.py + classifier.py — 8/8 tests passing
- Full suite: 54/54 passing
- All modules complete and pushed to main

**What needs to happen this session:**
- Create main.py in project root:
  Entry point that wires all modules together
  in correct data flow order per contracts.md
  Section 4:

  1. backup_db()
  2. should_skip_today() → exit 0 if weekend
  3. fetch_all_rss() + load_manual_queue()
  4. merge_and_deduplicate()
  5. rank_jobs() → select_top_n(n=25)
  6. for each job → find_contact()
  7. generate_email() → insert_queue()
  8. check_inbox() → process replies/bounces
  9. send_follow_ups()
  10. process_queue(daily_limit)
  11. send_summary(stats)
  12. commit state.db back to repo

  Graceful degradation at every step:
  log error and continue, never crash

- Create .github/workflows/daily.yml:
  Cron: '30 3 * * 1-5'
  (3:30 AM UTC = ~9 AM IST, weekdays only)

  Jobs:
  - Random jitter: sleep $((RANDOM % 45))m
  - Checkout repo (with full git history
    so state.db commit works)
  - Setup Python 3.11
  - Cache dependencies:
    ~/.cache/pip
    ~/.cache/huggingface/hub
    key: deps-${{ hashFiles('requirements.txt') }}
  - pip install -r requirements.txt
  - python main.py
  - Commit state.db back to repo if changed

- Create requirements.txt with all dependencies:
  feedparser
  requests
  beautifulsoup4
  spacy
  sentence-transformers
  google-generativeai
  gspread
  google-auth
  python-dotenv

**Environment variables (GitHub Actions secrets):**
  OUTREACH_EMAIL
  OUTREACH_APP_PASSWORD
  GEMINI_API_KEY
  GITHUB_TOKEN (auto-provided by Actions)

**Relevant contract sections:**
- contracts.md Section 4 (data flow — order is law)
- contracts.md FC-03 (zero scraper results → 
  process manual queue only, never crash)
- contracts.md FC-04 (SMTP fail → queue stays
  pending, log error)
- contracts.md FC-06 (GitHub Actions budget —
  log warning at 80%, skip scraping at 90%)
- contracts.md FC-07 (bounce rate > 5% →
  pause sending, alert in summary)
- agent_project.md Section 7 (GitHub Actions
  constraints — caching, jitter, state.db commit)
- decisions.md D010 (GitHub Actions as runtime)

**Constraints:**
- No new dependencies in main.py
- All secrets via os.environ — never hardcoded
- state.db committed back after every run
- state.db.backup created before run starts
- Weekend skip is first check in daily.yml
  (exit 0 immediately, burn zero minutes)
- Jitter applied before any work starts
- Dependency cache must be used — no re-download
  of 80MB MiniLM model every run
- spaCy model download in workflow:
  python -m spacy download en_core_web_sm
  (cache this too)
- main.py must run cleanly with zero emails
  sent on first run (empty queue is valid)
- Summary email sent at end of every run
  including runs with zero activity
  
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