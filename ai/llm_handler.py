"""
ai/llm_handler.py
Unified AI email generator supporting AWS Bedrock (API Key / Bearer Token via Converse API)
and local Ollama, with anti-spam sanitization and DevOps/Cloud/SRE fallback templates.
"""

import os
import random
import re
import sys
import time
import urllib.parse
import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config


# ─────────────────────────────────────────────────────────────────────────────
# SPAM TRIGGER WORDS — LLM is instructed to NEVER use these
# ─────────────────────────────────────────────────────────────────────────────
SPAM_WORDS = [
    "guaranteed", "free", "urgent", "act now",
    "click here", "apply now", "don't miss", "limited time",
    "exclusive", "amazing", "incredible", "best ever",
    "100%", "no experience", "earn money", "work from home",
    "congratulations", "winner", "selected", "offer expires",
]

# ─────────────────────────────────────────────────────────────────────────────
# EMAIL BODY PROMPT — Domain-Agnostic (Driven by Active Candidate Profile)
# ─────────────────────────────────────────────────────────────────────────────
BODY_PROMPT = """You are {name}, a {role} with {experience} of experience.
{education_line}{value_prop_line}{track_line}Your core skills and competencies: {skills}

A recruiter or hiring manager posted this opportunity on LinkedIn:
\"\"\"
{post_text}
\"\"\"

Write a polished, concise, and professional job application email directly to this recruiter.

Follow this structure:
1. GREETING:
   - "Hi [Recruiter Name]," if their name is clearly stated in the post.
   - Otherwise, "Hi there,"

2. OPENING & HOOK:
   - State clearly: "I came across your post regarding the [Specific Role Title / Opportunity] and would like to express my strong interest."

3. VALUE PROPOSITION & RELEVANT FIT:
   - Write 1-2 short, impactful paragraphs connecting your {experience} of experience as a {role} directly to what the post asks for.
   - Highlight ONLY the skills, metrics, tools, or domain accomplishments from your profile that genuinely align with the role in the post.

4. ALIGNMENT & CALL TO ACTION:
   - Express enthusiasm to contribute to their team's goals and mention that your updated resume is attached for their review.

CRITICAL GUIDELINES:
- Tone: Confident, practical, articulate, and respectful.
- DO NOT invent tools, degrees, or experience not present in your profile.
- DO NOT use gimmicky spam buzzwords like: {spam_words}
- DO NOT write sign-offs like "Best regards" or contact details at the end (the system appends your verified signature automatically).
- Output ONLY the clean email body text without headers, subject, or quotes.

Write the email now:"""


# Technical, business, product, and analytics acronyms that should NOT be flagged as spam caps
TECH_ACRONYMS = {
    # DevOps / Cloud / SRE / Tech
    "SRE", "IAC", "CICD", "K8S", "EKS", "GKE", "AKS", "ECS", "ECR", "EC2",
    "AWS", "GCP", "AZURE", "OCI", "VPC", "VPN", "DNS", "CDN", "SSL", "TLS",
    "SSH", "HTTP", "HTTPS", "GRPC", "TCP", "UDP", "YAML", "JSON", "TOML",
    "RBAC", "IAM", "CIDR", "NAT", "ALB", "NLB", "ELB", "ASG", "WAF", "KMS",
    "SSM", "SQS", "SNS", "RDS", "ELK", "EFK", "APM", "OTEL", "RCA", "SLA",
    "SLO", "SLI", "MTTR", "MTTD", "VM", "VMS", "OS", "CLI", "SDK", "DB",
    "SQL", "NOSQL", "ORM", "SMTP", "IMAP", "SOC", "SOC2", "ISO", "PCI",
    "CKA", "CKAD", "CKS", "SAA", "RHCE", "PM2", "API", "APIS", "REST",
    # Business / Product / Data / Analytics / Operations
    "BA", "PO", "PM", "APM", "BI", "KPI", "KPIS", "OKR", "OKRS", "ROI",
    "GMV", "ODR", "CSAT", "NPS", "CRM", "ERP", "BRD", "FRD", "PRD", "UAT",
    "SOP", "TAT", "MIS", "GTM", "B2B", "B2C", "SAAS", "BPO", "MBA", "BTECH",
    "UAE", "JIRA", "SQL", "ETL", "UI", "UX", "QA", "MVP",
    # General / AI / Business
    "AI", "ML", "DL", "LLM", "LLMS", "NLP", "RAG", "MLOPS", "DEVSECOPS",
    "GPU", "GPUS", "CUDA", "SOTA", "PWC", "IBM", "TCS", "SAP", "AMD",
    "IIT", "NIT", "USA", "NYC", "HR", "CEO", "CTO", "VP", "IT",
}

