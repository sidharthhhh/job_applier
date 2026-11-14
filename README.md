# 🚀 Autonomous AI Job Application & Cold Email Suite

An intelligent, multi-platform job application and recruitment outreach automation suite powered by **Local LLMs (Ollama)**, **Playwright**, and **MongoDB**. 

It automates the entire application lifecycle across **LinkedIn** and **Wellfound (AngelList)**:
1. **Scraping**: Collects posts and job listings with anti-bot evasion.
2. **Filtering**: Matches candidate keywords and enforces strict experience limits ($\le 3.0$ years).
3. **Wellfound Native Auto-Apply**: Completes application modals with real-time AI-tailored intro pitches.
4. **Email Extraction**: Discovers recruiter email addresses hidden inside job descriptions.
5. **DNS & MX Verification**: Validates recipient mail servers in real time to prevent bounces.
6. **Local AI Email Generation**: Crafts spam-free (Score: 0), personalized emails via Ollama (`gemma3:27b`, `gpt-oss:20b`).
7. **SMTP Dispatch**: Sends personalized emails with attached PDF resumes and human-like delays.
8. **Deduplication & Cooldown**: MongoDB tracks all past applications and emails to prevent duplicate outreach.

---

## 📌 Architecture & Pipeline Flow

```
                                      ┌────────────────────────┐
                                      │   Target Search Query  │
                                      │   or Role Slugs (WF)   │
                                      └───────────┬────────────┘
                                                  │
                 ┌────────────────────────────────┴───────────────────────────────┐
                 │                                                                │
                 ▼                                                                ▼
      [ LinkedIn Pipeline ]                                            [ Wellfound Pipeline ]
     Scrapes recruiter posts                                          Extracts Apollo GraphQL Cache
     via Playwright session                                           from Next.js (__NEXT_DATA__)
                 │                                                                │
                 └────────────────────────────────┬───────────────────────────────┘
                                                  │
                                                  ▼
                                      ┌────────────────────────┐
                                      │   Relevance Filter     │
                                      │  Keywords + Max Exp    │
                                      └───────────┬────────────┘
                                                  │
                         ┌────────────────────────┴───────────────────────┐
                         │                                                │
                         ▼                                                ▼
              [ Recruiter Emails Found ]                        [ Native Wellfound Apply ]
                         │                                                │
                         ▼                                                ▼
              ┌──────────────────────┐                        ┌──────────────────────┐
              │  DNS MX Verification │                        │ Playwright AI Modal  │
              └──────────┬───────────┘                        │ Submission (JS Click)│
                         │                                    └──────────┬───────────┘
                         ▼                                               │
              ┌──────────────────────┐                                   │
              │  Ollama (LLM) Email  │                                   │
              │  Generation & Spam=0 │                                   │
              └──────────┬───────────┘                                   │
                         │                                               │
                         ▼                                               │
              ┌──────────────────────┐                                   │
              │  SMTP Send + Resume  │                                   │
              └──────────┬───────────┘                                   │
                         │                                               │
                         └────────────────────────┬──────────────────────┘
                                                  │
                                                  ▼
                                      ┌────────────────────────┐
                                      │    MongoDB Storage     │
                                      │  Cooldown: 15–30 Days  │
                                      └────────────────────────┘
```

---

## ✨ Key Highlights

- **Dual Platform Engine**:
  - **LinkedIn Automator**: Scrapes posts under relevant hashtags/queries, extracts recruiter emails, filters non-technical contacts, and handles cold email outreach.
  - **Wellfound Automator**: Accesses live startup listings via Next.js Apollo cache state, clicks native "Apply" buttons, crafts contextual AI intro notes, and submits applications automatically.
- **Local AI (Zero API Cost & Privacy)**: Runs entirely locally or over a private network with Ollama models (`gemma3:27b`, `gpt-oss:20b`, `llama3`).
- **Anti-Spam Verification**:
  - Enforces professional tone guidelines and strips trigger buzzwords.
  - Automatically structures emails as RFC-compliant `multipart/mixed` and `multipart/alternative` with both plain text and clean HTML.
- **Deliverability Protection**: Checks MX records before sending to protect sender domain reputation and prevent bounces.
- **Flexible Pipeline Modes**: Toggle between full web scraping or processing stored backlogs with a single flag in `.env`.

---

## 📂 Project Structure

