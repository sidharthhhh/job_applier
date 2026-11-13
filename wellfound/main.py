"""
wellfound/main.py
─────────────────────────────────────────────────────────────────
Wellfound Job Application Automator
Scrape → Filter → Auto-Apply (native) + Email (from descriptions)
─────────────────────────────────────────────────────────────────

Pipeline Modes (set WF_SCRAPE_MODE in .env):
  true  → Scrape Wellfound → Filter → Auto-Apply → Extract emails → Send
  false → Skip scrape     → Load MongoDB backlog → AI email → Send

Usage:
  cd wellfound
  python main.py
"""

import sys
import time
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure UTF-8 output to prevent Windows cp1252 charmap encoding errors
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Path setup (resolve shared modules) ─────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wellfound.config import WellfoundConfig as Config
from wellfound.session.session_manager import get_authenticated_browser
from wellfound.scraper.job_scraper import scrape_wellfound_jobs
from wellfound.scraper.auto_apply import auto_apply_to_job
from wellfound.database.mongo_handler import WellfoundMongoHandler

# Reuse shared AI + mailer modules
from ai.ollama_handler import (
    generate_email_body,
    generate_subject_line,
    check_ollama_status,
)
from mailer.smtp_handler import SMTPHandler
from mailer.email_verifier import verify_email


