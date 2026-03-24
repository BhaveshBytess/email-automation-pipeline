# agent_project.md — Cold Email Pipeline Agent Manual

## 1. System Context

This project is an **Automated Cold Email Pipeline** for internship/job outreach.

It discovers relevant job postings, identifies technical decision-makers
(CTOs, VPs of Engineering — NOT HR), finds their email addresses,
generates personalized cold emails, and sends them automatically
via Gmail SMTP while the operator sleeps.

This system is a **personal job-hunting tool**, not a SaaS product.
It runs once daily via GitHub Actions. It serves one user.

---

## 2. Constraints (Non-Negotiable)

### 2.1 Budget
- **Zero rupees.** Every tool, API, and service must be free forever.
- No free trials that expire. No "free for 30 days." Permanent free tier only.

### 2.2 Hardware
- GitHub Actions free tier is the production runtime (~2000 min/month).
- Local development on 8GB RAM, GTX 1650 Ti, i5 laptop.
- No local models larger than 100MB.

### 2.3 APIs & Services
- **Gemini Pro** — Free tier (1500 req/day). Used for email generation only.
- **Gmail SMTP** — Via App Password. NOT Gmail API OAuth2.
- **Gmail IMAP** — Via same App Password. For reply/bounce tracking.
- **GitHub API** — Authenticated free tier. For contributor email discovery.
- **DuckDuckGo** — For search queries. NOT Google (blocks bots harder).
- **Gravatar** — MD5 hash lookup for email verification.

### 2.4 Sending Rules
- Dedicated outreach Gmail account. NEVER the primary personal email.
- Warmup schedule: Week 1-2: 1/day, Week 3-4: 2/day, Week 5-6: 3/day, Week 7+: 5/day.
- No sends on Saturday or Sunday.
- Plain text only. No HTML. No attachments. No images.
- Every email includes an unsubscribe line:
  `P.S. Not relevant? Reply "stop" and I'll make sure you never hear from me again.`
- Maximum 1 follow-up per person, 4-5 business days after initial email.
- Never follow up on bounced or opted-out contacts.

---

## 3. Tech Stack (Strict)

| Component        | Technology                        | Why                              |
|------------------|-----------------------------------|----------------------------------|
| Language         | Python 3.10+                      | Only language needed             |
| Database         | SQLite (state.db)                 | Zero setup, file-based, portable |
| Email sending    | smtplib + App Password            | No token expiry, no OAuth        |
| Reply tracking   | imaplib + App Password            | Same credentials as sender       |
| Job ranking      | all-MiniLM-L6-v2 (80MB, CPU)     | Semantic similarity, small model |
| NER              | spaCy en_core_web_sm (12MB)       | Name extraction from web pages   |
| Email generation | Gemini Pro API (free tier)        | Best free LLM API available      |
| Scraping         | requests + BeautifulSoup          | Lightweight, no browser needed   |
| Browser scraping | Playwright (only where required)  | JS-rendered pages only           |
| Scheduler        | GitHub Actions cron               | Free server, runs daily          |
| Dashboard        | Google Sheets (via gspread)       | Free, visual, shareable          |

**Do NOT introduce:** Redis, PostgreSQL, Docker, FastAPI, Flask, Celery,
any paid API, any npm package, any frontend framework.

---

## 4. What This System Is NOT

- NOT a SaaS product. No multi-user support. No auth. No admin panel.
- NOT a web scraper project. Scraping is a means, not the goal.
- NOT a mass email blaster. Maximum 5 emails per day. Quality over quantity.
- NOT a research project. Ship working code, not notebooks.
- NOT LinkedIn automation. No LinkedIn scraping. No browser automation on LinkedIn.

---

## 5. Domain Rules

### 5.1 Targeting
- Target: CTOs, Technical Co-founders, VP/Head of Engineering, Tech Leads.
- Never target: HR, recruiters, "People Operations," office managers.
- Company types: Startups and small companies (under ~200 employees).
- Sources: Job boards, YC company lists, manual additions.

### 5.2 Email Content
- Max 150 words per email.
- Must reference one specific thing about the company.
- Must reference one specific project from the operator's resume.
- No buzzwords. No "I'm passionate about..." No "synergy."
- Tone: Direct, competent, human. Like a peer reaching out, not a student begging.

### 5.3 Data Discipline
- All timestamps in UTC. Timezone is a display concern only.
- No duplicate contacts within 60 days.
- No retry on email_not_found within 30 days.
- Every sent email is logged with full body, subject variant, and metadata.
- Every reply is logged with classification (positive/neutral/negative/opted_out/bounce).

### 5.4 Safety
- If bounce rate exceeds 5% over any 7-day window, pause sending and alert.
- If Gemini API fails, fall back to hardcoded templates. Never skip sending.
- If scraper returns zero results, process manual_queue.json only.
- Daily summary email sent to primary Gmail after every run. No exceptions.

---

## 6. Resume Context (Hardcoded Reference)

The operator is a B.Tech Computer Science student (6th semester) at IIIT Kota.
Focus areas: AI/ML and backend development.

Resume highlights (used by email writer):
1. Built a temporal GNN (TRDGNN) achieving 0.58 PR-AUC on a 203K-node 
   fraud detection graph with strict zero-leakage temporal constraints 
   and 100% test coverage — PyTorch Geometric, XGBoost.
2. Engineered a PDF-to-JSON extraction pipeline with 100% JSON validity 
   and 81% evidence precision using LLMs, Pydantic validation, and 
   multi-backend API integration (Gemma, DeepSeek) — Python, Streamlit.
3. Optimized GNN architecture 10x parameter reduction (500K → 50K) 
   with +108% performance gain — production deployment on 
   resource-constrained systems.
4. Python, PyTorch, PyTorch Geometric, TensorFlow, scikit-learn, 
   Docker, Git, Linux, Streamlit, Pydantic, NumPy, Pandas.
5. CS undergrad at IIIT Kota specializing in GNNs and unstructured 
   data pipelines — building production-ready ML systems with clean 
   engineering principles, full test coverage, and reproducible research.

These bullets are injected into the Gemini prompt. Update them here when
the resume changes. This is the single source of truth for self-description.

---

## 7. GitHub Actions Constraints

- Free tier: 2000 minutes/month.
- Target usage: ~180 minutes/month (22 weekday runs × ~8 min each).
- Every workflow MUST use dependency caching.
- Random jitter (0-45 min) on cron start to avoid pattern detection.
- state.db committed back to repo after every run.
- state.db.backup created before every run.
- Weekend runs are skipped (exit 0 immediately).