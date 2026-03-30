# decisions.md — Architecture Decision Records

## Purpose

Every non-obvious technical decision is logged here with context,
rationale, and consequences. This prevents re-debating settled
questions and provides audit trail for future reference.

Format: Each decision gets a unique ID, date, and status.
Status: `Accepted` | `Superseded by DXXX` | `Rejected`

---

## D001: SMTP + App Password Over Gmail API OAuth2
**Date:** [DATE]
**Context:** Gmail API OAuth2 tokens expire every 7 days when the
Google Cloud project is in "Testing" mode. Verified/published status
requires a domain and privacy policy we don't have. Pipeline runs
unattended daily — a 7-day token expiry means silent failure every
Monday.
**Decision:** Use `smtplib` with Gmail App Password for sending,
`imaplib` with same App Password for reply tracking.
**Consequence:** Lose Gmail thread ID tracking. Reply matching uses
subject line prefix (`Re:`) and sender domain instead. At 5 emails/day
this is reliable. App Passwords never expire.
**Status:** Accepted

---

## D002: Dedicated Outreach Gmail Over Primary Email
**Date:** [DATE]
**Context:** If any recipient marks a cold email as spam, Gmail may
restrict or lock the sending account. Primary email is used for
college, job applications, password resets — losing it is catastrophic.
**Decision:** Create a separate Gmail account exclusively for outreach.
Primary email is never used for cold sending.
**Consequence:** Must manage two Gmail accounts. Summary emails are
sent FROM outreach account TO primary account for monitoring.
**Status:** Accepted

---

## D003: Top-N Ranking Over Fixed Threshold
**Date:** [DATE]
**Context:** A fixed cosine similarity threshold (e.g., >0.6) is
fragile. On days with many good jobs, it lets too many through.
On slow days, it lets nothing through. The threshold itself needs
tuning data we don't have yet.
**Decision:** Always take top N jobs regardless of absolute score.
N = 25 (to account for ~20-30% email-finding success rate, targeting
5 sends/day).
**Consequence:** Some low-relevance jobs may be contacted on slow days.
Acceptable — a mediocre lead contacted is better than zero emails sent.
**Status:** Accepted

---

## D004: DuckDuckGo Over Google For Search Queries
**Date:** [DATE]
**Context:** Google actively blocks automated queries with CAPTCHAs
and IP bans. GitHub Actions runs on well-known Azure IP ranges that
are pre-flagged by Google.
**Decision:** Use DuckDuckGo for all programmatic search queries.
Max 10 queries per run, 5-10 second delays between queries.
**Consequence:** Slightly worse search result quality than Google.
Acceptable tradeoff for zero block risk.
**Status:** Accepted

---

## D005: Remove SMTP Email Verification
**Date:** [DATE]
**Context:** SMTP verification (RCPT TO check) requires connecting
to the target company's mail server. GitHub Actions IPs are on
Azure ranges that are widely blacklisted by mail servers. Most
responses would be connection refused, timeout, or false positives
from catch-all servers.
**Decision:** Remove SMTP verification entirely. Verification stack
is: direct find → Gravatar MD5 → default pattern (firstname@domain).
**Consequence:** Higher bounce rate on permutation-guessed emails.
Mitigated by bounce detection and the 5% bounce rate circuit breaker.
**Status:** Accepted

---

## D006: Remove WellFound Automated Scraping
**Date:** [DATE]
**Context:** WellFound uses Cloudflare with aggressive bot detection
and JavaScript challenges. GitHub Actions IPs are among the first
blocked. Playwright with rotated user agents is insufficient.
**Decision:** Remove WellFound from automated scraping. Replace with
`manual_queue.json` — browse WellFound manually once per week, add
5-10 interesting companies to the file.
**Consequence:** Requires 10 minutes of manual work per week. Produces
higher quality targets than automated scraping because human judgment
is applied.
**Status:** Accepted

---

