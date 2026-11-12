"""
config.py - Central configuration loader from .env
All settings are read from .env file - nothing hardcoded
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ─── LINKEDIN SEARCH QUERIES ────────────────────────────
    # Supports BOTH hashtags (#devops #hiring) AND natural text queries (e.g. 'hiring "DevOps Engineer" email')
    _raw_queries = os.getenv("LINKEDIN_SEARCH_QUERIES") or os.getenv(
        "LINKEDIN_HASHTAGS",
        '#devops #hiring,#sre #hiring,#cloudengineer #hiring,#platformengineer #hiring,#kubernetes #hiring,#aws #hiring,hiring "DevOps Engineer" email,hiring "Site Reliability Engineer" email,hiring "Cloud Engineer" email'
    )
    LINKEDIN_SEARCH_QUERIES: list[str] = [
        tag.strip() for tag in _raw_queries.split(",") if tag.strip()
    ]
    # Retain LINKEDIN_HASHTAGS as alias for backward compatibility
    LINKEDIN_HASHTAGS: list[str] = LINKEDIN_SEARCH_QUERIES
    LINKEDIN_SCRAPE_DAYS: int = int(os.getenv("LINKEDIN_SCRAPE_DAYS", "7"))
    MAX_POSTS_PER_SEARCH: int = int(os.getenv("MAX_POSTS_PER_SEARCH", "50"))
    SCROLL_PAUSE_TIME: float = float(os.getenv("SCROLL_PAUSE_TIME", "3"))
    HEADLESS: bool = os.getenv("HEADLESS", "false").lower() == "true"

    # Date filter map for LinkedIn URL param
    SCRAPE_DAYS_TO_LINKEDIN_FILTER: dict = {
        7:  "past-week",
        14: "past-2-weeks",
        30: "past-month",
    }

    @classmethod
    def get_linkedin_date_filter(cls) -> str:
        return cls.SCRAPE_DAYS_TO_LINKEDIN_FILTER.get(
            cls.LINKEDIN_SCRAPE_DAYS, "past-week"
        )

    # ─── YOUR PROFILE ───────────────────────────────────────
    YOUR_NAME: str = os.getenv("YOUR_NAME", "Candidate")
    YOUR_ROLE: str = os.getenv("YOUR_ROLE", "DevOps / Cloud / SRE Engineer")
    YOUR_SKILLS: str = os.getenv(
        "YOUR_SKILLS",
        "Kubernetes, Docker, AWS, GCP, Azure, Terraform, Ansible, Linux, Python, Go, CI/CD, GitHub Actions, Jenkins, Prometheus, Grafana"
    )
    YOUR_EXPERIENCE: str = os.getenv("YOUR_EXPERIENCE", "2 years")
    MAX_TARGET_EXPERIENCE: float = float(os.getenv("MAX_TARGET_EXPERIENCE", "3"))
    TARGET_ROLE_KEYWORDS: list[str] = [
        kw.strip().rstrip(".,;").lower()
        for kw in os.getenv(
            "TARGET_ROLE_KEYWORDS",
            "devops,sre,site reliability,site reliability engineer,cloud engineer,cloud architect,platform engineer,infrastructure engineer,devsecops,kubernetes,k8s,docker,aws,gcp,google cloud,azure,terraform,iac,infrastructure as code,ansible,helm,argocd,jenkins,github actions,gitlab ci,ci/cd,cicd,prometheus,grafana,loki,datadog,elk,cloudwatch,observability,linux,bash,python,golang,eks,gke,aks,ecs,serverless,cloudformation,pulumi,release engineer,build engineer"
        ).split(",")
        if kw.strip().rstrip(".,;")
    ]
    YOUR_MOBILE: str = os.getenv("YOUR_MOBILE", "")          # Required for signature
    YOUR_LINKEDIN: str = os.getenv("YOUR_LINKEDIN", "")
    YOUR_GITHUB: str = os.getenv("YOUR_GITHUB", "")
    YOUR_PORTFOLIO: str = os.getenv("YOUR_PORTFOLIO", "")    # Optional
    RESUME_PATH: str = os.getenv("RESUME_PATH", "assets/resume.pdf")

    # ─── AI PROVIDER & FALLBACK (Bedrock / Gemini / Ollama) ─
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "bedrock").strip().lower()
    AI_FALLBACK_PROVIDER: str = os.getenv("AI_FALLBACK_PROVIDER", "gemini").strip().lower()
    AWS_BEDROCK_REGION: str = (
        os.getenv("AWS_BEDROCK_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or "us-east-1"
    ).strip()
    AWS_BEARER_TOKEN_BEDROCK: str = (
        os.getenv("AWS_BEARER_TOKEN_BEDROCK")
        or os.getenv("BEDROCK_API_KEY")
        or ""
    ).strip()
    BEDROCK_MODEL_ID: str = os.getenv("BEDROCK_MODEL_ID", "us.amazon.nova-lite-v1:0").strip()

    # Google Gemini API (used as fallback or primary when AI_PROVIDER=gemini)
    GEMINI_API_KEY: str = (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    ).strip()
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    # Optional fallback / local provider (used when AI_PROVIDER=ollama)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "gemma")

    # ─── SMTP ───────────────────────────────────────────────
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_EMAIL: str = os.getenv("SMTP_EMAIL", "").strip()
    _raw_smtp_pw: str = os.getenv("SMTP_PASSWORD", "").strip()
    SMTP_PASSWORD: str = _raw_smtp_pw.replace(" ", "") if "gmail" in SMTP_HOST.lower() else _raw_smtp_pw
    EMAIL_SUBJECT_PREFIX: str = os.getenv("EMAIL_SUBJECT_PREFIX", "Application for")

    # ─── MONGODB ────────────────────────────────────────────
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB: str = os.getenv("MONGO_DB", "linkedin_scraper")
    MONGO_POSTS_COLLECTION: str = os.getenv("MONGO_POSTS_COLLECTION", "scraped_posts")
    MONGO_EMAILS_COLLECTION: str = os.getenv("MONGO_EMAILS_COLLECTION", "extracted_emails")
    MONGO_SENT_COLLECTION: str = os.getenv("MONGO_SENT_COLLECTION", "sent_emails")
    MONGO_RESPONSES_COLLECTION: str = os.getenv("MONGO_RESPONSES_COLLECTION", "email_responses")

    # ─── FILTERS & SAFETY ───────────────────────────────────
    EMAIL_COOLDOWN_DAYS: int = int(os.getenv("EMAIL_COOLDOWN_DAYS", "15"))
    MAX_EMAILS_PER_DAY: int = int(os.getenv("MAX_EMAILS_PER_DAY", "30"))
    DELAY_BETWEEN_EMAILS: int = int(os.getenv("DELAY_BETWEEN_EMAILS", "60"))
    SKIP_PERSONAL_EMAILS: bool = os.getenv("SKIP_PERSONAL_EMAILS", "false").lower() == "true"

    # ─── PIPELINE MODE ──────────────────────────────────────
    # SCRAPE_MODE=true  → Full pipeline: scrape LinkedIn → extract emails → AI email → send
    # SCRAPE_MODE=false → Skip scraping: use MongoDB backlog only → AI email → send
    SCRAPE_MODE: bool = os.getenv("SCRAPE_MODE", "true").lower() == "true"
    DRY_RUN: bool = os.getenv("DRY_RUN", "false").lower() == "true"

    @classmethod
    def validate(cls):
        """Validate required configs are set"""
        errors = []
        if cls.AI_PROVIDER not in ("bedrock", "gemini", "ollama"):
            errors.append(f"Unsupported AI_PROVIDER '{cls.AI_PROVIDER}' (expected 'bedrock', 'gemini', or 'ollama')")
        if cls.AI_FALLBACK_PROVIDER not in ("", "none", "bedrock", "gemini", "ollama"):
            errors.append(
                f"Unsupported AI_FALLBACK_PROVIDER '{cls.AI_FALLBACK_PROVIDER}' "
                "(expected 'bedrock', 'gemini', 'ollama', or 'none')"
            )
        if not cls.SMTP_EMAIL:
            errors.append("SMTP_EMAIL is required in .env")
        if not cls.SMTP_PASSWORD:
            errors.append("SMTP_PASSWORD is required in .env")
        if not cls.YOUR_MOBILE:
            errors.append("YOUR_MOBILE is required in .env (shown in every email signature)")
        if not os.path.exists(cls.RESUME_PATH):
            errors.append(f"Resume not found at: {cls.RESUME_PATH}")
        if errors:
            raise ValueError("\n".join(["[CONFIG ERROR]"] + errors))
        return True

    @classmethod
    def display(cls):
        """Print current config (masks passwords)"""
        print("=" * 50)
        print("📋 CURRENT CONFIGURATION")
        print("=" * 50)
        mode_label = "🟢 FULL PIPELINE (Scrape + Email)" if cls.SCRAPE_MODE else "🟡 EMAIL-ONLY MODE (MongoDB Backlog)"
        print(f"  Pipeline Mode    : {mode_label}")
        print(f"  Scrape Days      : {cls.LINKEDIN_SCRAPE_DAYS}")
        print(f"  Hashtags         : {cls.LINKEDIN_HASHTAGS}")
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
        print(f"  MongoDB URI      : {cls.MONGO_URI}")
        print(f"  Your Role        : {cls.YOUR_ROLE}")
        print(f"  Target Max Exp   : <= {cls.MAX_TARGET_EXPERIENCE} years")
        print(f"  Role Keywords    : {', '.join(cls.TARGET_ROLE_KEYWORDS[:4])}...")
        print(f"  Your Mobile      : {cls.YOUR_MOBILE}")
        print(f"  Your LinkedIn    : {cls.YOUR_LINKEDIN}")
        print(f"  Your GitHub      : {cls.YOUR_GITHUB}")
        if cls.YOUR_PORTFOLIO:
            print(f"  Your Portfolio   : {cls.YOUR_PORTFOLIO}")
        print(f"  Cooldown Days    : {cls.EMAIL_COOLDOWN_DAYS}")
        print(f"  Max Emails/Day   : {cls.MAX_EMAILS_PER_DAY}")
        print(f"  Skip Personal    : {cls.SKIP_PERSONAL_EMAILS}")
        print(f"  Dry Run          : {cls.DRY_RUN}")
        print(f"  Resume           : {cls.RESUME_PATH}")
        print("=" * 50)