# ─────────────────────────────────────────────────────────────────────────────
# SUBJECT LINE PROMPT — Modern, High-Converting Executive Style
# ─────────────────────────────────────────────────────────────────────────────
SUBJECT_PROMPT = """You are an expert recruiter and career coach.
Write ONE modern, polished email subject line for an application to this job post.

Job Post Details:
\"\"\"
{post_text_short}
\"\"\"

Applicant Profile:
- Full Name: {name}
- Target Role: {role}
- Experience: {experience}
- Core Skills: {skills}
- Target Company: {company}

DESIGN INSTRUCTIONS:
- Choose the best matching style below:
  * Style 1: Application: [Role] — [Your Name] ([Strength1] & [Strength2])
  * Style 2: [Role] Role at [Company] | [Your Name]
  * Style 3: [Your Name] — [Role] ([Strength1], [Strength2] | [Experience])
  * Style 4: Regarding the [Role] post — [Your Name]
- Pick the 1-2 most relevant keywords/skills from the post and applicant profile.
- If company name is not specifically known, use Style 1 or Style 3.
- Length: 6 to 11 words. (Under 80 characters).
- FORBIDDEN: NO spam buzzwords ("Urgent", "Excited", "Hire me", "Greetings"), NO exclamation marks, NO all-caps words except domain acronyms.
- Output ONLY the final subject line text. NO quotation marks. NO explanation.

Subject Line:"""


COMBINED_PROMPT = """You are {name}, a {role} with {experience} of experience.
{education_line}{value_prop_line}{track_line}Your core skills and competencies: {skills}
Target Company (if known): {company}

A recruiter or hiring manager posted this opportunity on LinkedIn:
\"\"\"
{post_text}
\"\"\"

Write BOTH a polished subject line AND a concise, professional job application email body in ONE response.

SUBJECT RULES:
- 6 to 11 words, under 80 characters, NO quotation marks, NO exclamation marks.
- Pick 1-2 relevant skills or domain keywords from the post and your profile.
- Use one of these formats:
  * Application: [Role] — {name} ([Strength1] & [Strength2])
  * [Role] Role at [Company] | {name}
  * {name} — [Role] ([Strength1], [Strength2] | {experience})

BODY RULES:
1. GREETING: "Hi [Recruiter Name]," if stated in the post, otherwise "Hi there,"
2. OPENING: "I came across your post regarding the [Specific Role Title / Opportunity] and would like to express my strong interest."
3. VALUE PROPOSITION: 1-2 short paragraphs highlighting your {experience} as a {role} across ONLY the skills, metrics, and accomplishments in your profile that match the post. Do NOT invent tools or experience you do not have.
4. ALIGNMENT & CTA: Close by expressing alignment and mentioning your updated resume is attached for review.
5. FORBIDDEN: Do NOT include spam words ({spam_words}), URLs, exclamation marks, or a sign-off like "Best regards" (the system appends your signature automatically).

FORMAT YOUR OUTPUT EXACTLY AS:
SUBJECT: <subject line here>
---BODY---
<email body here>"""


# ─────────────────────────────────────────────────────────────────────────────
# SPAM CHECKER & SANITIZERS
# ─────────────────────────────────────────────────────────────────────────────
def _allowed_acronyms() -> set[str]:
    if not Config.PROFILE_ACRONYMS:
        return TECH_ACRONYMS
    return TECH_ACRONYMS | set(Config.PROFILE_ACRONYMS)


def check_spam_score(text: str) -> dict:
    """
    Spam score checker.
    Returns score (0=clean, higher=spammier) and triggered words.
    """
    text_lower = text.lower()
    triggered = [w for w in SPAM_WORDS if w in text_lower]

    allowed = _allowed_acronyms()
    raw_caps = re.findall(r"\b[A-Z]{4,}\b", text)
    caps_words = [w for w in raw_caps if w.upper() not in allowed]

    exclamations = text.count("!")
    links = len(re.findall(r"http[s]?://", text))

    score = (
        len(triggered) * 3
        + len(caps_words) * 2
        + exclamations * 2
        + links * 5
    )
    return {
        "score": score,
        "triggered_spam_words": triggered,
        "caps_words": caps_words,
        "exclamations": exclamations,
        "links": links,
        "is_clean": score == 0,
    }


def _clean_caps_match(match: re.Match) -> str:
    word = match.group(1)
    return word if word.upper() in _allowed_acronyms() else word.title()