```
├── main.py                     # LinkedIn automation entry point
├── config.py                   # Central configuration & .env loader
├── requirements.txt            # Python dependencies
├── .env.example                # Sample environment configuration template
├── .gitignore                  # Production-grade git ignore (protects cookies, PDFs, .env)
│
├── wellfound/                  # Wellfound (AngelList) subsystem
│   ├── main.py                 # Wellfound automation entry point
│   ├── config.py               # Wellfound-specific settings & limits
│   ├── database/
│   │   └── mongo_handler.py    # Wellfound collections handler (wf_*)
│   ├── scraper/
│   │   ├── job_scraper.py      # Apollo GraphQL cache extraction
│   │   └── auto_apply.py       # JS-based React modal apply automation
│   ├── session/
│   │   ├── session_manager.py  # Session restoration & stealth context
│   │   └── wf_cookies.json     # Saved session cookies (gitignored)
│   └── tools/
│       ├── save_session.py     # One-time interactive manual login tool
│       └── debug_scraper.py    # Diagnostic script for inspection
│
├── scraper/                    # LinkedIn scraping subsystem
│   ├── linkedin_scraper.py     # Feed parser & continuous scroll engine
│   ├── email_extractor.py      # Regex & heuristic email parser
│   └── session_manager.py      # LinkedIn cookies & browser context
│
├── ai/                         # LLM integration
│   ├── ollama_handler.py       # Ollama API client & spam scoring engine
│   └── relevance_filter.py     # Regex & keyword candidate matching
│
├── mailer/                     # Email sending subsystem
│   ├── smtp_handler.py         # Multi-part MIME SMTP mailer with PDF attachment
│   └── email_verifier.py       # Syntax, disposable email, and DNS MX verifier
│
├── database/                   # Shared MongoDB operations
│   └── mongo_handler.py        # LinkedIn database handler (deduplication & cooldown)
│
└── assets/                     # Resumes and documents
    └── README.txt              # Place your PDF resume here (e.g., resume.pdf)
```

---

## 🛠️ Prerequisites

1. **Python 3.10+**
2. **MongoDB**: Running locally at `mongodb://localhost:27017` or via MongoDB Atlas.
3. **Ollama**: Installed and running locally or on a remote GPU server with a supported model:
   ```bash
   ollama pull gemma3:27b
   # or
   ollama pull gpt-oss:20b
   ```
