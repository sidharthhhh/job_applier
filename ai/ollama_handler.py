"""
ai/ollama_handler.py
Backward-compatible wrapper re-exporting from ai/llm_handler.py.
"""

from ai.llm_handler import (  # noqa: F401
    BODY_PROMPT,
    COMBINED_PROMPT,
    SPAM_WORDS,
    SUBJECT_PROMPT,
    TECH_ACRONYMS,
    check_bedrock_status,
    check_gemini_status,
    check_llm_status,
    check_ollama_status,
    check_spam_score,
    clean_email_body,
    clean_subject,
    generate_email_body,
    generate_email_content,
    generate_subject_line,
)
