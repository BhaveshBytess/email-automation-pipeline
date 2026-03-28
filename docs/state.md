# state.md — Current System State

**Last Updated:** 2026-03-27

---

## Current Module: Module 7 — GitHub Actions workflow (Completed)

## Completed Modules:
- [x] Module 0: SQLite schema + tests
- [x] Module 1: RSS scraper + manual queue
- [x] Module 2: Gemini writer + fallback templates
- [x] Module 3: SMTP sender + summary email
- [x] Module 4: Finder waterfall + role match
- [x] Module 5: MiniLM ranker
- [x] Module 6: Reply tracker
- [x] Module 7: GitHub Actions workflow

## Module 7 Results:
- `main.py`: end-to-end pipeline entrypoint wired to contracts.md Section 4 flow with graceful degradation
- `.github/workflows/daily.yml`: weekday cron workflow with weekend exit, jitter, caching, cache-miss-only spaCy download, and state DB commit/push
- `requirements.txt`: pinned project dependency manifest for workflow installs
- Full suite passing after integration: 54/54

## Module 6 Results:
- `src/tracker/imap.py`: inbox polling, bounce detection, opt-out detection, bounced-email extraction, reply matching, and bounce-rate circuit breaker flag
- `src/tracker/classifier.py`: Gemini-first reply classifier with keyword fallback
- `src/tracker/__init__.py`: empty package marker
- `tests/test_tracker.py`: 8 tests aligned to contracts.md Section 6.6
- Tracker tests passing: 8/8
- Full suite passing: 54/54

## Module 5 Results:
- `src/ranker/minilm.py`: model loader, resume embedding, job ranking, top-N selection
- `src/ranker/__init__.py`: empty package marker
- `tests/test_ranker.py`: 5 tests with fully mocked model encoding (no real model load)
- Added dependency: `sentence-transformers`
- Ranker tests passing: 5/5
- Full suite passing: 46/46

## Module 4 Results:
- `src/finder/role_match.py`: name-first role matcher with ROLE_PRIORITY and local context scan around each name
- `src/finder/waterfall.py`: 5-level finder waterfall (team pages, GitHub, DuckDuckGo, permutations, Gravatar/default pattern)
- `src/finder/__init__.py`: empty package marker
- `tests/test_finder.py`: 7 tests aligned to contracts.md Section 6.3
- Priority behavior verified: CTO preferred over Co-founder when both are present
- Module tests passing: 7/7
- Full suite passing: 41/41

## Module 0 Results:
- All 5 tables created per contracts.md Section 3
- 17 helper functions implemented per build_plan.md Module 0
- 8/8 tests passing per contracts.md Section 6.1
- `backup_db` uses SQLite online backup API (WAL-safe)
- All timestamps use `datetime.now(timezone.utc)` (Python 3.12+ compliant)

## Module 1 Results:
- `src/scraper/rss.py`: RSS feed fetcher with keyword filtering, SHA-256 job IDs, company extraction, `merge_and_deduplicate`
- `src/scraper/manual.py`: Manual queue loader (required: company/domain/jd_summary; optional: url/title)
- `data/manual_queue.json`: Starter file (empty array)
- 5/5 tests passing per contracts.md Section 6.2
- Dependency added: `feedparser`

## Module 2 Results:
- `src/writer/gemini.py`: Gemini API email writer with structured prompt, post-generation validation (word count ≤ 150, banned phrases, company name, subject count), retry once if over limit, auto-fallback
- `src/writer/fallback.py`: 4 hardcoded templates, `.format()` placeholders, all < 150 words
- 6/6 tests passing per contracts.md Section 6.4
- Dependency added: `google-generativeai`
- Resume bullets from agent_project.md Section 6 hardcoded as `_RESUME_BULLETS`

## Module 3 Results:
- `src/sender/smtp.py`: 6 functions — `should_skip_today`, `get_warmup_limit`, `send_email`, `process_queue`, `send_follow_ups`, `send_summary`
- Transactional queue processing: mark_sent + insert_contact wrapped in BEGIN/COMMIT with rollback on failure
- FC-04 compliant: SMTP failures leave emails as 'pending', summary falls back to stdout
- Unsubscribe line appended to every outgoing body
- 15/15 tests passing (3 weekend + 10 warmup + 1 unsubscribe + 1 queue limit)
- No new dependencies (stdlib smtplib only)

## Outreach Gmail Account:
- [ ] Created
- [ ] 2FA enabled
- [ ] App Password generated
- [ ] Tested with smtplib locally

## Open Decisions:
- None

## Known Issues:
- None

## Files Created:
- `src/__init__.py`
- `src/db/__init__.py`
- `src/db/schema.py`
- `src/scraper/__init__.py`
- `src/scraper/rss.py`
- `src/scraper/manual.py`
- `src/writer/__init__.py`
- `src/writer/gemini.py`
- `src/writer/fallback.py`
- `src/sender/__init__.py`
- `src/sender/smtp.py`
- `src/finder/__init__.py`
- `src/finder/role_match.py`
- `src/finder/waterfall.py`
- `src/ranker/__init__.py`
- `src/ranker/minilm.py`
- `src/tracker/__init__.py`
- `src/tracker/imap.py`
- `src/tracker/classifier.py`
- `main.py`
- `.github/workflows/daily.yml`
- `requirements.txt`
- `data/manual_queue.json`
- `tests/__init__.py`
- `tests/test_db.py`
- `tests/test_scraper.py`
- `tests/test_writer.py`
- `tests/test_sender.py`
- `tests/test_finder.py`
- `tests/test_ranker.py`
- `tests/test_tracker.py`

## Session Log:
| Date       | Session # | What Was Done                          | What Remains                    |
|------------|-----------|----------------------------------------|---------------------------------|
| 2026-03-24 | 1         | Module 0: SQLite schema + 8/8 tests   | Module 1: RSS scraper + manual  |
| 2026-03-25 | 2         | Module 1: RSS scraper + 5/5 tests     | Module 2: Gemini writer         |
| 2026-03-25 | 3         | Module 2: Gemini writer + 6/6 tests   | Module 3: SMTP sender           |
| 2026-03-25 | 4         | Module 3: SMTP sender + 15/15 tests   | Module 4: Finder waterfall      |
| 2026-03-27 | 5         | Module 4: Finder waterfall + 7/7 tests| Module 5: MiniLM ranker         |
| 2026-03-27 | 6         | Module 5: MiniLM ranker + 5/5 tests   | Module 6: Reply tracker         |
| 2026-03-27 | 7         | Module 6: Reply tracker + 8/8 tests   | Module 7: GitHub Actions workflow |
| 2026-03-28 | 8         | Module 7: main.py + daily workflow    | Automation live                 |

---

## Metrics (Updated weekly once live):
- Total emails sent: 0
- Total replies: 0
- Reply rate: N/A
- Bounce rate: N/A
- Opt-out rate: N/A
- Best performing subject variant: N/A