def clean_email_body(body: str) -> str:
    """Post-process AI output to strip markdown formatting and spam signals."""
    body = re.sub(r"\*\*(.+?)\*\*", r"\1", body)
    body = body.replace("`", "")
    body = body.replace("!", ".")
    body = re.sub(r"http[s]?://\S+", "", body)
    body = re.sub(r"\b([A-Z]{3,})\b", _clean_caps_match, body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body


def clean_subject(subject: str) -> str:
    """Remove markdown, spam signals, and prefixes from subject line."""
    subject = re.sub(r"\*\*(.+?)\*\*", r"\1", subject)
    subject = subject.strip().strip('"\'`*')
    subject = re.sub(r"^(?:subject|re)\s*[:\-]\s*", "", subject, flags=re.IGNORECASE)
    subject = subject.replace("!", "")
    subject = re.sub(r"\b([A-Z]{3,})\b", _clean_caps_match, subject)
    return subject.strip()


# ─────────────────────────────────────────────────────────────────────────────
# HTTP SESSION, SHARED RATE LIMITER & PROVIDER CLIENTS
# ─────────────────────────────────────────────────────────────────────────────
_SESSION = requests.Session()


class _ProviderRateState:
    """Tracks pacing and circuit-breaker state for a rate-limited LLM API."""

    def __init__(self, name: str, pacing_sec: float):
        self.name = name
        self.default_pacing_sec = pacing_sec
        self.pacing_sec = pacing_sec
        self.last_call_ts = 0.0
        self.consecutive_429 = 0
        self.circuit_open = False

    def reset(self):
        self.pacing_sec = self.default_pacing_sec
        self.last_call_ts = 0.0
        self.consecutive_429 = 0
        self.circuit_open = False


_BEDROCK_STATE = _ProviderRateState("Bedrock", pacing_sec=2.5)
_GEMINI_STATE = _ProviderRateState("Gemini", pacing_sec=4.2)


def _is_daily_quota_error(err_msg: str) -> bool:
    low = err_msg.lower()
    return any(tok in low for tok in ("tokens per day", "requests per day", "perday", "daily"))


def _post_with_rate_limit(
    state: _ProviderRateState,
    url: str,
    headers: dict,
    payload: dict,
    model_label: str,
    extract_fn,
    retries: int = 4,
    timeout: int = 60,
) -> str | None:
    """Shared HTTP POST helper with RPM pacing, 429 backoff, and circuit-breaker handling."""
    if state.circuit_open:
        return None

    saw_429 = False
    for attempt in range(1, retries + 1):
        elapsed = time.monotonic() - state.last_call_ts
        if state.last_call_ts > 0 and elapsed < state.pacing_sec:
            time.sleep(state.pacing_sec - elapsed)

        try:
            state.last_call_ts = time.monotonic()
            response = _SESSION.post(url, headers=headers, json=payload, timeout=timeout)

            if response.status_code in (400, 401, 403, 404):
                err_msg = response.text[:300].replace("\n", " ")
                print(f"[{state.name}] HTTP {response.status_code} ({model_label}): {err_msg}")
                if response.status_code in (401, 403):
                    state.circuit_open = True
                return None

            if response.status_code == 429:
                saw_429 = True
                err_msg = response.text[:250].replace("\n", " ")
                if _is_daily_quota_error(err_msg):
                    state.circuit_open = True
                    print(
                        f"[{state.name}] ⚠️  Daily quota exhausted ({err_msg}) — "
                        f"disabling {state.name} for this run."
                    )
                    return None

                retry_after_raw = response.headers.get("Retry-After", "")
                try:
                    wait_s = max(3.0, float(retry_after_raw))
                except ValueError:
                    wait_s = (2 ** attempt) * 2.5 + random.uniform(0.5, 2.0)

                state.pacing_sec = min(10.0, state.pacing_sec + 1.5)
                print(f"[{state.name}] HTTP 429 throttled on attempt {attempt}/{retries} ({err_msg}) — waiting {wait_s:.1f}s")
                if attempt < retries:
                    time.sleep(wait_s)
                    continue
                break

            if response.status_code in (500, 502, 503, 504):
                print(f"[{state.name}] Transient HTTP {response.status_code} on attempt {attempt}/{retries}")
                if attempt < retries:
                    time.sleep(attempt * 2.0)
                    continue
                return None

            response.raise_for_status()
            resp_text = (extract_fn(response.json()) or "").strip()
            if resp_text:
                state.consecutive_429 = 0
                return resp_text
            print(f"[{state.name}] Empty response on attempt {attempt}/{retries}")
        except requests.exceptions.Timeout:
            print(f"[{state.name}] Timeout on attempt {attempt}/{retries}")
        except requests.exceptions.ConnectionError:
            print(f"[{state.name}] Connection error reaching {url.split('/v1')[0].split('/model')[0]}")
            return None
        except Exception as e:
            print(f"[{state.name}] Generation failed (attempt {attempt}/{retries}): {e}")

    if saw_429:
        state.consecutive_429 += 1
        if state.consecutive_429 >= 3:
            state.circuit_open = True
            print(
                f"[{state.name}] ⚠️  Repeated HTTP 429 throttling across 3 requests — "
                f"switching away from {state.name} for this run."
            )
    return None


def _extract_bedrock_text(data: dict) -> str:
    content_blocks = data.get("output", {}).get("message", {}).get("content", [])
    return "".join(
        block.get("text", "") for block in content_blocks if isinstance(block, dict)
    )


def _extract_gemini_text(data: dict) -> str:
    candidates = data.get("candidates", [])
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    # Skip internal reasoning/thought parts on Gemini 2.5 thinking models
    return "".join(
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and not part.get("thought")
    )


def _call_bedrock(prompt: str, max_tokens: int = 550, temperature: float = 0.7, retries: int = 4) -> str | None:
    """Call AWS Bedrock Converse API using Bearer Token authentication (AWS_BEARER_TOKEN_BEDROCK)."""
    token = Config.AWS_BEARER_TOKEN_BEDROCK
    if not token:
        if not _BEDROCK_STATE.circuit_open:
            print("[Bedrock] AWS_BEARER_TOKEN_BEDROCK is not configured")
            _BEDROCK_STATE.circuit_open = True
        return None

    encoded_model = urllib.parse.quote(Config.BEDROCK_MODEL_ID, safe="")
    url = f"https://bedrock-runtime.{Config.AWS_BEDROCK_REGION}.amazonaws.com/model/{encoded_model}/converse"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    return _post_with_rate_limit(
        _BEDROCK_STATE,
        url=url,
        headers=headers,
        payload=payload,
        model_label=Config.BEDROCK_MODEL_ID,
        extract_fn=_extract_bedrock_text,
        retries=retries,
    )


def _call_gemini(prompt: str, max_tokens: int = 600, temperature: float = 0.7, retries: int = 4) -> str | None:
    """Call Google Gemini API generateContent endpoint using x-goog-api-key header."""
    api_key = Config.GEMINI_API_KEY
    if not api_key:
        if not _GEMINI_STATE.circuit_open:
            print("[Gemini] GEMINI_API_KEY is not configured")
            _GEMINI_STATE.circuit_open = True
        return None

    encoded_model = urllib.parse.quote(Config.GEMINI_MODEL, safe="")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    gen_config: dict = {
        "temperature": temperature,
        "maxOutputTokens": max(max_tokens, 2048 if "2.5-flash" in Config.GEMINI_MODEL.lower() else 4096),
    }
    if "2.5-flash" in Config.GEMINI_MODEL.lower():
        # Prevent hidden thinking tokens from exhausting maxOutputTokens on email drafts
        gen_config["thinkingConfig"] = {"thinkingBudget": 0}

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_config,
    }
    return _post_with_rate_limit(
        _GEMINI_STATE,
        url=url,
        headers=headers,
        payload=payload,
        model_label=Config.GEMINI_MODEL,
        extract_fn=_extract_gemini_text,
        retries=retries,
    )


