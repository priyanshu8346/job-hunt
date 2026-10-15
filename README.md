# 🎯 JobHunt: Automated Personal Job-Search Agent

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-138%20passing-brightgreen.svg)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero Scraping](https://img.shields.io/badge/scraping-zero%20%2F%20pure%20APIs-success.svg)](#supported-job-boards)
[![LLM Powered](https://img.shields.io/badge/LLM-Anthropic%20%7C%20Gemini%20%7C%20Groq%20%7C%20Ollama-orange.svg)](#supported-llm-providers)

**JobHunt** is an open-source, automated personal job-hunting engine. Every morning, it reads public career boards from companies you care about, filters out 99% of irrelevant postings for **zero cost**, scores matching roles against your real resume with an LLM, drafts customized application kits for the top few, and emails you a clean HTML digest.

> **It never auto-submits applications.** It finds, filters, ranks, and drafts. You inspect the digest, polish the cover note, and click submit yourself.

---

## 🏗️ How It Works: The Cost-Guarded Funnel

Job boards receive thousands of postings every week. Blasting entire career feeds into LLM prompts is slow, fragile, and expensive. JobHunt uses a deterministic three-stage funnel:

```text
  [2,500+ Raw Postings]  (Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable,
                          Recruitee, Personio, Teamtailor, Pinpoint, Breezy HR, Jobvite)
            │
            ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Stage 1: Deterministic Pre-Filter (0 Tokens / ₹0 / $0)  │
  │  • Regex Title Match & Exclusions (SDE, Frontend, etc.) │
  │  • Seniority Gate (Drop Senior/Staff/Interns early)     │
  │  • Location & Scoped Remote Enforcer (India / APAC / WW)│
  │  • Freshness / Age Gate (Discard stale re-postings)     │
  └─────────────────────────────────────────────────────────┘
            │  (Eliminates ~99% of noise before LLM calls)
            ▼
  [~20-40 Qualified Candidates]
            │
            ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Stage 2: LLM Resume Screening (Fast & Cheap)           │
  │  Evaluates candidates against your actual resume skills │
  │  Assigns a 1–10 fit score + structured reasoning        │
  └─────────────────────────────────────────────────────────┘
            │  (Keeps score >= 7.0, max 5 per run)
            ▼
  [Top Matched Roles]
            │
            ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Stage 3: LLM Application Kit Drafting                  │
  │  • Fit summary & gap analysis                           │
  │  • Tailored bullet points highlighting relevant work    │
  │  • Customized cover note ready to send                  │
  │  • High-signal questions to ask the interviewer         │
  └─────────────────────────────────────────────────────────┘
            │
            ▼
  [📬 Daily HTML Email Digest] + [📊 Spreadsheet Tracker (out/tracker.csv)]
```

---

## ✨ Key Features

- **No Scraping & No Bot Detection**: Ingests official, public JSON, XML, and RSS feeds published by ATS platforms. No headless browsers, no Puppeteer/Selenium, no CAPTCHAs, no risk of account bans.
- **12 Supported ATS Platforms**: Native support for Greenhouse, Lever, Ashby, Workday, SmartRecruiters, Workable, Recruitee, Personio, Teamtailor, Pinpoint, Breezy HR, and Jobvite.
- **Zero Cost Pre-Filtering**: The deterministic prefilter weeds out wrong seniorities, wrong disciplines, stale jobs, and region-locked roles without spending a single LLM token.
- **Smart Remote Scope**: Rejects US-only or EU-only "remote" roles unless they explicitly match worldwide, APAC, or your specified target geography.
- **Multi-Provider LLM Flexibility**: Use Anthropic Claude (Haiku / Sonnet), Google Gemini (Flash / Pro), Groq (Llama), any OpenAI-compatible provider (OpenRouter, Together, vLLM), or 100% offline with local Ollama.
- **Automated Scheduling**: Ready-to-go GitHub Actions workflow (runs free in the cloud) or a native macOS LaunchAgent (runs locally at 08:00 AM).
- **Application Tracker**: Deduplicates seen jobs so you are never shown the same role twice. Track applied jobs and export to CSV with built-in CLI commands.

---

## ⚡ 30-Second Quickstart (Zero API Keys Required)

You can run the entire pipeline immediately using bundled test fixtures and an offline keyword scorer:

```bash
git clone https://github.com/priyanshu8346/job-hunt.git
cd job-hunt

# Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run offline mock pipeline
python -m jobhunt run --mock --scorer keyword
```

You will see:
```text
[1/5] fetching boards
  [mock] 12 postings from 4 boards
[2/5] filtering
  prefilter: 12 -> 5 (dropped title=5 location=1 stale=1)
[3/5] screening 5 jobs (keyword stub — DEV ONLY)
  3 scored >= 7.0
[5/5] digest
  wrote out/digest.html
funnel: 12 scanned -> 5 passed filters -> 5 new -> 3 in digest
```
Open `out/digest.html` in your browser to inspect the sample email digest.

---

## 🏢 Supported Job Boards

JobHunt reads public career boards without authentication. Add companies to `companies.yaml` using their board type and identifier:

| ATS Platform | `ats` key | Where to find `slug` | Example `companies.yaml` entry |
|---|---|---|---|
| **Greenhouse** | `greenhouse` | `boards.greenhouse.io/<slug>` | `{ats: greenhouse, slug: stripe, name: Stripe}` |
| **Lever** | `lever` | `jobs.lever.co/<slug>` | `{ats: lever, slug: cred, name: CRED}` |
| **Ashby** | `ashby` | `jobs.ashbyhq.com/<slug>` | `{ats: ashby, slug: plane, name: Plane}` |
| **Workday** | `workday` | Full HTTPS career site URL | `{ats: workday, slug: 'https://postman.wd108.myworkdayjobs.com/en-US/careers', name: Postman}` |
| **SmartRecruiters** | `smartrecruiters` | `careers.smartrecruiters.com/<slug>` | `{ats: smartrecruiters, slug: Freshworks, name: Freshworks}` |
| **Workable** | `workable` | `apply.workable.com/<slug>` | `{ats: workable, slug: wati-dot-i-o, name: WATI}` |
| **Recruitee** | `recruitee` | `<slug>.recruitee.com` | `{ats: recruitee, slug: transperfect, name: TransPerfect}` |
| **Personio** | `personio` | `<slug>.jobs.personio.de` or `.com` | `{ats: personio, slug: cuculus-gmbh, name: Cuculus}` |
| **Teamtailor** | `teamtailor` | `<slug>.teamtailor.com` | `{ats: teamtailor, slug: cartrackasiacareerpage, name: Cartrack}` |
| **Pinpoint** | `pinpoint` | `<slug>.pinpointhq.com` | `{ats: pinpoint, slug: sunking, name: Sun King}` |
| **Breezy HR** | `breezy` | `<slug>.breezy.hr` | `{ats: breezy, slug: codebase, name: Codebase}` |
| **Jobvite** | `jobvite` | `jobs.jobvite.com/<slug>` | `{ats: jobvite, slug: alivecor, name: AliveCor}` |

> **Coverage Note**: Closed platforms without public feeds (e.g. LinkedIn, Indeed, Naukri, Wellfound, Instahyre) require private employee credentials or violate ToS, and are deliberately excluded.

---

## 🚀 Setup Guide

### 1. Configure Target Companies (`companies.yaml`)

Edit [`companies.yaml`](companies.yaml) with companies you want to monitor:

```yaml
companies:
  - {ats: ashby, slug: plane, name: Plane}
  - {ats: workday, slug: 'https://postman.wd108.myworkdayjobs.com/en-US/careers', name: Postman}
  - {ats: smartrecruiters, slug: Freshworks, name: Freshworks}
  - {ats: lever, slug: cred, name: CRED}
  - {ats: greenhouse, slug: capco, name: Capco}
```

### 2. Configure Filters (`config.yaml`)

Tune the prefilter in [`config.yaml`](config.yaml) to match your desired titles, locations, and experience:

```yaml
filters:
  include_titles:
    - \b(software|frontend|backend|fullstack|web)\b.*\b(engineer|developer)\b
    - \bsde\b
  exclude_titles:
    - \b(senior|sr\.?|staff|principal|lead|architect)\b    # drop senior roles
    - \b(intern|internship|trainee)\b                      # drop junior roles
    - \b(sales|marketing|recruiter|support)\b              # drop other functions
  locations:
    - india
    - bangalore
    - bengaluru
    - hyderabad
    - pune
    - mumbai
    - delhi
  allow_remote: true
  remote_locations:
    - worldwide
    - global
    - anywhere
    - apac
    - asia pacific
    - asia-pacific
  max_age_days: 30

# LLM thresholds
score_threshold: 7.0       # Minimum score (out of 10) to draft an application kit
max_per_digest: 5          # Cap on daily email inclusions to prevent token spend
```

### 3. Generate Your Profile (`profile.json`)

Copy `.env.example` to `.env` and add your LLM API key:

```bash
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY, GEMINI_API_KEY, or GROQ_API_KEY
```

Generate your structured profile directly from your resume:

```bash
python -m jobhunt profile --resume path/to/your_resume.pdf
```
*(Supports `.pdf`, `.txt`, and `.md` formats)*. This creates `profile.json` (automatically gitignored). Review and adjust any extracted details.

### 4. Run the Pipeline

```bash
# Build the digest and view terminal summary
python -m jobhunt run

# Generate and send the HTML digest directly via email
python -m jobhunt run --send

# Cost guard during testing (process only first 10 matching jobs)
python -m jobhunt run --limit 10

# Screen only, skip drafting kits
python -m jobhunt run --no-draft
```

---

## 🤖 Supported LLM Providers

JobHunt supports separate models for screening (hundreds of jobs → fast/cheap) and drafting (top 5 jobs → high capability):

```bash
# In your .env:
LLM_PROVIDER=gemini             # default provider for both stages
SCREEN_PROVIDER=groq           # optional: override screening stage
DRAFT_PROVIDER=anthropic       # optional: override drafting stage
SCREEN_MODEL=llama-3.3-70b-versatile
DRAFT_MODEL=claude-sonnet-4-5
```

| Provider | Provider Setting | Required Key | Resume PDF Support | Notes |
|---|---|---|---|---|
| **Google Gemini** | `gemini` | `GEMINI_API_KEY` | Yes | Fast, generous free tier |
| **Anthropic** | `anthropic` | `ANTHROPIC_API_KEY` | Yes | Top tier drafting quality |
| **Groq** | `groq` | `GROQ_API_KEY` | No (converts to text) | Extremely fast Llama inference |
| **OpenAI / Compatible** | `openai-compatible` | `GROQ_API_KEY` + `LLM_BASE_URL` | No | Together, OpenRouter, vLLM |
| **Ollama** | `ollama` | None | No | 100% local and offline (`OLLAMA_HOST`) |

---

## ⏰ Automated Daily Scheduling

### Option A: Local macOS LaunchAgent (Recommended for Mac)

Runs every morning at **08:00 AM** in your local timezone without needing a terminal open:

```bash
# Run one-line setup
./scripts/setup_daily.sh

# Check status anytime
launchctl print gui/$(id -u)/com.jobhunt.daily

# Run manual trigger
launchctl kickstart gui/$(id -u)/com.jobhunt.daily
```
*(See [DAILY_RUN.md](DAILY_RUN.md) for logs, rotation, and troubleshooting)*.

### Option B: GitHub Actions (Free in the Cloud)

Use the built-in [`.github/workflows/daily.yml`](.github/workflows/daily.yml) to run on weekday mornings. `seen.json` is preserved across runs using GitHub cache so you never receive duplicate emails.

Add the following repository secrets (**Settings → Secrets and variables → Actions**):
- `PROFILE_JSON`: Contents of your `profile.json`
- `GEMINI_API_KEY` or `ANTHROPIC_API_KEY`
- `SMTP_USER` & `SMTP_PASS`: Gmail address + [Google App Password](https://myaccount.google.com/apppasswords)
- `MAIL_TO`: Destination email address

---

## 📊 Application Tracking & History

`seen.json` records every job seen so you never get duplicates. Built-in CLI commands let you manage your pipeline:

```bash
# Mark a job as applied (job_id is listed in every digest)
python -m jobhunt applied "workday:postman:careers:JR1000052"

# View status summary and update out/tracker.csv
python -m jobhunt stats
```

Exported tracker CSVs (`out/tracker.csv`) can be opened directly in Excel, Google Sheets, or Numbers.

---

## 🧪 Running Tests

The test suite runs completely offline with mock fixtures and zero network requests:

```bash
PYTHONPATH=. pytest
```
```text
============================= 138 passed in 0.12s ==============================
```

Tests verify:
- All 12 ATS parsers against native JSON/XML/RSS payloads
- HTML entity unescaping, block tags, and formatting cleanup
- Prefilter title regexes, discipline matching, seniority gates, and regional remote limits
- Epoch millisecond normalization and ISO date parsing
- LLM response parsing (JSON markdown blocks, reasoning preamble, malformed array handling)

---

## 🔒 Security & Privacy

- **Never Commits Personal Data**: `.env`, `seen.json`, `profile.json`, `resume.*`, and generated files in `out/` are strictly ignored by `.gitignore`.
- **Zero Credentials in Plists**: The scheduler scripts and templates contain no passwords or API tokens.
- **Safe Transports**: Uses timeouts, user-agent headers, and payload validation across all network calls.

---

## 📄 License

Distributed under the [MIT License](LICENSE). Contributions, bug reports, and new ATS adapters are welcome!