# ── Helpers ──────────────────────────────────────────────────────
def print_banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║        Wellfound AI Job Application Automator            ║
║        Scrape → Filter → Auto-Apply + Email → Send       ║
╚══════════════════════════════════════════════════════════╝
    """)


def print_step(n: int, label: str):
    print(f"\n{'=' * 55}")
    print(f"  STEP {n}: {label}")
    print(f"{'=' * 55}")


def print_mode_banner(scrape_mode: bool):
    if scrape_mode:
        print("┌─────────────────────────────────────────────────────┐")
        print("│  🟢 MODE: FULL PIPELINE                             │")
        print("│     Scrape ➜ Filter ➜ Auto-Apply ➜ AI Email         │")
        print("└─────────────────────────────────────────────────────┘")
    else:
        print("┌─────────────────────────────────────────────────────┐")
        print("│  🟡 MODE: BACKLOG MODE (MongoDB Jobs)               │")
        print("│     Skip Scrape ➜ Apply to Saved Jobs ➜ AI Email    │")
        print("└─────────────────────────────────────────────────────┘")


def is_job_relevant(job: dict) -> tuple[bool, str]:
    """
    Filter job by keyword relevance and experience range.
    Returns (is_relevant, reason).
    """
    text = (
        (job.get("title") or "") + " " +
        (job.get("description") or "")
    ).lower()

    # Keyword check
    matched = [kw for kw in Config.TARGET_ROLE_KEYWORDS if kw.lower() in text]
    if not matched:
        return False, "No target keywords matched"

    # Experience check
    min_exp = job.get("min_exp", 0)
    max_exp = job.get("max_exp", 99)
    if min_exp > Config.MAX_TARGET_EXPERIENCE:
        return False, f"Min exp {min_exp}y > target {Config.MAX_TARGET_EXPERIENCE}y"

    return True, f"Matched: {matched[:3]}"


# ── Main Pipeline ─────────────────────────────────────────────────
def run_pipeline():
    print_banner()
    print_mode_banner(Config.SCRAPE_MODE)
    start_time = datetime.now()

    # Validate config
    Config.display()
    if not Config.validate():
        print("\n[Pipeline] ❌ Fix config errors above and retry.")
        return

    # Ollama check
    print("\n[Init] Checking Ollama status...")
    ollama = check_ollama_status()
    if not ollama["running"]:
        print(f"[Init] ❌ Ollama not reachable at {Config.OLLAMA_BASE_URL}")
        return
    if not ollama["model_available"]:
        print(f"[Init] ❌ Model '{Config.OLLAMA_MODEL}' not found in Ollama")
        return
    print(f"[Init] ✅ Ollama running | Model '{Config.OLLAMA_MODEL}' available")

    # MongoDB
    print("\n[Init] Connecting to MongoDB...")
    db = WellfoundMongoHandler(
        uri=Config.MONGO_URI,
        db_name=Config.MONGO_DB,
        jobs_col=Config.WF_JOBS_COLLECTION,
        applied_col=Config.WF_APPLIED_COLLECTION,
        emails_col=Config.WF_EMAILS_COLLECTION,
        sent_col=Config.WF_SENT_COLLECTION,
    )
    db.clean_false_already_applied()

    all_jobs:    list[dict] = []
    apply_results: list[dict] = []

    # ── STEP 1: Job Discovery (Scrape or Load from MongoDB) ───────
    if Config.SCRAPE_MODE:
        print_step(1, "SCRAPE WELLFOUND JOB LISTINGS")
        playwright, browser, context, page = get_authenticated_browser(
            Config.EMAIL, Config.PASSWORD, Config.HEADLESS
        )
        try:
            all_jobs = scrape_wellfound_jobs(
                page,
                role_slugs=Config.ROLE_SLUGS,
                location_slug=Config.LOCATION_SLUG,
            )
        finally:
            browser.close()
            playwright.stop()

        if not all_jobs:
            print("[Pipeline] ⚠️  No jobs scraped — falling back to MongoDB backlog...")
            all_jobs = list(db.jobs.find({}))
        else:
            # Save to MongoDB
            new_jobs = sum(1 for j in all_jobs if db.save_job(j))
            print(f"[Pipeline] 💾 {new_jobs} new jobs saved ({len(all_jobs) - new_jobs} duplicates)")
    else:
        print_step(1, "LOAD JOBS FROM MONGODB (SCRAPING SKIPPED)")
        print("\n[Pipeline] ⏭️  WF_SCRAPE_MODE=false — Skipping web scrape")
        all_jobs = list(db.jobs.find({}))
        print(f"[Pipeline] 📂 Loaded {len(all_jobs)} existing jobs from MongoDB backlog")

    if not all_jobs:
        print("[Pipeline] ⚠️  No jobs found in MongoDB backlog. Set WF_SCRAPE_MODE=true to scrape new jobs.")
        db.close()
        return

    # ── STEP 2: Relevance Filter ─────────────────────────────
    print_step(2, "FILTER BY RELEVANCY & EXPERIENCE")
    relevant, skipped = [], 0
    for j in all_jobs:
        ok, reason = is_job_relevant(j)
        if ok:
            relevant.append(j)
        else:
            skipped += 1

    # Check already-applied status for clarity
    applied_cutoff = datetime.now(timezone.utc) - timedelta(days=Config.APPLY_COOLDOWN_DAYS)
    already_applied_ids = set(
        d["job_id"] for d in db.applied.find(
            {
                "status": {"$in": ["applied", "already_applied", "external_ats", "closed", "ineligible"]},
                "applied_at": {"$gte": applied_cutoff}
            },
            {"job_id": 1}
        )
    )
    relevant_ids = {j.get("job_id") for j in relevant}
    already_done = len(relevant_ids.intersection(already_applied_ids))
    pending_new  = len(relevant) - already_done

    print(f"[Filter] 🎯 {len(relevant)} jobs match your profile keywords ({skipped} skipped)")
    print(f"[Filter] 📊 Breakdown: {already_done} already handled | {pending_new} pending new application")

    # ── STEP 3: Auto-Apply (native Wellfound) ────────────────
    if Config.AUTO_APPLY and relevant:
        print_step(3, f"AUTO-APPLY TO WELLFOUND JOBS (max {Config.MAX_APPLIES_PER_DAY}/day)")
        jobs_to_apply = db.get_jobs_not_applied(Config.APPLY_COOLDOWN_DAYS)
        pending = [j for j in jobs_to_apply
                   if j.get("job_id") in relevant_ids][:Config.MAX_APPLIES_PER_DAY]

        if pending:
            print(f"[Apply] 📋 {len(pending)} jobs queued for application (out of {pending_new} remaining)")
            playwright2, browser2, context2, page2 = get_authenticated_browser(
                Config.EMAIL, Config.PASSWORD, Config.HEADLESS
            )
            applied_count, external_count, ineligible_count = 0, 0, 0
            try:
                for i, job in enumerate(pending, 1):
                    try:
                        title_clean   = job.get("title", "")
                        company_clean = job.get("company", "")
                        print(f"[Apply] [{i}/{len(pending)}] {title_clean} @ {company_clean}")
                        result = auto_apply_to_job(
                            page2, job,
                            Config.YOUR_NAME, Config.YOUR_ROLE,
                            Config.YOUR_SKILLS, Config.YOUR_EXPERIENCE,
                            Config.OLLAMA_BASE_URL, Config.OLLAMA_MODEL,
                            Config.APPLY_NOTE_MAX_WORDS,
                            your_mobile=Config.YOUR_MOBILE,
                            your_linkedin=Config.YOUR_LINKEDIN,
                            your_github=Config.YOUR_GITHUB,
                        )
                        db.save_application(result)

                        if result["status"] == "applied":
                            print(f"[Apply] ✅ Applied: {result['message']}")
                            applied_count += 1
                        elif result["status"] == "external_ats":
                            print(f"[Apply] 🔗 External ATS → {result['message'][:80]}")
                            external_count += 1
                        elif result["status"] == "ineligible":
                            print(f"[Apply] 🚫 Ineligible — {result['message'][:80]}")
                            ineligible_count += 1
                        elif result["status"] == "already_applied":
                            print(f"[Apply] ⏭️  Already applied — skipping")
                        elif result["status"] == "closed":
                            print(f"[Apply] 🔒 Job Closed — {result['message']}")
                        else:
                            print(f"[Apply] ❌ Failed: {result['message']}")

                        apply_results.append(result)
                    except Exception as loop_err:
                        print(f"[Apply] ⚠️  Error on job {i}: {loop_err}")

                    time.sleep(random.uniform(Config.DELAY_BETWEEN_ACTIONS,
                                             Config.DELAY_BETWEEN_ACTIONS + 2))
            finally:
                browser2.close()
                playwright2.stop()

            print(f"\n[Apply] 🏁 Applied: {applied_count} | External ATS: {external_count} | Ineligible: {ineligible_count}")
        else:
            print("[Apply] ✅ All relevant jobs already applied or on cooldown!")
    elif not Config.AUTO_APPLY:
        print("\n[Apply] ⏭️  WF_AUTO_APPLY=false — Skipping native apply step")

    # ── STEP 4: Extract Emails from Descriptions ─────────────
    print_step(4, "EXTRACT RECRUITER EMAILS FROM JOB DESCRIPTIONS")
    email_records_new = 0
    for job in relevant:
        for em in job.get("emails", []):
            record = {
                "email":       em,
                "company":     job.get("company", ""),
                "job_title":   job.get("title", ""),
                "post_text":   job.get("description", "")[:1500],
                "source":      "wellfound",
                "apply_url":   job.get("apply_url", ""),
            }
            if db.save_email(record):
                email_records_new += 1
    print(f"[Pipeline] 💾 {email_records_new} new recruiter emails saved to MongoDB")

    # ── STEP 5: DNS Verify Emails ─────────────────────────────────
    print_step(5, "VERIFY RECIPIENT EMAILS (DNS & MX RECORDS)")
    pending_emails = db.get_pending_emails(Config.EMAIL_COOLDOWN_DAYS)

    if not pending_emails:
        print(f"[Pipeline] ✅ No new emails to send (all on {Config.EMAIL_COOLDOWN_DAYS}-day cooldown)")
        _print_summary(start_time, all_jobs, apply_results, [], 0, db)
        db.close()
        return

    verified = []
    for rec in pending_emails:
        em = rec.get("email", "")
        ok, _ = verify_email(em)
        if ok:
            print(f"[Verifier] ✅ {em} → Active Mail Server confirmed")
            verified.append(rec)
        else:
            print(f"[Verifier] ❌ {em} → MX not found — skipped")

    print(f"[Pipeline] 🎯 {len(verified)} verified emails ready to send")

    # ── STEP 6: AI Email Generation + Send ───────────────────────
    print_step(6, f"GENERATE EMAILS WITH OLLAMA ({Config.OLLAMA_MODEL.upper()})")
    to_send    = verified[:Config.MAX_EMAILS_PER_DAY]
    sent_count = 0
    mailer     = SMTPHandler()

    for i, rec in enumerate(to_send, 1):
        email   = rec["email"]
        company = rec.get("company", "")
        post    = rec.get("post_text", "")

        print(f"\n[Ollama] [{i}/{len(to_send)}] Generating email for: {email}")
        body    = generate_email_body(post, company)
        subject = generate_subject_line(post, company)

        # ── STEP 7: Send ─────────────────────────────────────────
        result = mailer.send_email(
            to_email=email,
            subject=subject,
            body=body,
        )

        if result.get("status") == "sent":
            db.log_sent_email(email, subject, company)
            sent_count += 1
            print(f"[Mailer] ✅ Sent → {email}")
        else:
            print(f"[Mailer] ❌ Failed → {email} | {result.get('error', '')}")

        time.sleep(random.uniform(3, 6))

    _print_summary(start_time, all_jobs, apply_results, to_send, sent_count, db)
    db.close()


def _print_summary(start_time, all_jobs, apply_results, emails_sent_list,
                   sent_count, db):
    elapsed = datetime.now() - start_time
    stats   = db.stats()
    applied_ok  = sum(1 for r in apply_results if r.get("status") == "applied")
    external    = sum(1 for r in apply_results if r.get("status") == "external_ats")

    print(f"""
{'=' * 55}
  ✅ WELLFOUND PIPELINE COMPLETE
{'=' * 55}
  Jobs Scraped     : {len(all_jobs)}
  Native Applied   : {applied_ok}
  External ATS     : {external}
  Emails Sent      : {sent_count}
  Time Elapsed     : {str(elapsed).split('.')[0]}
─────────────────────────────────────
  DB: Total Jobs   : {stats['total_jobs_scraped']}
  DB: Total Applied: {stats['total_applied']}
  DB: Emails Found : {stats['total_emails_found']}
  DB: Emails Sent  : {stats['total_emails_sent']}
{'=' * 55}
""")


if __name__ == "__main__":
    run_pipeline()