4. **Gmail Account & App Password**:
   - Generate a 16-character App Password at [Google App Passwords](https://myaccount.google.com/apppasswords).

---

## ⚡ Quickstart

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/abhish12345/job_applier.git
cd job_applier

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser binaries
playwright install chromium
```

### 2. Configure Environment Variables

Copy the example file and update it with your credentials:

```bash
copy .env.example .env     # On Windows
cp .env.example .env       # On Linux/macOS
```

Key settings in `.env`:

```env
# ─── YOUR PROFILE ─────────────────────────────────────────
YOUR_NAME=Your Full Name
YOUR_ROLE=AI/ML Engineer
YOUR_SKILLS=Python, Machine Learning, Deep Learning, NLP, Generative AI, LLMs, RAG, PyTorch
YOUR_EXPERIENCE=2.5+ years
MAX_TARGET_EXPERIENCE=3

YOUR_MOBILE=+91-XXXXXXXXXX
YOUR_LINKEDIN=https://www.linkedin.com/in/your-profile/
YOUR_GITHUB=https://github.com/your-username
RESUME_PATH=assets/resume.pdf

# ─── OLLAMA CONFIGURATION ─────────────────────────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3:27b

# ─── SMTP CONFIGURATION ───────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your_email@gmail.com
SMTP_PASSWORD=your_16_digit_app_password

# ─── WELLFOUND SETTINGS ───────────────────────────────────
WELLFOUND_EMAIL=your_email@gmail.com
WELLFOUND_PASSWORD=your_password
WF_SCRAPE_MODE=false            # true = scrape fresh jobs, false = apply from DB backlog
WF_AUTO_APPLY=true              # Automatically submit Wellfound modal applications
WF_MAX_APPLIES_PER_DAY=40
```

### 3. Add Your Resume

Place your resume PDF in the `assets/` directory:
```
assets/resume.pdf
```
Ensure `RESUME_PATH` in `.env` points to this file.

---

## 🔑 One-Time Authentication Setup

Both platforms store session cookies locally so that future runs operate headlessly without prompting for login.

### LinkedIn Session Setup
1. Run the LinkedIn pipeline once:
   ```bash
   python main.py
   ```
2. If no saved cookies are found, Playwright will open a browser window for you to log in. Once logged in, cookies will be saved to `session/cookies.json`.

### Wellfound Session Setup
Run the dedicated session saver tool:
```bash
python wellfound\tools\save_session.py
```
A browser window will launch. Log in to Wellfound, navigate to the job feed, and press `ENTER` in your terminal. Cookies will be saved to `wellfound/session/wf_cookies.json`.

---

## 🚀 Daily Usage

### Running the LinkedIn Pipeline

```bash
python main.py
```

- **Full Pipeline (`SCRAPE_MODE=true`)**: Scrapes LinkedIn for posts matching your keywords, extracts emails, filters relevance, verifies MX records, generates personalized AI emails, and sends them via SMTP.
- **Backlog Mode (`SCRAPE_MODE=false`)**: Skips browser scraping and directly generates/sends emails for un-contacted leads saved in MongoDB.

### Running the Wellfound Pipeline

```bash
python wellfound\main.py
```

- **Scrape & Auto-Apply (`WF_SCRAPE_MODE=true`)**: Scrapes target role listings (`ai-engineer`, `machine-learning-engineer`, etc.) via Wellfound's Apollo cache, saves them to MongoDB, applies to eligible listings, and emails recruiters.
- **Backlog Apply (`WF_SCRAPE_MODE=false`)**: Skips the web scrape, loads the remaining unapplied jobs from MongoDB, and applies to the next daily batch (e.g., 40 applications/day) with custom AI intro pitches.

---

## ⚙️ Configuration Reference (`.env`)

| Variable | Description | Default |
|---|---|---|
| `SCRAPE_MODE` | LinkedIn mode toggle (`true` = full scrape, `false` = DB backlog) | `true` |
| `WF_SCRAPE_MODE` | Wellfound mode toggle (`true` = scrape, `false` = DB backlog apply) | `false` |
| `WF_AUTO_APPLY` | Enable native 1-click Wellfound application submission | `true` |
| `MAX_TARGET_EXPERIENCE` | Max allowed years of experience required by job | `3` |
| `TARGET_ROLE_KEYWORDS` | Comma-separated list of keywords to match jobs against | AI/ML keywords |
| `EMAIL_COOLDOWN_DAYS` | Cooldown period before allowing re-emailing the same address | `15` |
| `WF_APPLY_COOLDOWN_DAYS` | Cooldown period before re-applying to the same company | `30` |
| `MAX_EMAILS_PER_DAY` | Safety cap for outbound cold emails per run | `30` |
| `WF_MAX_APPLIES_PER_DAY` | Safety cap for native Wellfound applications per run | `40` |
| `DELAY_BETWEEN_EMAILS` | Humanized pause between emails in seconds | `60` |
| `WF_DELAY_BETWEEN_ACTIONS` | Humanized pause between Wellfound applies in seconds | `4` |
| `HEADLESS` | Run Playwright browser in background (`true`) or visible (`false`) | `true` |

---

## 🛡️ Anti-Detection & Reliability Features

1. **React Modal Overlay Bypass**: Wellfound's React modal overlays intercept standard pointer clicks. The automator dispatches native JavaScript events (`MouseEvent`, `dispatchEvent`) directly to bypass overlays.
2. **React Controlled Input State**: AI-generated intro pitches are injected via native prototype setters (`HTMLTextAreaElement.prototype.value`) alongside `input` and `change` events so React state synchronizes accurately.
3. **Apollo Cache Extraction**: Scrapes Wellfound's embedded `__NEXT_DATA__` JSON directly, bypassing DOM parsing instability and dynamic CSS obfuscation.
4. **Stealth Browser Context**: Automatically removes `navigator.webdriver`, configures realistic plugins, viewports, and locale headers.

---

## 🔒 Security & Privacy

- **All AI processing is local** via Ollama. No candidate data, post content, or recruiter details are shared with third-party LLM APIs.
- `.env`, session cookie files (`*cookies.json`), candidate PDFs (`assets/*.pdf`), and scraper debug logs are strictly excluded via `.gitignore`.
- Always review and adhere to the Terms of Service of respective platforms and relevant email communication laws (e.g., CAN-SPAM, GDPR).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
