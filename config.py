"""
config.py - Central & multi-profile configuration loader.
Loads shared infrastructure keys from root .env and optional per-user overrides
from profiles/<name>/profile.env (via --profile <name> or PROFILE env var).
"""

import os
from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_ENV_PATH = os.path.join(BASE_DIR, ".env")
PROFILES_DIR = os.path.join(BASE_DIR, "profiles")

# Snapshot shell-exported env vars before reading .env files so shell overrides still win
_INITIAL_SHELL_ENV = dict(os.environ)


def list_available_profiles() -> list[str]:
    """Return profile names found under profiles/ (excluding _template)."""
    if not os.path.isdir(PROFILES_DIR):
        return []
    profiles = []
    for entry in sorted(os.listdir(PROFILES_DIR)):
        if entry.startswith("_"):
            continue
        env_file = os.path.join(PROFILES_DIR, entry, "profile.env")
        if os.path.isfile(env_file):
            profiles.append(entry)
    return profiles


class Config:
    # Date filter map for LinkedIn URL param
    SCRAPE_DAYS_TO_LINKEDIN_FILTER: dict = {
        7: "past-week",
        14: "past-2-weeks",
        30: "past-month",
    }

    PROFILE_NAME: str = "default"
    LINKEDIN_SEARCH_QUERIES: list[str] = []
    LINKEDIN_HASHTAGS: list[str] = []
    LINKEDIN_SCRAPE_DAYS: int = 7
    MAX_POSTS_PER_SEARCH: int = 50
    SCROLL_PAUSE_TIME: float = 3.0
    HEADLESS: bool = False

    YOUR_NAME: str = "Candidate"
    YOUR_ROLE: str = "Software / Tech Professional"
    YOUR_SKILLS: str = ""
    YOUR_EXPERIENCE: str = "2 years"
    YOUR_EDUCATION: str = ""
    YOUR_LOCATION: str = ""
    YOUR_VALUE_PROPOSITION: str = ""
    MAX_TARGET_EXPERIENCE: float = 3.0
    TARGET_ROLE_KEYWORDS: list[str] = []
    EXCLUDE_TITLE_KEYWORDS: list[str] = []
    PROFILE_ACRONYMS: list[str] = []
    YOUR_MOBILE: str = ""
    YOUR_LINKEDIN: str = ""
    YOUR_GITHUB: str = ""
    YOUR_PORTFOLIO: str = ""
    RESUME_PATH: str = "assets/resume.pdf"

    AI_PROVIDER: str = "bedrock"
    AI_FALLBACK_PROVIDER: str = "gemini"
    AWS_BEDROCK_REGION: str = "us-east-1"
    AWS_BEARER_TOKEN_BEDROCK: str = ""
    BEDROCK_MODEL_ID: str = "us.amazon.nova-lite-v1:0"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "gemma"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_EMAIL: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_SUBJECT_PREFIX: str = "Application for"

    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB: str = "linkedin_scraper"
    MONGO_POSTS_COLLECTION: str = "scraped_posts"
    MONGO_EMAILS_COLLECTION: str = "extracted_emails"
    MONGO_SENT_COLLECTION: str = "sent_emails"
    MONGO_RESPONSES_COLLECTION: str = "email_responses"

    EMAIL_COOLDOWN_DAYS: int = 15
    MAX_EMAILS_PER_DAY: int = 30
    DELAY_BETWEEN_EMAILS: int = 60
    SKIP_PERSONAL_EMAILS: bool = False
    SCRAPE_MODE: bool = True
    DRY_RUN: bool = False

    @classmethod
    def load(cls, profile: str | None = None):
        """Load configuration from root .env and optional profiles/<profile>/profile.env."""
        requested = (profile or _INITIAL_SHELL_ENV.get("PROFILE") or "default").strip().lower()
        root_vals = {k: (v or "") for k, v in dotenv_values(ROOT_ENV_PATH).items()} if os.path.isfile(ROOT_ENV_PATH) else {}

        profile_vals: dict[str, str] = {}
        if requested and requested != "default":
            profile_env_path = os.path.join(PROFILES_DIR, requested, "profile.env")
            if not os.path.isfile(profile_env_path):
                avail = ", ".join(list_available_profiles()) or "(none)"
                raise ValueError(
                    f"[CONFIG ERROR] Profile '{requested}' not found at: {profile_env_path}\n"
                    f"Available profiles: {avail}"
                )
            profile_vals = {k: (v or "") for k, v in dotenv_values(profile_env_path).items()}

        env = {**root_vals, **profile_vals, **_INITIAL_SHELL_ENV}

        def get(key: str, default: str = "") -> str:
            val = env.get(key)
            return default if val is None else str(val)

        def get_personal(key: str, default: str = "") -> str:
            """For named profiles, never leak another person's info from root .env."""
            if requested != "default":
                if key in _INITIAL_SHELL_ENV:
                    return str(_INITIAL_SHELL_ENV[key])
                val = profile_vals.get(key)
                return default if val is None else str(val)
            return get(key, default)

        cls.PROFILE_NAME = requested or "default"

        # ─── LINKEDIN SEARCH QUERIES ────────────────────────
        raw_queries = get_personal("LINKEDIN_SEARCH_QUERIES") or get_personal(
            "LINKEDIN_HASHTAGS",
            '#devops #hiring,#sre #hiring,#cloudengineer #hiring,hiring "DevOps Engineer" email',
        )
        cls.LINKEDIN_SEARCH_QUERIES = [q.strip() for q in raw_queries.split(",") if q.strip()]
        cls.LINKEDIN_HASHTAGS = cls.LINKEDIN_SEARCH_QUERIES
        cls.LINKEDIN_SCRAPE_DAYS = int(get("LINKEDIN_SCRAPE_DAYS", "7") or "7")
        cls.MAX_POSTS_PER_SEARCH = int(get("MAX_POSTS_PER_SEARCH", "50") or "50")
        cls.SCROLL_PAUSE_TIME = float(get("SCROLL_PAUSE_TIME", "3") or "3")
        cls.HEADLESS = get("HEADLESS", "false").lower() == "true"

        # ─── CANDIDATE PROFILE ──────────────────────────────
        cls.YOUR_NAME = get_personal("YOUR_NAME", "Candidate").strip()
        cls.YOUR_ROLE = get_personal("YOUR_ROLE", "Professional").strip()
        cls.YOUR_SKILLS = get_personal("YOUR_SKILLS", "").strip()
        cls.YOUR_EXPERIENCE = get_personal("YOUR_EXPERIENCE", "2 years").strip()
        cls.YOUR_EDUCATION = get_personal("YOUR_EDUCATION", "").strip()
        cls.YOUR_LOCATION = get_personal("YOUR_LOCATION", "").strip()
        cls.YOUR_VALUE_PROPOSITION = get_personal("YOUR_VALUE_PROPOSITION", "").strip()
        cls.MAX_TARGET_EXPERIENCE = float(get_personal("MAX_TARGET_EXPERIENCE", "3") or "3")

        raw_keywords = get_personal(
            "TARGET_ROLE_KEYWORDS",
            "devops,sre,cloud engineer,kubernetes,aws,terraform,docker",
        )
        cls.TARGET_ROLE_KEYWORDS = [
            kw.strip().rstrip(".,;").lower()
            for kw in raw_keywords.split(",")
            if kw.strip().rstrip(".,;")
        ]

        raw_excludes = get_personal(
            "EXCLUDE_TITLE_KEYWORDS",
            "director,vp,vice president,principal,staff engineer,head of,lead architect,associate director,chief",
        )
        cls.EXCLUDE_TITLE_KEYWORDS = [
            kw.strip().lower() for kw in raw_excludes.split(",") if kw.strip()
        ]

        raw_acronyms = get_personal("PROFILE_ACRONYMS", "")
        cls.PROFILE_ACRONYMS = [
            a.strip().upper() for a in raw_acronyms.split(",") if a.strip()
        ]

        cls.YOUR_MOBILE = get_personal("YOUR_MOBILE", "").strip()
        cls.YOUR_LINKEDIN = get_personal("YOUR_LINKEDIN", "").strip()
        cls.YOUR_GITHUB = get_personal("YOUR_GITHUB", "").strip()
        cls.YOUR_PORTFOLIO = get_personal("YOUR_PORTFOLIO", "").strip()
        cls.RESUME_PATH = get_personal("RESUME_PATH", "assets/resume.pdf").strip()

        # ─── AI PROVIDER & FALLBACK ─────────────────────────
        cls.AI_PROVIDER = get("AI_PROVIDER", "bedrock").strip().lower()
        cls.AI_FALLBACK_PROVIDER = get("AI_FALLBACK_PROVIDER", "gemini").strip().lower()
        cls.AWS_BEDROCK_REGION = (
            get("AWS_BEDROCK_REGION") or get("AWS_REGION") or get("AWS_DEFAULT_REGION") or "us-east-1"
        ).strip()
        cls.AWS_BEARER_TOKEN_BEDROCK = (
            get("AWS_BEARER_TOKEN_BEDROCK") or get("BEDROCK_API_KEY") or ""
        ).strip()
        cls.BEDROCK_MODEL_ID = get("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0").strip()

        cls.GEMINI_API_KEY = (get("GEMINI_API_KEY") or get("GOOGLE_API_KEY") or "").strip()
        cls.GEMINI_MODEL = get("GEMINI_MODEL", "gemini-2.5-flash").strip()

        cls.OLLAMA_BASE_URL = get("OLLAMA_BASE_URL", "http://localhost:11434").strip()
        cls.OLLAMA_MODEL = get("OLLAMA_MODEL", "gemma").strip()

        # ─── SMTP ───────────────────────────────────────────
        cls.SMTP_HOST = get_personal("SMTP_HOST", "smtp.gmail.com").strip()
        cls.SMTP_PORT = int(get_personal("SMTP_PORT", "587") or "587")
        cls.SMTP_EMAIL = get_personal("SMTP_EMAIL", "").strip()
        raw_smtp_pw = get_personal("SMTP_PASSWORD", "").strip()
        cls.SMTP_PASSWORD = raw_smtp_pw.replace(" ", "") if "gmail" in cls.SMTP_HOST.lower() else raw_smtp_pw
        cls.EMAIL_SUBJECT_PREFIX = get_personal("EMAIL_SUBJECT_PREFIX", "Application for").strip()

        # ─── MONGODB (Isolated per profile by default) ─────
        cls.MONGO_URI = get("MONGO_URI", "mongodb://localhost:27017").strip()
        default_db = "linkedin_scraper" if cls.PROFILE_NAME == "default" else f"job_applier_{cls.PROFILE_NAME}"
        if "MONGO_DB" in profile_vals and profile_vals["MONGO_DB"].strip():
            cls.MONGO_DB = profile_vals["MONGO_DB"].strip()
        elif cls.PROFILE_NAME == "default":
            cls.MONGO_DB = get("MONGO_DB", default_db).strip()
        else:
            cls.MONGO_DB = default_db

        cls.MONGO_POSTS_COLLECTION = get("MONGO_POSTS_COLLECTION", "scraped_posts").strip()
        cls.MONGO_EMAILS_COLLECTION = get("MONGO_EMAILS_COLLECTION", "extracted_emails").strip()
        cls.MONGO_SENT_COLLECTION = get("MONGO_SENT_COLLECTION", "sent_emails").strip()
        cls.MONGO_RESPONSES_COLLECTION = get("MONGO_RESPONSES_COLLECTION", "email_responses").strip()

        # ─── FILTERS & SAFETY ───────────────────────────────
        cls.EMAIL_COOLDOWN_DAYS = int(get("EMAIL_COOLDOWN_DAYS", "15") or "15")
        cls.MAX_EMAILS_PER_DAY = int(get("MAX_EMAILS_PER_DAY", "30") or "30")
        cls.DELAY_BETWEEN_EMAILS = int(get("DELAY_BETWEEN_EMAILS", "60") or "60")
        cls.SKIP_PERSONAL_EMAILS = get("SKIP_PERSONAL_EMAILS", "false").lower() == "true"

        # ─── PIPELINE MODE ──────────────────────────────────
        cls.SCRAPE_MODE = get("SCRAPE_MODE", "true").lower() == "true"
        cls.DRY_RUN = get("DRY_RUN", "false").lower() == "true"

    @classmethod
    def get_session_dir(cls) -> str:
        """Return isolated session directory for the active profile."""
        base_session = os.path.join(BASE_DIR, "session")
        if cls.PROFILE_NAME and cls.PROFILE_NAME != "default":
            return os.path.join(base_session, cls.PROFILE_NAME)
        return base_session

    @classmethod
    def get_cookie_file(cls) -> str:
        return os.path.join(cls.get_session_dir(), "cookies.json")

    @classmethod
    def get_chrome_profile_dir(cls) -> str:
        return os.path.join(cls.get_session_dir(), "chrome_profile")

    @classmethod
    def get_linkedin_date_filter(cls) -> str:
        return cls.SCRAPE_DAYS_TO_LINKEDIN_FILTER.get(
            cls.LINKEDIN_SCRAPE_DAYS, "past-week"
        )

    @classmethod
    def validate(cls, check_smtp: bool = True, check_resume: bool = True):
        """Validate required configs are set."""
        errors = []
        if cls.AI_PROVIDER not in ("bedrock", "gemini", "ollama"):
            errors.append(f"Unsupported AI_PROVIDER '{cls.AI_PROVIDER}' (expected 'bedrock', 'gemini', or 'ollama')")
        if cls.AI_FALLBACK_PROVIDER not in ("", "none", "bedrock", "gemini", "ollama"):
            errors.append(
                f"Unsupported AI_FALLBACK_PROVIDER '{cls.AI_FALLBACK_PROVIDER}' "
                "(expected 'bedrock', 'gemini', 'ollama', or 'none')"
            )
        if check_smtp:
            if not cls.SMTP_EMAIL:
                errors.append("SMTP_EMAIL is required in profile/env config")
            if not cls.SMTP_PASSWORD:
                errors.append("SMTP_PASSWORD is required in profile/env config (Gmail App Password)")
        if check_resume:
            if not cls.YOUR_MOBILE:
                errors.append("YOUR_MOBILE is required in profile/env config (shown in every email signature)")
            if not os.path.exists(cls.RESUME_PATH):
                errors.append(f"Resume not found at: {cls.RESUME_PATH}")
            elif os.path.getsize(cls.RESUME_PATH) == 0:
                errors.append(f"Resume file is empty (0 bytes) at: {cls.RESUME_PATH} — replace with a valid PDF")
        if errors:
            raise ValueError("\n".join(["[CONFIG ERROR]"] + errors))
        return True

    @classmethod
    def display(cls, scrape_only: bool = False):
        """Print current config (masks passwords/keys)."""
        print("=" * 50)
        print("📋 CURRENT CONFIGURATION")
        print("=" * 50)
        if scrape_only:
            mode_label = "🔍 SCRAPE-ONLY (LinkedIn ➜ Extract ➜ MongoDB)"
        elif cls.SCRAPE_MODE:
            mode_label = "🟢 FULL PIPELINE (Scrape + Email)"
        else:
            mode_label = "🟡 EMAIL-ONLY MODE (MongoDB Backlog)"
        print(f"  Active Profile   : {cls.PROFILE_NAME}")
        print(f"  Pipeline Mode    : {mode_label}")
        print(f"  Scrape Days      : {cls.LINKEDIN_SCRAPE_DAYS}")
        print(f"  Search Queries   : {len(cls.LINKEDIN_HASHTAGS)} configured")
        print(f"  AI Provider      : {cls.AI_PROVIDER}")
        if cls.AI_PROVIDER == "bedrock":
            key_state = "✅ Configured" if cls.AWS_BEARER_TOKEN_BEDROCK else "⚠️ Not set"
            print(f"  Bedrock Region   : {cls.AWS_BEDROCK_REGION}")
            print(f"  Bedrock Model    : {cls.BEDROCK_MODEL_ID}")
            print(f"  Bedrock API Key  : {key_state}")
        elif cls.AI_PROVIDER == "gemini":
            g_state = "✅ Configured" if cls.GEMINI_API_KEY else "⚠️ Not set"
            print(f"  Gemini Model     : {cls.GEMINI_MODEL}")
            print(f"  Gemini API Key   : {g_state}")
        else:
            print(f"  Ollama Model     : {cls.OLLAMA_MODEL}")

        fallback = cls.AI_FALLBACK_PROVIDER if cls.AI_FALLBACK_PROVIDER not in ("", "none") else "none (templates only)"
        print(f"  Fallback AI      : {fallback}")
        if cls.AI_FALLBACK_PROVIDER == "gemini" and cls.AI_PROVIDER != "gemini":
            g_state = "✅ Configured" if cls.GEMINI_API_KEY else "⚠️ Not set"
            print(f"  Gemini Model     : {cls.GEMINI_MODEL}")
            print(f"  Gemini API Key   : {g_state}")
        print(f"  SMTP Email       : {cls.SMTP_EMAIL}")
        print(f"  MongoDB DB       : {cls.MONGO_DB}")
        print(f"  Session Dir      : {cls.get_session_dir()}")
        print(f"  Candidate        : {cls.YOUR_NAME} ({cls.YOUR_ROLE})")
        print(f"  Target Max Exp   : <= {cls.MAX_TARGET_EXPERIENCE} years")
        print(f"  Role Keywords    : {', '.join(cls.TARGET_ROLE_KEYWORDS[:5])}...")
        print(f"  Your Mobile      : {cls.YOUR_MOBILE}")
        if cls.YOUR_LOCATION:
            print(f"  Location         : {cls.YOUR_LOCATION}")
        if cls.YOUR_LINKEDIN:
            print(f"  Your LinkedIn    : {cls.YOUR_LINKEDIN}")
        if cls.YOUR_GITHUB:
            print(f"  Your GitHub      : {cls.YOUR_GITHUB}")
        if cls.YOUR_PORTFOLIO:
            print(f"  Your Portfolio   : {cls.YOUR_PORTFOLIO}")
        print(f"  Cooldown Days    : {cls.EMAIL_COOLDOWN_DAYS}")
        print(f"  Max Emails/Day   : {cls.MAX_EMAILS_PER_DAY}")
        print(f"  Skip Personal    : {cls.SKIP_PERSONAL_EMAILS}")
        print(f"  Dry Run          : {cls.DRY_RUN}")
        print(f"  Resume           : {cls.RESUME_PATH}")
        print("=" * 50)


# Load default configuration on import so module-level access remains seamless
Config.load()
