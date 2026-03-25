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

**Task:** Build Module 1 — RSS Scraper + Manual Queue

**What exists:**
- `src/db/schema.py` — fully implemented, 8/8 tests passing
- `src/db/__init__.py`, `src/__init__.py`, `tests/__init__.py`

**What needs to happen this session:**
- Create `src/scraper/rss.py`:
  - `fetch_rss(feed_url: str, source_name: str) -> list[dict]`
  - `fetch_all_rss() -> list[dict]`
  - Feeds: RemoteOK, We Work Remotely, Jobspresso
  - Filter by keywords: ML, AI, machine learning, backend, 
    Python, NLP, deep learning, data engineering
  - Each returned dict must have: title, company, url, 
    source, jd_summary, job_id (SHA-256 hash of url)
  - Malformed XML returns empty list, no crash

- Create `src/scraper/manual.py`:
  - `load_manual_queue(filepath: str) -> list[dict]`
  - Handles missing file, empty file, malformed JSON 
    gracefully — returns empty list, logs warning

- Create `src/scraper/__init__.py` — empty package marker

- Create `data/manual_queue.json` — empty array `[]` as starter

- Create `tests/test_scraper.py` with tests per 
  contracts.md Section 6.2

**Relevant contract sections:**
- contracts.md Section 3.1 (jobs_seen schema — 
  returned dicts must match this structure)
- contracts.md Section 3.6 (enumerated source values)
- contracts.md Section 6.2 (test specifications)

**Constraints:**
- feedparser for RSS parsing (only new dependency)
- requests + BeautifulSoup for any HTTP (already in stack)
- No Playwright in this module
- job_id = SHA-256 hash of url if url exists, 
  else hash of title + company
- discovered_at = ISO-8601 UTC string
- source must be one of: rss_remoteok, rss_wwr, 
  rss_jobspresso, manual
- All timestamps: datetime.now(timezone.utc).isoformat()
  NOT datetime.utcnow()

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