## D007: SQLite Over Any Other Database
**Date:** [DATE]
**Context:** Zero budget, no server, state must persist in a Git
repository (committed after each GitHub Actions run). SQLite is a
single file, requires zero setup, zero cost, and can be committed
to Git.
**Decision:** SQLite as sole database. File: `state.db`.
Backup before every run: `state.db.backup`.
**Consequence:** No concurrent writes (fine — single daily run).
File size grows linearly but at 5 emails/day, will take years to
reach any meaningful size.
**Status:** Accepted

---

## D008: Fallback Templates For Gemini Failure
**Date:** [DATE]
**Context:** Gemini free tier may change terms, have outages, or
rate-limit differently without notice. If email generation breaks,
the entire pipeline produces zero output for that day.
**Decision:** Maintain 3-4 hardcoded fallback templates in
`writer/fallback.py`. If Gemini fails, randomly select a template,
fill placeholders, and send. Log warning.
**Consequence:** Fallback emails are less personalized (no
company-specific reference from JD analysis). Still better than
zero emails.
**Status:** Accepted

---

## D009: One Follow-Up Maximum Per Contact
**Date:** [DATE]
**Context:** Follow-ups generate 40-60% of cold email replies. But
multiple follow-ups to the same person cross the line from persistence
to harassment, especially from a student seeking internships.
**Decision:** Exactly one follow-up per contact. Sent 4-5 business
days after initial email. Uses hardcoded template (no Gemini). Never
sent if bounced, opted out, or already replied.
**Consequence:** Leaves some potential replies on the table from a
hypothetical second follow-up. Acceptable — reputation protection
outweighs marginal reply gain.
**Status:** Accepted

---

## D010: GitHub Actions As Production Runtime
**Date:** [DATE]
**Context:** Zero budget means no VPS, no cloud server, no always-on
machine. GitHub Actions free tier provides 2000 minutes/month of
compute on Ubuntu runners with network access.
**Decision:** Use GitHub Actions as the sole production runtime.
Cron-triggered daily workflow.
**Consequence:** Gray area in GitHub TOS (intended for CI/CD, not
general automation). At our volume (~180 min/month), unlikely to
trigger enforcement. Fallback plan: Windows Task Scheduler on local
laptop if GitHub sends a warning.
**Status:** Accepted

---

## D011: SQLite Online Backup API Over shutil.copy2
**Date:** [TODAY]
**Context:** WAL mode keeps unflushed writes in a separate -wal 
file. shutil.copy2 only copies the main db file — backup would 
be incomplete or inconsistent.
**Decision:** Use sqlite3.Connection.backup() API for all 
database backups.
**Consequence:** Backup is always a consistent snapshot 
regardless of journal state.
**Status:** Accepted

---

## D012: Manual Queue Required Keys — company, domain, jd_summary
**Date:** [TODAY]
**Context:** Agent initially validated for title+company+url 
but manual entries are operator-added and don't always have 
a url. Domain is more useful than url for the finder waterfall.
**Decision:** Required keys = company, domain, jd_summary. 
url and title optional. job_id = SHA-256(url) if url exists 
else SHA-256(company+domain).
**Consequence:** Manual queue is simpler to fill in. 
Finder waterfall gets domain directly.
**Status:** Accepted

---

## D013: Role Match Context Window Tightened to ~100 chars
**Date:** 2026-03-27
**Context:** Initial implementation had overly large context 
window per name — a role keyword near a different person's 
name could be incorrectly associated. Also, first match was 
returned instead of globally highest priority role.
**Decision:** Tighten per-name context span to ~100 chars 
total. Scan all names first, collect all role matches, then 
return the highest priority result globally.
**Consequence:** More accurate role association on busy team 
pages with multiple people and role mentions.
**Status:** Accepted

---

