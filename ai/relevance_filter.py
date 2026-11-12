"""
ai/relevance_filter.py
Filters posts based on job profile keywords and years of experience criteria.
Ensures we only apply to relevant roles matching candidate's level.
"""

import re
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config


# Regular expressions for detecting years of experience in post text
EXPERIENCE_PATTERNS = [
    # "2-4 years", "2 to 5 yrs", "1-3 Yrs"
    re.compile(r'(\d+)\s*(?:-|to)\s*(\d+)\s*(?:years?|yrs?|yr)\b', re.IGNORECASE),
    # "3+ years", "3 + yrs", "minimum 2 years", "min 3 yrs"
    re.compile(r'(?:min(?:imum)?\s*)?(\d+)\s*\+\s*(?:years?|yrs?|yr)\b', re.IGNORECASE),
    # "3 years of experience", "2 yrs exp", "3+ yoe"
    re.compile(r'(\d+)\s*(?:years?|yrs?|yr|yoe)\s*(?:of\s*)?(?:experience|exp)?\b', re.IGNORECASE),
    # "experience: 2-4 years"
    re.compile(r'(?:exp|experience)\s*[:\-]\s*(\d+)(?:\s*(?:-|to)\s*(\d+))?\s*(?:years?|yrs?)?', re.IGNORECASE),
]

# Fresher / entry-level pattern with word boundaries (avoids 'intern' matching 'internal')
FRESHER_REGEX = re.compile(
    r'\b(?:fresher|freshers|entry[\s\-]level|graduate|intern|internship|junior|0\s*(?:-|to)\s*[12]\s*(?:years?|yrs?|yr)?)\b',
    re.IGNORECASE,
)

# High-seniority titles when explicitly part of the hiring role (skip if targeting <= 4 years)
LEADERSHIP_HIRING_REGEX = re.compile(
    r'\b(?:hiring|looking\s+for|seeking|role|position|opening(?:s)?\s+for)\b'
    r'[\s:\-]*(?:a\s+|an\s+|for\s+|the\s+)?(?:senior\s+|sr\.?\s+|lead\s+)?'
    r'(director|vp|vice\s+president|principal|staff\s+engineer|head\s+of|lead\s+architect|associate\s+director)\b',
    re.IGNORECASE,
)

# Detect fellow job-seekers (#opentowork) vs actual hiring posts
JOB_SEEKER_REGEX = re.compile(
    r'(?:#opentowork\b|\bopen\s+to\s+work\b|\bactively\s+looking\s+for\b|'
    r'\bseeking\s+(?:a\s+role|opportunities|new\s+opportunities|job)\b|'
    r'\blooking\s+for\s+(?:a\s+job|my\s+next\s+role|new\s+opportunities)\b|'
    r'\bplease\s+refer\s+me\b|\bhere\s+is\s+my\s+resume\b|\bavailable\s+immediately\b)',
    re.IGNORECASE,
)

HIRING_SIGNAL_REGEX = re.compile(
    r'(?:\bwe(?:\'re|\s+are)\s+hiring\b|\bhiring\s+(?:for|a|an)\b|\blooking\s+for\s+(?:a|an)\b|'
    r'\b(?:send|share|drop|email|mail)\s+(?:your|updated)\s+(?:resume|cv)\b|'
    r'\bjoin\s+our\s+team\b|\bjob\s+opening\b|\bopen\s+position\b)',
    re.IGNORECASE,
)

_KEYWORD_CACHE: tuple[tuple[str, ...], list[tuple[str, re.Pattern, str]]] | None = None


def _get_compiled_keywords() -> list[tuple[str, re.Pattern, str]]:
    """Compile and cache role keyword matchers for the active Config."""
    global _KEYWORD_CACHE
    raw = tuple(Config.TARGET_ROLE_KEYWORDS)
    if _KEYWORD_CACHE is not None and _KEYWORD_CACHE[0] == raw:
        return _KEYWORD_CACHE[1]

    compiled = []
    for kw in raw:
        kw_clean = kw.strip().rstrip(".,;").lower()
        if not kw_clean:
            continue
        kw_norm = re.sub(r"[/_\-&]+", " ", kw_clean).strip()
        kw_compact = re.sub(r"[\s/_\-&]+", "", kw_clean)
        pattern = re.compile(r"\b" + re.escape(kw_norm) + r"\b", re.IGNORECASE)
        compiled.append((kw_clean, pattern, kw_compact))

    _KEYWORD_CACHE = (raw, compiled)
    return compiled


