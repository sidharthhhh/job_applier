"""
wellfound/config.py
Configuration for the Wellfound Job Application Automator.
Reads from the shared .env at the project root.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load shared root .env
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

def _bool(key: str, default: bool = True) -> bool:
    return os.getenv(key, str(default)).strip().lower() in ("true", "1", "yes")

def _int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

def _list(key: str, default: str = "") -> list[str]:
    raw = os.getenv(key, default).strip()
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else []


class WellfoundConfig:
    # ── Wellfound Credentials ────────────────────────────────────
    EMAIL    = os.getenv("WELLFOUND_EMAIL", "")
    PASSWORD = os.getenv("WELLFOUND_PASSWORD", "")

    # ── Job Search Settings ──────────────────────────────────────
    # Role slugs from wellfound.com/role/<slug>
    ROLE_SLUGS: list[str] = _list(
        "WELLFOUND_ROLE_SLUGS",
        "machine-learning-engineer,ai-engineer,data-scientist,"
        "python-developer,ml-engineer,generative-ai-engineer,"
        "ai-researcher,applied-scientist,llm-engineer"
    )
    # Optional location slug e.g. "india", "bengaluru", "remote"
    LOCATION_SLUG: str = os.getenv("WELLFOUND_LOCATION", "india")

    # ── Filters ──────────────────────────────────────────────────
    MAX_TARGET_EXPERIENCE: float = float(os.getenv("MAX_TARGET_EXPERIENCE", "3"))
    TARGET_ROLE_KEYWORDS: list[str] = _list(
        "TARGET_ROLE_KEYWORDS",
        "machine learning,ai,python,ml,data science,deep learning,"
        "nlp,mlops,generative ai,genai,llm,ai engineer,ml engineer"
    )

    # ── Pipeline Mode ────────────────────────────────────────────
    # true  = Full: scrape → filter → auto-apply + email → send
    # false = Backlog mode: skip scraping → apply to saved jobs in MongoDB → AI email
    SCRAPE_MODE: bool = _bool("WF_SCRAPE_MODE", True)

    # ── Auto-Apply Settings ──────────────────────────────────────
    # Whether to click the Apply button on Wellfound natively
    AUTO_APPLY: bool = _bool("WF_AUTO_APPLY", True)
    # Short intro note sent with native Wellfound applications
    APPLY_NOTE_MAX_WORDS: int = _int("WF_APPLY_NOTE_MAX_WORDS", 80)

    # ── Email (for jobs that expose recruiter email in description) ──
    SMTP_HOST    = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT    = _int("SMTP_PORT", 587)
    SMTP_EMAIL   = os.getenv("SMTP_EMAIL", "")
    SMTP_PASSWORD= os.getenv("SMTP_PASSWORD", "")

    YOUR_NAME      = os.getenv("YOUR_NAME", "Candidate")
    YOUR_ROLE      = os.getenv("YOUR_ROLE", "AI/ML Engineer")
    YOUR_SKILLS    = os.getenv("YOUR_SKILLS", "Python, ML, Deep Learning")
    YOUR_EXPERIENCE= os.getenv("YOUR_EXPERIENCE", "2.5+ years")
    YOUR_MOBILE    = os.getenv("YOUR_MOBILE", "")
    YOUR_LINKEDIN  = os.getenv("YOUR_LINKEDIN", "")
    YOUR_GITHUB    = os.getenv("YOUR_GITHUB", "")
    RESUME_PATH    = os.getenv("RESUME_PATH", "assets/Abhishek_Kumar.pdf")

    # ── Ollama ───────────────────────────────────────────────────
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "gemma3:12b")

    # ── MongoDB ──────────────────────────────────────────────────
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB  = os.getenv("MONGO_DB", "linkedin_scraper")  # shared DB
    # Wellfound uses separate collections
    WF_JOBS_COLLECTION    = "wf_scraped_jobs"
    WF_APPLIED_COLLECTION = "wf_applied_jobs"
    WF_EMAILS_COLLECTION  = "wf_extracted_emails"
    WF_SENT_COLLECTION    = "wf_sent_emails"

    # ── Safety Limits ────────────────────────────────────────────
    MAX_APPLIES_PER_DAY: int = _int("WF_MAX_APPLIES_PER_DAY", 40)
    APPLY_COOLDOWN_DAYS: int = _int("WF_APPLY_COOLDOWN_DAYS", 30)
    EMAIL_COOLDOWN_DAYS: int = _int("EMAIL_COOLDOWN_DAYS", 15)
    MAX_EMAILS_PER_DAY : int = _int("MAX_EMAILS_PER_DAY", 30)
    DELAY_BETWEEN_ACTIONS: int = _int("WF_DELAY_BETWEEN_ACTIONS", 4)  # seconds

    # ── Browser ──────────────────────────────────────────────────
    HEADLESS: bool = _bool("HEADLESS", True)

    @classmethod
    def display(cls):
        mode = "🟢 FULL PIPELINE (Scrape + Apply + Email)" if cls.SCRAPE_MODE else "🟡 BACKLOG MODE (Skip Scrape ➜ Apply to DB Jobs + Email)"
        print("=" * 55)
        print("📋 WELLFOUND CONFIGURATION")
        print("=" * 55)
        print(f"  Pipeline Mode    : {mode}")
        print(f"  Role Slugs       : {cls.ROLE_SLUGS[:3]}...")
        print(f"  Location         : {cls.LOCATION_SLUG}")
        print(f"  Auto Apply       : {'✅ Yes' if cls.AUTO_APPLY else '❌ No'}")
        print(f"  Ollama Model     : {cls.OLLAMA_MODEL}")
        print(f"  SMTP Email       : {cls.SMTP_EMAIL}")
        print(f"  MongoDB URI      : {cls.MONGO_URI}")
        print(f"  Your Role        : {cls.YOUR_ROLE}")
        print(f"  Target Max Exp   : <= {cls.MAX_TARGET_EXPERIENCE} years")
        print(f"  Max Applies/Day  : {cls.MAX_APPLIES_PER_DAY}")
        print(f"  Apply Cooldown   : {cls.APPLY_COOLDOWN_DAYS} days")
        print(f"  Resume           : {cls.RESUME_PATH}")
        print("=" * 55)

    @classmethod
    def validate(cls):
        errors = []
        if cls.SCRAPE_MODE:
            if not cls.EMAIL:
                errors.append("WELLFOUND_EMAIL is required")
            if not cls.PASSWORD:
                errors.append("WELLFOUND_PASSWORD is required")
        if not cls.SMTP_EMAIL:
            errors.append("SMTP_EMAIL is required")
        if not cls.SMTP_PASSWORD:
            errors.append("SMTP_PASSWORD is required")
        if errors:
            print("\n[Config] ❌ Missing required settings:")
            for e in errors:
                print(f"   • {e}")
            return False
        return True