def _call_ollama(prompt: str, max_tokens: int = 600, temperature: float = 0.7, retries: int = 2) -> str | None:
    """Call local/remote Ollama API with retry logic."""
    for attempt in range(1, retries + 1):
        try:
            response = _SESSION.post(
                f"{Config.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": Config.OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=300,
            )
            response.raise_for_status()
            data = response.json()
            resp_text = (data.get("response") or "").strip()
            if resp_text:
                return resp_text
            print(f"[Ollama] Empty response on attempt {attempt}/{retries}")
        except requests.exceptions.Timeout:
            print(f"[Ollama] Timeout on attempt {attempt}/{retries} (model may be slow)")
        except requests.exceptions.ConnectionError:
            print(f"[Ollama] Connection error at {Config.OLLAMA_BASE_URL}")
            return None
        except Exception as e:
            print(f"[Ollama] Generation failed (attempt {attempt}/{retries}): {e}")
    return None


def _provider_model_name(provider: str) -> str:
    if provider == "bedrock":
        return Config.BEDROCK_MODEL_ID
    if provider == "gemini":
        return Config.GEMINI_MODEL
    return Config.OLLAMA_MODEL


def _call_provider(provider: str, prompt: str, max_tokens: int, temperature: float) -> str | None:
    if provider == "bedrock":
        return _call_bedrock(prompt, max_tokens=max_tokens, temperature=temperature)
    if provider == "gemini":
        return _call_gemini(prompt, max_tokens=max_tokens, temperature=temperature)
    if provider == "ollama":
        return _call_ollama(prompt, max_tokens=max_tokens, temperature=temperature)
    return None


def _generate_text(prompt: str, max_tokens: int, temperature: float) -> tuple[str | None, str]:
    """
    Dispatch text generation to primary provider, automatically falling back to
    AI_FALLBACK_PROVIDER (e.g., Gemini) if the primary fails or hits quota.
    Returns: (generated_text_or_None, provider_name_used)
    """
    primary = Config.AI_PROVIDER
    fallback = Config.AI_FALLBACK_PROVIDER

    result = _call_provider(primary, prompt, max_tokens, temperature)
    if result:
        return result, primary

    if fallback and fallback not in ("none", primary):
        print(f"[AI] ↪ {primary.upper()} unavailable — trying fallback provider ({fallback.upper()}: {_provider_model_name(fallback)})")
        fb_result = _call_provider(fallback, prompt, max_tokens, temperature)
        if fb_result:
            return fb_result, fallback
        return None, fallback

    return None, primary


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────
def _detect_profile_track(post_text: str = "") -> str:
    """
    Detect whether post is targeting:
    - 'data_analyst' (Data Analyst, Business Analyst, BI, Analytics, Python/SQL/PowerBI)
    - 'account_manager' (Key Account Manager, Account Manager, Customer Support/Success, E-Commerce, CRM)
    - 'general' (Standard profile / DevOps / other)
    """
    if not post_text:
        return "general"
    low = post_text.lower()
    da_keywords = (
        "data analyst", "data analysis", "business analyst", "business analysis",
        "business intelligence", "bi analyst", "analytics", "power bi", "powerbi",
        "sql", "python", "pandas", "numpy", "kpi dashboard", "tableau", "eda",
        "reporting analyst", "mis analyst", "dashboard", "data model"
    )
    da_score = sum(1 for kw in da_keywords if kw in low)

    kam_keywords = (
        "account manager", "key account", "customer support", "customer success",
        "customer service", "process advisor", "client relations", "crm", "sla",
        "csat", "e-commerce", "ecommerce", "marketplace", "flipkart", "shopsy",
        "vendor onboarding", "seller onboarding", "gmv", "odr"
    )
    kam_score = sum(1 for kw in kam_keywords if kw in low)

    if da_score > kam_score:
        return "data_analyst"
    elif kam_score > da_score:
        return "account_manager"
    return "general"


