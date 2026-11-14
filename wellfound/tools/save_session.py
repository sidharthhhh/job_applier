"""
wellfound/tools/save_session.py
────────────────────────────────────────────────────────
ONE-TIME SETUP: Save your Wellfound login session.

Run this script ONCE before using the main pipeline.
It opens a real browser window so you can log in manually.
Cookies are saved automatically — future runs are headless.

Usage:
    cd c:\\Users\\abhishek\\Documents\\linkedin_scrapper
    python wellfound\\tools\\save_session.py
────────────────────────────────────────────────────────
"""

import sys
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT         = Path(__file__).resolve().parent.parent.parent
SESSION_FILE = Path(__file__).resolve().parent.parent / "session" / "wf_cookies.json"
LOGIN_URL    = "https://wellfound.com/login"
JOBS_URL     = "https://wellfound.com/jobs"


def main():
    print("=" * 55)
    print("  Wellfound — One-Time Session Saver")
    print("=" * 55)
    print(f"\n  Cookies will be saved to:")
    print(f"  {SESSION_FILE}\n")
    print("  Steps:")
    print("  1. A Chrome browser will open")
    print("  2. Log in to Wellfound manually")
    print("  3. Once you see the jobs page, come back here")
    print("  4. Press ENTER — cookies are saved automatically")
    print("\n" + "=" * 55)
    input("\n  Press ENTER to open the browser...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
            ]
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )
        # Hide webdriver flag
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        page = context.new_page()
        page.goto(LOGIN_URL)

        print("\n  [Browser opened] — Log in to Wellfound now.")
        print("  After you see the jobs/feed page, press ENTER here.\n")
        input("  Press ENTER after you are logged in...")

        # Verify logged in
        current_url = page.url
        print(f"\n  Current URL: {current_url}")

        if "login" in current_url.lower():
            print("\n  WARNING: Still on login page. Are you sure you're logged in?")
            confirm = input("  Save anyway? (y/n): ").strip().lower()
            if confirm != "y":
                print("  Cancelled. Run again after logging in.")
                browser.close()
                return

        # Save cookies
        cookies = context.cookies()
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(json.dumps(cookies, indent=2))

        print(f"\n  Saved {len(cookies)} cookies to: {SESSION_FILE.name}")
        print("\n  Test: Navigating to jobs page to verify session...")
        time.sleep(1)
        page.goto(JOBS_URL, wait_until="load", timeout=30000)
        time.sleep(3)

        final_url = page.url
        if "login" not in final_url:
            print("  Session verified! You are logged in.")
            print("\n  DONE. You can now run the main pipeline:")
            print("  python wellfound\\main.py")
        else:
            print("  Session verification failed — try again.")

        browser.close()


if __name__ == "__main__":
    main()
