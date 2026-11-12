"""
main.py - Master Pipeline Orchestrator
LinkedIn Post Scraper → Email Extractor → MongoDB Dedup → Ollama AI → SMTP Sender

Run: python main.py
"""

import argparse
import sys
import os
import time
from datetime import datetime

# ── Setup path ─────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from database.mongo_handler import MongoHandler
from scraper.session_manager import get_authenticated_browser
from scraper.linkedin_scraper import run_scraper
from scraper.email_extractor import extract_emails_from_posts
from ai.llm_handler import (
    check_llm_status,
    generate_email_body,
    generate_email_content,
    generate_subject_line,
)
from ai.relevance_filter import is_job_relevant
from mailer.email_verifier import verify_email, is_personal_email
from mailer.smtp_handler import SMTPHandler


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════╗
║        LinkedIn AI Job Application Automator             ║
║        Scrape → Extract → Deduplicate → AI Email → Send  ║
╚══════════════════════════════════════════════════════════╝
    """)


def print_mode_banner(scrape_mode: bool):
    if scrape_mode:
        print("""
┌──────────────────────────────────────────────────────────┐
│  🟢 MODE: FULL PIPELINE                                  │
│     LinkedIn Scrape ➜ Extract ➜ AI Email ➜ Send        │
└──────────────────────────────────────────────────────────┘""")
    else:
        print("""
┌──────────────────────────────────────────────────────────┐
│  🟡 MODE: EMAIL-ONLY (MongoDB Backlog)                   │
│     Skipping scrape ➜ Using saved emails ➜ AI Email ➜ Send│
└──────────────────────────────────────────────────────────┘""")


def print_step(step: int, title: str):
    print(f"\n{'='*55}")
    print(f"  STEP {step}: {title}")
    print(f"{'='*55}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse optional CLI overrides for dry-run and scrape mode."""
    parser = argparse.ArgumentParser(description="LinkedIn AI Job Application Automator")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run scraping, filtering, verification, and AI drafting without sending SMTP emails",
    )
    parser.add_argument(
        "--test-smtp",
        action="store_true",
        help="Test SMTP login/connection with current .env settings and exit",
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--email-only",
        action="store_true",
        help="Skip LinkedIn scraping and process the existing MongoDB backlog",
    )
    mode_group.add_argument(
        "--scrape",
        action="store_true",
        help="Force full scraping + email pipeline regardless of SCRAPE_MODE in .env",
    )
    return parser.parse_args(argv)


