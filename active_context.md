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

**Task:** Build Module 0 — SQLite schema and helper functions.

**What exists:** Nothing yet. Fresh start.

**What needs to happen this session:**
- Create `src/db/schema.py` with all table definitions per contracts.md Section 3
- Implement all helper functions per build_plan.md Module 0
- Create `tests/test_db.py` with tests per contracts.md Section 6.1
- All tests passing

**Relevant contract sections:** contracts.md Section 3 (full schema), Section 6.1 (test specs)

**Constraints:**
- Python 3.10+, sqlite3 standard library only
- No ORM. Raw SQL with parameterized queries.
- All timestamps as ISO-8601 UTC strings.

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