def extract_required_experience(text: str) -> dict:
    """
    Extracts min and max years of experience mentioned in post text.
    Explicit numeric requirements take precedence over fresher keywords.
    Returns: {"min_years": float or None, "max_years": float or None, "is_fresher": bool}
    """
    found_mins = []
    found_maxs = []

    for pattern in EXPERIENCE_PATTERNS:
        matches = pattern.findall(text)
        for match in matches:
            if isinstance(match, tuple):
                # Group 1 = min, Group 2 = max (if present)
                val1 = match[0]
                val2 = match[1] if len(match) > 1 else ""

                if val1 and val1.isdigit():
                    num1 = float(val1)
                    # Filter out unreasonable years (e.g., 2024, 50, etc.)
                    if 0 <= num1 <= 20:
                        found_mins.append(num1)

                if val2 and val2.isdigit():
                    num2 = float(val2)
                    if 0 <= num2 <= 20:
                        found_maxs.append(num2)
            elif isinstance(match, str) and match.isdigit():
                num = float(match)
                if 0 <= num <= 20:
                    found_mins.append(num)

    min_val = min(found_mins) if found_mins else None
    max_val = max(found_maxs) if found_maxs else min_val

    is_fresher = False
    if FRESHER_REGEX.search(text):
        if min_val is None or min_val <= 1.0:
            return {"min_years": 0.0, "max_years": 1.0, "is_fresher": True}
        is_fresher = False

    return {
        "min_years": min_val,
        "max_years": max_val,
        "is_fresher": is_fresher,
    }


def is_job_relevant(post_text: str) -> tuple[bool, str]:
    """
    Checks if post matches:
    1. Target role keywords (DevOps, SRE, Cloud, Kubernetes, Terraform, CI/CD, etc.)
    2. Seniority title compatibility
    3. Target years of experience (<= Config.MAX_TARGET_EXPERIENCE)

    Returns: (is_relevant: bool, reason: str)
    """
    if not post_text or not post_text.strip():
        return False, "Empty post text"

    # ── 0. Skip candidate #opentowork self-promotion posts ────
    if JOB_SEEKER_REGEX.search(post_text) and not HIRING_SIGNAL_REGEX.search(post_text):
        return False, "Post appears to be a job seeker rather than a hiring post"

    # ── 1. Check Profile / Role Keyword Relevance ─────────────
    # Normalize punctuation (e.g. 'CI/CD' -> 'ci cd', 'Blue-Green' -> 'blue green')
    normalized_text = re.sub(r"[/_\-&]+", " ", post_text.lower())
    compact_text = re.sub(r"[\s/_\-&]+", "", post_text.lower())

    matched_keywords = []
    for kw_clean, pattern, kw_compact in _get_compiled_keywords():
        if pattern.search(normalized_text):
            matched_keywords.append(kw_clean)
        elif len(kw_compact) > 3 and kw_compact in compact_text:
            matched_keywords.append(kw_clean)

    if not matched_keywords:
        return False, "No matching profile keywords found in post"

    # ── 2. Check Leadership Title Mismatch ─────────────────────
    if Config.MAX_TARGET_EXPERIENCE <= 4:
        leadership_match = LEADERSHIP_HIRING_REGEX.search(post_text)
        if leadership_match:
            return False, f"Post requires senior leadership ({leadership_match.group(1)})"

    # ── 3. Check Years of Experience ──────────────────────────
    exp_info = extract_required_experience(post_text)

    if exp_info["min_years"] is not None:
        if exp_info["min_years"] > Config.MAX_TARGET_EXPERIENCE:
            return False, f"Requires {exp_info['min_years']}+ years exp (exceeds target of <= {Config.MAX_TARGET_EXPERIENCE} yrs)"

    return True, f"Matched keywords: {', '.join(matched_keywords[:3])} | Exp: <= {Config.MAX_TARGET_EXPERIENCE} yrs"
