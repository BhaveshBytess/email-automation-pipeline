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

**Task:** Build Module 2 — Email Writer (Gemini + Fallback Templates)

**What exists:**
- `src/db/schema.py` — 17 helper functions, 8/8 tests passing
- `src/scraper/rss.py` — RSS fetcher, keyword filter, SHA-256 IDs
- `src/scraper/manual.py` — manual queue loader
- Full suite: 13/13 tests passing

**What needs to happen this session:**
- Create `src/writer/gemini.py`:
  - `generate_email(person_name, person_title, company, 
    jd_summary, resume_bullets) -> dict`
  - Returns: `{"subject_options": [str, str, str], "body": str}`
  - Gemini API call with prompt constraints enforced in code
  - Post-generation word count validation — if body > 150 words,
    retry once, then fall back to template
  - On any Gemini failure → call generate_fallback(), log warning

- Create `src/writer/fallback.py`:
  - `generate_fallback(person_name, company, relevant_skill,
    project_name, project_desc) -> dict`
  - Returns same structure as gemini.py
  - 3-4 hardcoded templates, randomly selected
  - All placeholders must fill without KeyError

- Create `src/writer/__init__.py` — empty package marker

- Create `tests/test_writer.py` with tests per
  contracts.md Section 6.4

**Gemini prompt constraints (enforce in code, not just prompt):**
- Plain text only, no markdown, no bullet points
- Max 150 words in body (validate post-generation)
- No "I hope this email finds you well"
- No "passionate", "synergy", "leverage"
- Must contain company name
- Must reference one resume project
- Vary sentence length
- Alternate opening styles
- One casual phrase per email
- Human tone — typed fast, not templated
- Structural variation per email

**Subject line:**
- Gemini generates exactly 3 options
- Vary structure: question / statement / name drop
- subject_options list must have exactly 3 items
- Validated post-generation

**Resume bullets to inject (from agent_project.md Section 6):**
1. Built temporal GNN (TRDGNN) achieving 0.58 PR-AUC on 
   203K-node fraud detection graph — PyTorch Geometric, XGBoost
2. PDF-to-JSON pipeline with 100% JSON validity and 81% 
   evidence precision — LLMs, Pydantic, Gemma, DeepSeek
3. 10x GNN parameter reduction (500K→50K) with +108% 
   performance gain on resource-constrained systems
4. Python, PyTorch, PyG, TensorFlow, scikit-learn, Docker, 
   Git, Linux, Streamlit, Pydantic
5. CS undergrad IIIT Kota — GNNs and unstructured data 
   pipelines, production-ready ML, full test coverage

**Relevant contract sections:**
- contracts.md Section 6.4 (test specifications)
- agent_project.md Section 5.2 (email content rules)
- agent_project.md Section 2.3 (sending rules — plain text,
  unsubscribe line NOT added here, that is sender's job)

**Constraints:**
- Gemini API key via environment variable GEMINI_API_KEY
- Use google-generativeai SDK (free tier)
- No API key hardcoded anywhere
- All timestamps: datetime.now(timezone.utc).isoformat()
- New dependency: google-generativeai

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