def run_pipeline():
    """Main pipeline execution"""
    print_banner()
    print_mode_banner(Config.SCRAPE_MODE)
    if Config.DRY_RUN:
        print("  🧪 DRY RUN ENABLED — Emails will be drafted and previewed, NOT sent.\n")
    start_time = datetime.now()

    # ── Validate Config ────────────────────────────────────
    print("[Init] Validating configuration...")
    try:
        Config.validate()
        Config.display()
    except ValueError as e:
        print(f"\n{e}")
        sys.exit(1)

    # ── Check AI Provider Status ───────────────────────────
    print(f"\n[Init] Checking AI provider ({Config.AI_PROVIDER})...")
    llm_status = check_llm_status()
    if llm_status["running"]:
        print(
            f"[Init] ✅ {Config.AI_PROVIDER.upper()} ready | "
            f"Model '{llm_status['configured_model']}' available: {llm_status['model_available']} "
            f"({llm_status.get('note', '')})"
        )
        if not llm_status["model_available"] and llm_status.get("available_models"):
            print(f"[Init] ⚠️  Available models: {llm_status['available_models']}")
    else:
        print(f"[Init] ⚠️  {llm_status.get('note', 'AI provider unavailable')}.")

    fb_status = llm_status.get("fallback")
    if fb_status:
        fb_name = fb_status["provider"].upper()
        if fb_status["running"]:
            print(
                f"[Init] 🔁 Fallback {fb_name} ready | "
                f"Model '{fb_status['configured_model']}' available: {fb_status['model_available']}"
            )
        else:
            print(f"[Init] ⚠️  Fallback {fb_name} not ready ({fb_status.get('note', '')}) — DevOps templates will be used if primary fails.")
    elif not llm_status["running"]:
        print("[Init] ℹ️  Will use DevOps fallback email templates.")

    # ── Connect to MongoDB ─────────────────────────────────
    print("\n[Init] Connecting to MongoDB...")
    db = MongoHandler()

    # ── Track totals for summary (initialized here so always defined) ──────
    all_posts = []
    email_records = []
    newly_saved_emails: set[str] = set()

    if Config.SCRAPE_MODE:
        # ─────────────────────────────────────────────────────────
        # STEP 1: Scrape LinkedIn Posts
        # ─────────────────────────────────────────────────────────
        print_step(1, "SCRAPE LINKEDIN POSTS")

        playwright, browser, context, page = get_authenticated_browser()
        try:
            all_posts = run_scraper(page)
        finally:
            browser.close()
            playwright.stop()

        if not all_posts:
            print("\n[Pipeline] ⚠️  No posts scraped — falling through to MongoDB backlog...")

        # Save posts to MongoDB
        new_posts = 0
        for post in all_posts:
            if db.save_post(post):
                new_posts += 1
        if all_posts:
            print(f"[Pipeline] 💾 Saved {new_posts} new posts to MongoDB ({len(all_posts) - new_posts} duplicates skipped)")

        # ─────────────────────────────────────────────────────────
        # STEP 2: Filter by Relevancy & Experience Level
        # ─────────────────────────────────────────────────────────
        print_step(2, "FILTER BY RELEVANCY & EXPERIENCE")
        print(f"[Filter] Target Keywords: {', '.join(Config.TARGET_ROLE_KEYWORDS[:5])}...")
        print(f"[Filter] Maximum Target Exp: <= {Config.MAX_TARGET_EXPERIENCE} years")

        relevant_posts = []
        skipped_count = 0
        for post in all_posts:
            text = post.get("post_text", "")
            is_rel, reason = is_job_relevant(text)
            if is_rel:
                relevant_posts.append(post)
            else:
                skipped_count += 1

        print(f"[Filter] 🎯 {len(relevant_posts)} relevant posts kept | {skipped_count} skipped")

        # ─────────────────────────────────────────────────────────
        # STEP 3: Extract Email Addresses
        # ─────────────────────────────────────────────────────────
        print_step(3, "EXTRACT EMAIL ADDRESSES")

        if relevant_posts:
            email_records = extract_emails_from_posts(relevant_posts)
            new_emails = 0
            for record in email_records:
                if db.save_email(record):
                    new_emails += 1
                    newly_saved_emails.add(record["email"].lower().strip())
            print(f"[Pipeline] 💾 {new_emails} new emails saved | {len(email_records) - new_emails} already in DB")
        else:
            print("[Pipeline] ℹ️  No relevant posts found in this scrape.")

    else:
        # ─────────────────────────────────────────────────────────
        # SCRAPE_MODE = false → skip Steps 1-3 entirely
        # ─────────────────────────────────────────────────────────
        print("\n[Pipeline] ⏭️  SCRAPE_MODE=false — Skipping Steps 1-3 (no browser launched)")
        print("[Pipeline] 📂 Loading unsent pending emails from MongoDB backlog...")

    # ─────────────────────────────────────────────────────────
    # STEP 4: Filter via MongoDB (Newly Scraped / Pending Only)
    # ─────────────────────────────────────────────────────────
    print_step(4, "FILTER NEWLY SCRAPED / PENDING EMAILS")

    if Config.SCRAPE_MODE:
        if not newly_saved_emails:
            print("[Pipeline] ℹ️  No new emails scraped in this run (skipping already-saved emails in DB).")
            print("[Pipeline]    Run with --email-only if you want to send unsent pending backlog.")
            db.close()
            return
        pending_emails = db.get_pending_emails(only_emails=newly_saved_emails)
        print(f"[Pipeline] 🆕 {len(pending_emails)} newly scraped email(s) queued (saved DB backlog skipped)")
    else:
        pending_emails = db.get_pending_emails()

    if not pending_emails:
        print("[Pipeline] ✅ No unsent pending emails to process.")
        db.close()
        return

    # ─────────────────────────────────────────────────────────
    # STEP 5: Validate Email Addresses (DNS MX & Anti-Bounce Check)
    # ─────────────────────────────────────────────────────────
    print_step(5, "VERIFY RECIPIENT EMAILS (DNS & MX RECORDS)")

    sent_today = db.get_sent_count_today()
    remaining_quota = max(0, Config.MAX_EMAILS_PER_DAY - sent_today)
    if remaining_quota == 0:
        print(f"[Pipeline] ⚠️  Daily limit already reached ({sent_today}/{Config.MAX_EMAILS_PER_DAY} sent today). Stopping.")
        db.close()
        return

    verified_emails = []
    for record in pending_emails:
        target_email = record.get("email", "")

        if Config.SKIP_PERSONAL_EMAILS and is_personal_email(target_email):
            print(f"[Verifier] ⏭️  Skipping personal email (SKIP_PERSONAL_EMAILS=true): {target_email}")
            continue

        is_valid, reason = verify_email(target_email)
        if is_valid:
            verified_emails.append(record)
            print(f"[Verifier] ✅ {target_email} -> Active Mail Server confirmed")
            if len(verified_emails) >= remaining_quota:
                break
        else:
            print(f"[Verifier] ⚠️  Skipping {target_email}: {reason}")
            db.mark_email_invalid(target_email, reason)

    if not verified_emails:
        print("[Pipeline] ⚠️  No valid emails with active mail servers found. Stopping.")
        db.close()
        return

    print(f"[Pipeline] 🎯 {len(verified_emails)} verified emails ready to send (remaining daily quota: {remaining_quota})")

    # ─────────────────────────────────────────────────────────
    # STEP 6: Generate AI Emails
    # ─────────────────────────────────────────────────────────
    model_map = {
        "bedrock": Config.BEDROCK_MODEL_ID,
        "gemini": Config.GEMINI_MODEL,
        "ollama": Config.OLLAMA_MODEL,
    }
    active_model = model_map.get(Config.AI_PROVIDER, Config.BEDROCK_MODEL_ID)
    fb_label = f" | FALLBACK: {Config.AI_FALLBACK_PROVIDER.upper()}" if Config.AI_FALLBACK_PROVIDER not in ("", "none", Config.AI_PROVIDER) else ""
    print_step(6, f"GENERATE EMAILS WITH {Config.AI_PROVIDER.upper()} ({active_model}){fb_label}")

    email_queue = []
    for i, record in enumerate(verified_emails, 1):
        print(f"\n[{Config.AI_PROVIDER.upper()}] [{i}/{len(verified_emails)}] Generating email for: {record['email']}")

        post_text = record.get("post_text", f"{Config.YOUR_ROLE} job opportunity")
        company = record.get("company", "")

        subject, body = generate_email_content(post_text, company)

        email_queue.append({
            "email": record["email"],
            "subject": subject,
            "body": body,
            "post_url": record.get("post_url", ""),
            "company": company,
        })

        # Local Ollama benefits from brief cooldown; Bedrock pacing is managed in llm_handler
        if Config.AI_PROVIDER == "ollama" and i < len(verified_emails):
            time.sleep(2.0)

    # ─────────────────────────────────────────────────────────
    # STEP 7: Send Emails via SMTP (or Preview in Dry Run)
    # ─────────────────────────────────────────────────────────
    if Config.DRY_RUN:
        print_step(7, "DRY RUN PREVIEW (SMTP SKIPPED)")
        for i, item in enumerate(email_queue, 1):
            print(f"\n[DryRun] [{i}/{len(email_queue)}] To: {item['email']}")
            print(f"[DryRun] Subject: {item['subject']}")
            print(f"[DryRun] Body preview: {item['body'][:220].replace(chr(10), ' ')}...")
        results = [{"email": item["email"], "status": "dry_run"} for item in email_queue]
        print_step(8, "LOG RESULTS TO MONGODB (SKIPPED IN DRY RUN)")
    else:
        print_step(7, "SEND EMAILS VIA SMTP")

        mailer = SMTPHandler()

        # Test connection first
        if not mailer.test_connection():
            print("[Pipeline] ❌ SMTP connection failed. Check your .env SMTP settings.")
            db.close()
            return

        results = []

        def _persist_result(item: dict, result: dict):
            results.append(result)
            if result["status"] == "sent":
                db.log_sent_email(
                    email=result["email"],
                    subject=item.get("subject", ""),
                    body=item.get("body", ""),
                    post_url=result.get("post_url", ""),
                    company=result.get("company", ""),
                )
            elif result["status"] == "failed":
                if result.get("permanent_failure"):
                    db.update_email_status(result["email"], "bounced")
                else:
                    print(f"[Pipeline] ⚠️  Transient send failure for {result['email']} — keeping pending for retry")

        try:
            mailer.send_batch(email_queue, on_result=_persist_result)
        except KeyboardInterrupt:
            print("\n[Pipeline] ⚠️  Batch interrupted — already-sent emails were saved to MongoDB.")

        # ─────────────────────────────────────────────────────────
        # STEP 8: Log Results to MongoDB (Persisted per email above)
        # ─────────────────────────────────────────────────────────
        print_step(8, "MONGODB SYNC COMPLETE")

    # ─────────────────────────────────────────────────────────
    # FINAL SUMMARY
    # ─────────────────────────────────────────────────────────
    elapsed = int((datetime.now() - start_time).total_seconds())
    stats = db.get_stats()

    mode_str = "🟢 FULL PIPELINE" if Config.SCRAPE_MODE else "🟡 EMAIL-ONLY MODE"
    posts_scraped_display = len(all_posts) if Config.SCRAPE_MODE else "(skipped)"
    emails_extracted_display = len(email_records) if Config.SCRAPE_MODE else "(skipped)"

    print(f"""
╔══════════════════════════════════════════════════════════╗
║                   PIPELINE COMPLETE ✅                   ║
╠══════════════════════════════════════════════════════════╣
║  Run Mode               : {mode_str:<30}║
║  Posts Scraped Today    : {str(posts_scraped_display):<30}║
║  Emails Extracted       : {str(emails_extracted_display):<30}║
║  Emails Sent Today      : {sum(1 for r in results if r['status']=='sent'):<30}║
║  Failed                 : {sum(1 for r in results if r['status']=='failed'):<30}║
╠══════════════════════════════════════════════════════════╣
║  ALL TIME STATS                                          ║
║  Total Posts in DB      : {stats['total_posts_scraped']:<30}║
║  Total Emails in DB     : {stats['total_emails_extracted']:<30}║
║  Total Sent             : {stats['total_sent']:<30}║
║  Replies Received       : {stats['replied']:<30}║
║  Reply Rate             : {stats['reply_rate']:<30}║
╠══════════════════════════════════════════════════════════╣
║  Time Taken             : {f"{elapsed}s":<30}║
╚══════════════════════════════════════════════════════════╝
    """)

    db.close()


if __name__ == "__main__":
    args = parse_args()
    if args.test_smtp:
        try:
            Config.validate()
        except ValueError as e:
            print(f"\n{e}")
            sys.exit(1)
        ok = SMTPHandler().test_connection()
        sys.exit(0 if ok else 1)
    if args.dry_run:
        Config.DRY_RUN = True
    if args.email_only:
        Config.SCRAPE_MODE = False
    elif args.scrape:
        Config.SCRAPE_MODE = True
    run_pipeline()