def _profile_prompt_context(post_text: str = "") -> dict[str, str]:
    edu = f"Education: {Config.YOUR_EDUCATION}\n" if Config.YOUR_EDUCATION else ""
    vp = f"Career Highlights: {Config.YOUR_VALUE_PROPOSITION}\n" if Config.YOUR_VALUE_PROPOSITION else ""

    track_line = ""
    if Config.PROFILE_NAME == "sakshi":
        track = _detect_profile_track(post_text)
        if track == "data_analyst":
            track_line = (
                "ROLE EMPHASIS (Data & Business Analyst Track):\n"
                "- This opportunity targets Data / Business Analytics.\n"
                "- Emphasize technical analytical stack: Python (Pandas, NumPy), SQL (queries & joins), "
                "Power BI (DAX & interactive KPI dashboards), Advanced Excel (Pivot Tables, Power Query), and EDA.\n"
                "- Highlight ability to translate raw transactional data into commercial insights and automated reporting.\n"
            )
        elif track == "account_manager":
            track_line = (
                "ROLE EMPHASIS (Key Account Manager & Customer Operations Track):\n"
                "- This opportunity targets Account Management, Customer Success, or E-Commerce Operations.\n"
                "- Emphasize: Managing key seller portfolios on Flipkart and Shopsy (Teleperformance), driving GMV growth, "
                "pricing optimization, reducing Order Defect Rate (ODR), and maintaining SLA/CSAT excellence in multi-channel client support.\n"
            )

    return {
        "education_line": edu,
        "value_prop_line": vp,
        "track_line": track_line,
    }


def generate_email_body(post_text: str, company: str = "") -> str:
    """
    Generate a spam-safe, human-like email body using primary AI (and fallback AI).
    Falls back to clean profile template if all providers fail or flag spam.
    """
    ctx = _profile_prompt_context(post_text)
    prompt = BODY_PROMPT.format(
        name=Config.YOUR_NAME,
        role=Config.YOUR_ROLE,
        experience=Config.YOUR_EXPERIENCE,
        skills=Config.YOUR_SKILLS or Config.YOUR_ROLE,
        post_text=post_text[:1200],
        spam_words=", ".join(SPAM_WORDS[:12]),
        **ctx,
    )

    body, used_provider = _generate_text(prompt, max_tokens=500, temperature=0.75)
    provider_label = _provider_model_name(used_provider)

    if not body:
        print(f"[{used_provider.upper()}] ⚠️  No response from model — using fallback template")
        return _fallback_email_body(post_text)

    body = clean_email_body(body)

    spam = check_spam_score(body)
    if spam["score"] > 0:
        print(f"[{used_provider.upper()}] Spam score: {spam['score']} | Issues: {spam}")
        if spam["triggered_spam_words"] or spam["score"] >= 4:
            print(f"[{used_provider.upper()}] ⚠️  Generated body flagged spam check — using fallback template")
            return _fallback_email_body(post_text)
    else:
        print(f"[{used_provider.upper()}] Email is spam-clean (score: 0)")

    print(f"[{used_provider.upper()}] Email generated ({len(body.split())} words) via {provider_label}")
    return body


def generate_subject_line(post_text: str, company: str = "") -> str:
    """
    Generate a modern, high-converting subject line using primary AI (and fallback AI).
    Falls back to polished DevOps template if unavailable.
    """
    prompt = SUBJECT_PROMPT.format(
        post_text_short=post_text[:500],
        name=Config.YOUR_NAME,
        role=Config.YOUR_ROLE,
        experience=Config.YOUR_EXPERIENCE,
        skills=Config.YOUR_SKILLS,
        company=company or "your team",
    )

    subject, used_provider = _generate_text(prompt, max_tokens=60, temperature=0.6)

    if not subject:
        return _fallback_subject(company, post_text)

    subject = clean_subject(subject)

    if not subject or len(subject) > 85 or len(subject) < 8:
        print(f"[{used_provider.upper()}] Subject length {len(subject)} out of range — using fallback subject")
        return _fallback_subject(company, post_text)

    spam = check_spam_score(subject)
    if spam["score"] > 0:
        print(f"[{used_provider.upper()}] Subject spam score {spam['score']} — using fallback subject")
        return _fallback_subject(company, post_text)

    print(f"[{used_provider.upper()}] Subject: '{subject}'")
    return subject