## D014: Bounce Rate Circuit Breaker at 5% (FC-07)
**Date:** 2026-03-27
**Context:** Sending to bounced addresses damages Gmail 
sender reputation permanently. Need an automatic stop 
mechanism before reputation is impacted.
**Decision:** After each inbox check, calculate bounce 
rate over last 7 days. If > 5%, set bounce_rate_exceeded 
flag in stats dict. Sender checks flag before processing 
queue.
**Consequence:** Pipeline pauses automatically on high 
bounce rate. Requires manual investigation before resuming.
**Status:** Accepted

---

## D015: [skip ci] Tag on state.db Commits
**Date:** 2026-03-27
**Context:** GitHub Actions commits state.db back to repo 
after every run. Without [skip ci], that commit triggers 
another workflow run — infinite loop burning free minutes.
**Decision:** All state.db commits use message suffix 
[skip ci] to prevent re-triggering the workflow.
**Consequence:** State commits are invisible to CI. 
Correct behavior.
**Status:** Accepted

---

## D016: Enforce Runtime Dedupe Gates + Controlled Manual Retry Override
**Date:** 2026-03-31
**Context:** Pipeline orchestration depended on `jobs_seen` dedupe and did not explicitly enforce the 60-day contact block (`companies_contacted`) or 30-day finder retry block (`email_not_found`) before contact discovery/sending. This allowed policy drift risk and made manual recovery from prior finder misses operationally awkward.
**Decision:** In `main.py`, enforce `is_company_contacted(domain, 60)` and `is_email_not_found(domain, 30)` as runtime gates before finder/sender execution. Add controlled manual retry selection for manual queue entries already present in `jobs_seen`, with an explicit operator override `FORCE_MANUAL_RETRY=true` for one-off recovery runs.
**Consequence:** Contract policies are now consistently enforced in execution flow. Manual recovery is possible without schema changes, while unsafe bypass remains explicit and opt-in.
**Status:** Accepted

---

## D017: Block Default-Pattern Email Sends By Default
**Date:** 2026-03-31
**Context:** A permutation-derived `default_pattern` address (`sarah@wtfox.ai`) bounced with `550 5.1.1`, confirming high false-positive risk for unverified guessed emails.
**Decision:** Do not send contacts when finder confidence is `default_pattern` unless operator explicitly enables `ALLOW_DEFAULT_PATTERN_SEND=true`. Log such cases to `email_not_found` with reason `verification_failed`.
**Consequence:** Short-term send volume may drop, but bounce risk and sender reputation damage are significantly reduced. Recovery runs remain possible through explicit override.
**Status:** Accepted

---

## D018: Default Gemini Model Switched to gemini-2.5-flash
**Date:** 2026-03-31
**Context:** Runtime tests with the current API key show `gemini-2.0-flash` returns `429 ResourceExhausted` with free-tier quota limits at 0, while `gemini-2.5-flash` successfully serves generation requests.
**Decision:** Make model selectable via `GEMINI_MODEL` and set default to `gemini-2.5-flash` in writer code.
**Consequence:** Writer stays operational with current key settings while retaining a one-variable switch for future quota/model changes.
**Status:** Accepted

---

## D019: Prefer On-Page Email Signals Over Guessing
**Date:** 2026-03-31
**Context:** Real company pages often expose addresses through `mailto:` links or simple obfuscation (`[at]`, `[dot]`). Missing these signals lowers direct-find success and pushes the system toward risky guessed addresses.
**Decision:** Extend L1 finder extraction to include `mailto:` parsing from raw HTML and obfuscated email normalization before regex matching.
**Consequence:** Higher chance of obtaining direct evidence-based emails without relaxing bounce-protection policies.
**Status:** Accepted

---

## Template For New Decisions

## DXXX: [Title]
**Date:** [DATE]
**Context:** [What situation or problem prompted this decision]
**Decision:** [What was decided]
**Consequence:** [What tradeoffs this creates]
**Status:** Accepted | Superseded by DXXX | Rejected