def generate_email_content(post_text: str, company: str = "") -> tuple[str, str]:
    """
    Generate BOTH subject line and email body in a single LLM request.
    Tries primary provider first, then AI_FALLBACK_PROVIDER (e.g. Gemini), then DevOps templates.
    Returns: (subject, body)
    """
    ctx = _profile_prompt_context(post_text)
    prompt = COMBINED_PROMPT.format(
        name=Config.YOUR_NAME,
        role=Config.YOUR_ROLE,
        experience=Config.YOUR_EXPERIENCE,
        skills=Config.YOUR_SKILLS or Config.YOUR_ROLE,
        company=company or "your team",
        post_text=post_text[:1200],
        spam_words=", ".join(SPAM_WORDS[:12]),
        **ctx,
    )

    raw, used_provider = _generate_text(prompt, max_tokens=600, temperature=0.7)
    provider_label = _provider_model_name(used_provider)

    if not raw:
        print("[AI] ⚠️  All AI providers unavailable — using profile fallback template")
        return _fallback_subject(company, post_text), _fallback_email_body(post_text)

    subject_raw = ""
    body_raw = ""
    parts = re.split(
        r"\n\s*(?:\*{0,2})(?:---\s*BODY\s*---|BODY:)\s*(?:\*{0,2})(?:\n|$)",
        raw,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    if len(parts) == 2:
        head, body_raw = parts
        m = re.search(r"(?:\*{0,2})SUBJECT(?:\*{0,2})\s*:\s*(.+)", head, re.IGNORECASE)
        subject_raw = m.group(1).strip() if m else head.strip()
    else:
        lines = [ln.strip() for ln in raw.strip().splitlines()]
        if lines and re.match(r"^(?:\*{0,2})SUBJECT(?:\*{0,2})\s*:", lines[0], re.IGNORECASE):
            subject_raw = re.sub(r"^(?:\*{0,2})SUBJECT(?:\*{0,2})\s*:\s*", "", lines[0], flags=re.IGNORECASE)
            body_raw = "\n".join(lines[1:]).strip()
        else:
            body_raw = raw.strip()

    # Validate & sanitize subject
    subject = clean_subject(subject_raw) if subject_raw else ""
    if not subject or len(subject) > 85 or len(subject) < 8 or check_spam_score(subject)["score"] > 0:
        subject = _fallback_subject(company, post_text)

    # Validate & sanitize body
    body = clean_email_body(body_raw) if body_raw else ""
    if not body or len(body) < 40:
        body = _fallback_email_body(post_text)
    else:
        spam = check_spam_score(body)
        if spam["triggered_spam_words"] or spam["score"] >= 4:
            print(f"[{used_provider.upper()}] ⚠️  Generated body flagged spam check — using DevOps fallback template")
            body = _fallback_email_body(post_text)

    print(f"[{used_provider.upper()}] Drafted ({len(body.split())} words) via {provider_label} | Subject: '{subject}'")
    return subject, body


# ─────────────────────────────────────────────────────────────────────────────
# FALLBACK TEMPLATES (Domain-agnostic, parameterized by active Config profile)
# Note: Do NOT add sign-off/name at the bottom — SMTPHandler.attach_signature()
# automatically strips closings and appends the verified signature.
# ─────────────────────────────────────────────────────────────────────────────
_FALLBACK_BODIES = [
    """Hi there,

I came across your post regarding the {role} opportunity and would like to express my strong interest. With {experience} of hands-on experience across {top_skills}, I have consistently delivered measurable improvements in operational performance, stakeholder alignment, and data-informed decision-making.

{value_line}Please find my updated resume attached for your review. I would welcome the chance to connect and discuss how I can contribute to your team.""",
    """Hello,

Your post caught my attention — the responsibilities you outlined align closely with my work over the past {experience} as a {role}.

My core strengths include {top_skills}, with a proven focus on turning operational metrics into actionable recommendations and collaborating smoothly across teams. My resume is attached, and I would be glad to connect for a quick conversation.""",
    """Hi,

I saw your hiring post and wanted to reach out directly. I am a {role} with {experience} of experience across {top_skills}, focused on driving efficiency, clear reporting, and strong execution.

{value_line}I believe my background aligns well with your team's goals. Please find my updated resume attached for your review.""",
]

# ─────────────────────────────────────────────────────────
# SAKSHI SPECIALIZED TEMPLATES: 2 Separate Tracks
# Track 1: Data Analyst & Business Analyst
# Track 2: Key Account Manager & Customer Support / Operations
# ─────────────────────────────────────────────────────────
_SAKSHI_DA_BODIES = [
    """Hi there,

I came across your post regarding the Data / Business Analyst opportunity and would like to express my strong interest.

As a B.Tech graduate with 2+ years of hands-on experience across business operations and analytics, I specialize in translating complex operational and transactional datasets into actionable business intelligence. My core technical strengths include Python (Pandas, NumPy), SQL for multi-table queries and data modeling, Power BI (custom DAX measures and interactive KPI dashboards), and Advanced Excel (Power Query, XLOOKUP, Pivot Tables). In previous roles, I audited daily performance dashboards, conducted exploratory data analysis (EDA), and identified revenue leakages to drive commercial growth.

Please find my updated resume attached for your review. I would welcome the opportunity to discuss how my analytical rigor and problem-solving mindset can contribute to your team.""",
    """Hello,

Your post regarding the Data / Business Analytics role caught my attention — the requirements align directly with my background in data manipulation, KPI dashboarding, and business intelligence.

Over the past 2 years, I have leveraged Python, SQL, Power BI, and Advanced Excel to analyze daily marketplace metrics, build automated reporting pipelines, and surface actionable insights that optimize conversion and performance. Combining an engineering problem-solving foundation with commercial acumen, I focus on turning raw numbers into strategic clarity.

My single-page resume is attached, and I would be glad to connect for a brief conversation.""",
]

_SAKSHI_KAM_BODIES = [
    """Hi there,

I came across your post regarding the Key Account Management / Client Operations opportunity and would like to express my strong interest.

With 2+ years of cross-functional experience directing key seller account portfolios on Flipkart and Shopsy (Teleperformance) and managing enterprise client relationships (Splash India, Ttec), I have consistently driven measurable improvements in GMV growth, pricing optimization, Order Defect Rate (ODR) reduction, and SLA/CSAT excellence. I collaborate smoothly across Category, Finance, Supply Chain, and Support teams to eliminate operational bottlenecks and elevate customer satisfaction.

Please find my updated resume attached for your review. I would love the chance to connect and discuss how I can contribute to your team's operational and growth goals.""",
    """Hello,

Your hiring post caught my attention — the responsibilities outlined align closely with my 2+ years of experience across E-Commerce Key Account Management, Enterprise CRM, and Multi-Channel Customer Support.

In my recent roles managing seller portfolios on Flipkart and Shopsy, I audited daily sales performance, accelerated GMV growth through targeted promotions and pricing optimization, and maintained strict SLA compliance while sustaining top-tier CSAT scores. I take strong ownership of account health, partner onboarding, and cross-departmental coordination.

My resume is attached, and I look forward to the possibility of discussing how I can add value to your team.""",
]

_FALLBACK_SUBJECTS = [
    "Application: {role} — {name} ({skill1}, {skill2})",
    "Application: {role} at {company} — {name}",
    "{name} — {role} ({skill1}, {skill2} | {experience})",
    "{role} Role — {name} (Resume Attached)",
    "Application: {role} — {name} ({experience} Exp)",
]


def _top_skills(limit: int = 8, post_text: str = "") -> list[str]:
    skills = [s.strip().rstrip(".") for s in Config.YOUR_SKILLS.split(",") if s.strip()]
    if not skills:
        return [Config.YOUR_ROLE] if Config.YOUR_ROLE else ["Domain Expertise"]
    if post_text:
        low = post_text.lower()
        matched = [s for s in skills if s.lower() in low]
        rest = [s for s in skills if s.lower() not in low]
        skills = matched + rest
    return skills[:limit]


def _clean_company_for_subject(company: str) -> str:
    """Return company only if it looks like a short organization name, not a recruiter headline."""
    c = (company or "").strip()
    if not c or len(c) > 35:
        return ""
    low = c.lower()
    if any(word in low for word in ("hiring", "recruiter", "talent", "hr ", "|", "engineer", "specialist", "lead")):
        return ""
    return c


def _fallback_email_body(post_text: str = "") -> str:
    """Pick a random spam-clean fallback template tailored to the active profile & post."""
    if Config.PROFILE_NAME == "sakshi":
        track = _detect_profile_track(post_text)
        if track == "account_manager":
            return random.choice(_SAKSHI_KAM_BODIES)
        return random.choice(_SAKSHI_DA_BODIES)

    template = random.choice(_FALLBACK_BODIES)
    value_line = f"{Config.YOUR_VALUE_PROPOSITION.strip()} " if Config.YOUR_VALUE_PROPOSITION.strip() else ""
    return template.format(
        role=Config.YOUR_ROLE,
        experience=Config.YOUR_EXPERIENCE,
        top_skills=", ".join(_top_skills(8, post_text)),
        value_line=value_line,
    )


def _short_role() -> str:
    role = (Config.YOUR_ROLE or "Candidate").strip()
    if len(role) <= 38:
        return role
    for sep in ("|", "/", "—", "-"):
        if sep in role:
            head = role.split(sep, 1)[0].strip()
            if head:
                return head
    return role[:38].strip()


def _fallback_subject(company: str = "", post_text: str = "") -> str:
    """Pick a random spam-clean fallback subject tailored to the active profile."""
    clean_co = _clean_company_for_subject(company)
    short_role = _short_role()

    if Config.PROFILE_NAME == "sakshi":
        track = _detect_profile_track(post_text)
        if track == "account_manager":
            kam_subjects = [
                "Application: Key Account Manager — Sakshi Puraviya (Flipkart/Shopsy Exp)",
                "Application: Customer Success / Operations — Sakshi Puraviya",
                "Key Account Manager Role — Sakshi Puraviya (Resume Attached)",
            ]
            if clean_co:
                kam_subjects.append(f"Account Manager Role at {clean_co} — Sakshi Puraviya")
            return random.choice(kam_subjects)[:85]
        else:
            da_subjects = [
                "Application: Data / Business Analyst — Sakshi Puraviya (SQL, Power BI)",
                "Data Analyst Role — Sakshi Puraviya (Python, SQL, Power BI)",
                "Application: Business Analyst — Sakshi Puraviya (B.Tech)",
            ]
            if clean_co:
                da_subjects.append(f"Data Analyst Role at {clean_co} — Sakshi Puraviya")
            return random.choice(da_subjects)[:85]

    skills_list = _top_skills(3, post_text)
    has_two_skills = len(skills_list) >= 2
    short_role = _short_role()

    candidates = []
    for tmpl in _FALLBACK_SUBJECTS:
        if "{company}" in tmpl and not clean_co:
            continue
        if "{skill2}" in tmpl and not has_two_skills:
            continue
        candidates.append(tmpl)
    if not candidates:
        candidates = ["{role} Role — {name} (Resume Attached)"]

    short_skills = [s.split("(", 1)[0].strip() for s in skills_list if s.split("(", 1)[0].strip()]
    s1 = short_skills[0][:24] if len(short_skills) > 0 else short_role
    s2 = short_skills[1][:24] if len(short_skills) > 1 else Config.YOUR_EXPERIENCE
    s3 = short_skills[2][:24] if len(short_skills) > 2 else Config.YOUR_EXPERIENCE

    rendered = []
    for tmpl in candidates:
        cand = tmpl.format(
            name=Config.YOUR_NAME,
            role=short_role,
            experience=Config.YOUR_EXPERIENCE,
            company=clean_co or "your team",
            skill1=s1,
            skill2=s2,
            skill3=s3,
        )
        if len(cand) <= 85:
            rendered.append(cand)
    if not rendered:
        return f"{short_role} Role — {Config.YOUR_NAME}"[:85]
    return random.choice(rendered)


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH / STATUS CHECKS
# ─────────────────────────────────────────────────────────────────────────────
def check_bedrock_status() -> dict:
    """Check if AWS Bedrock API key is configured and endpoint is reachable."""
    model_id = Config.BEDROCK_MODEL_ID
    region = Config.AWS_BEDROCK_REGION
    token = Config.AWS_BEARER_TOKEN_BEDROCK

    if not token:
        return {
            "provider": "bedrock",
            "running": False,
            "configured_model": model_id,
            "region": region,
            "model_available": False,
            "available_models": [],
            "note": "AWS_BEARER_TOKEN_BEDROCK is missing in .env",
        }

    # Strip cross-region prefix (us./eu./apac./global.) when matching base foundation models
    base_model_id = re.sub(r"^(?:us|eu|apac|global)\.", "", model_id)

    try:
        resp = _SESSION.get(
            f"https://bedrock.{region}.amazonaws.com/foundation-models",
            params={"byOutputModality": "TEXT"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        if resp.status_code == 200:
            models = [m.get("modelId", "") for m in resp.json().get("modelSummaries", [])]
            return {
                "provider": "bedrock",
                "running": True,
                "configured_model": model_id,
                "region": region,
                "model_available": any(base_model_id in m for m in models),
                "available_models": models[:10],
                "note": "Connected to AWS Bedrock",
            }
        if resp.status_code == 403:
            # Runtime-scoped Bedrock API keys may lack ListFoundationModels permission
            return {
                "provider": "bedrock",
                "running": True,
                "configured_model": model_id,
                "region": region,
                "model_available": True,
                "available_models": [],
                "note": "Bedrock key configured (runtime-scoped; model list check skipped)",
            }
        if resp.status_code == 401:
            return {
                "provider": "bedrock",
                "running": False,
                "configured_model": model_id,
                "region": region,
                "model_available": False,
                "available_models": [],
                "note": "AWS Bedrock API key rejected (HTTP 401 — check/regenerate key)",
            }
        return {
            "provider": "bedrock",
            "running": False,
            "configured_model": model_id,
            "region": region,
            "model_available": False,
            "available_models": [],
            "note": f"Unexpected HTTP {resp.status_code} from Bedrock",
        }
    except Exception as e:
        return {
            "provider": "bedrock",
            "running": False,
            "configured_model": model_id,
            "region": region,
            "model_available": False,
            "available_models": [],
            "note": f"Cannot reach AWS Bedrock in {region}: {e}",
        }


def check_gemini_status() -> dict:
    """Check if Google Gemini API key is configured and valid."""
    model_id = Config.GEMINI_MODEL
    api_key = Config.GEMINI_API_KEY

    if not api_key:
        return {
            "provider": "gemini",
            "running": False,
            "configured_model": model_id,
            "model_available": False,
            "available_models": [],
            "note": "GEMINI_API_KEY is missing in .env",
        }

    try:
        resp = _SESSION.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            headers={"x-goog-api-key": api_key},
            timeout=5,
        )
        if resp.status_code == 200:
            models = [
                m.get("name", "").replace("models/", "")
                for m in resp.json().get("models", [])
            ]
            return {
                "provider": "gemini",
                "running": True,
                "configured_model": model_id,
                "model_available": any(model_id == m or model_id in m for m in models),
                "available_models": [m for m in models if "gemini" in m][:10],
                "note": "Connected to Google Gemini API",
            }
        if resp.status_code in (400, 401, 403):
            return {
                "provider": "gemini",
                "running": False,
                "configured_model": model_id,
                "model_available": False,
                "available_models": [],
                "note": f"Gemini API key rejected (HTTP {resp.status_code} — check GEMINI_API_KEY)",
            }
        return {
            "provider": "gemini",
            "running": False,
            "configured_model": model_id,
            "model_available": False,
            "available_models": [],
            "note": f"Unexpected HTTP {resp.status_code} from Gemini API",
        }
    except Exception as e:
        return {
            "provider": "gemini",
            "running": False,
            "configured_model": model_id,
            "model_available": False,
            "available_models": [],
            "note": f"Cannot reach Gemini API: {e}",
        }


def check_ollama_status() -> dict:
    """Check if Ollama is running and configured model is available."""
    try:
        resp = _SESSION.get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        return {
            "provider": "ollama",
            "running": True,
            "available_models": models,
            "configured_model": Config.OLLAMA_MODEL,
            "model_available": any(Config.OLLAMA_MODEL in m for m in models),
            "note": "Connected to Ollama",
        }
    except Exception:
        return {
            "provider": "ollama",
            "running": False,
            "available_models": [],
            "configured_model": Config.OLLAMA_MODEL,
            "model_available": False,
            "note": f"Ollama not running at {Config.OLLAMA_BASE_URL}",
        }


def _check_provider_status(provider: str) -> dict:
    if provider == "gemini":
        return check_gemini_status()
    if provider == "ollama":
        return check_ollama_status()
    return check_bedrock_status()


def check_llm_status() -> dict:
    """Check connectivity/readiness for primary AI provider and optional fallback."""
    status = _check_provider_status(Config.AI_PROVIDER)
    fallback = Config.AI_FALLBACK_PROVIDER
    if fallback and fallback not in ("none", Config.AI_PROVIDER):
        status["fallback"] = _check_provider_status(fallback)
    return status

