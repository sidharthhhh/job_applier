"""
tools/export_cookies.py
─────────────────────────────────────────────────────────────
BACKUP LOGIN METHOD — Use this if the main pipeline login needs manual help.

How to use:
  1. Run this script:
        python tools/export_cookies.py
  2. Login to LinkedIn in the Playwright Chrome window that opens
  3. Make sure you can see your LinkedIn feed, then press ENTER in the terminal
  4. Cookies are saved to session/cookies.json
  5. Then run: python main.py  (login will be skipped automatically!)
─────────────────────────────────────────────────────────────
"""

import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SESSION_DIR  = os.path.join(os.path.dirname(__file__), "..", "session")
COOKIE_FILE  = os.path.join(SESSION_DIR, "cookies.json")


def export_via_playwright() -> bool:
    """
    Better method: Open Playwright with real Chrome, you login once,
    cookies are captured automatically.
    This is the most reliable approach.
    """
    print("\n" + "=" * 55)
    print("COOKIE EXPORT VIA PLAYWRIGHT + REAL CHROME")
    print("=" * 55)
    print("This will open a Chrome window.")
    print("Login to LinkedIn, then come back here and press ENTER.")
    print("=" * 55 + "\n")

    try:
        from playwright.sync_api import sync_playwright
        import time

        os.makedirs(SESSION_DIR, exist_ok=True)
        profile_dir = os.path.join(SESSION_DIR, "chrome_profile")
        os.makedirs(profile_dir, exist_ok=True)

        with sync_playwright() as p:
            launch_kwargs = {
                "user_data_dir": profile_dir,
                "headless": False,
                "args": ["--disable-blink-features=AutomationControlled", "--start-maximized"],
                "viewport": {"width": 1440, "height": 900},
                "locale": "en-US",
                "timezone_id": "Asia/Kolkata",
            }
            try:
                context = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
                print("[✓] Using persistent real Chrome profile")
            except Exception:
                context = p.chromium.launch_persistent_context(**launch_kwargs)
                print("[!] Using persistent Chromium profile (Chrome not found)")

            context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });")
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

            # Inject banner
            try:
                page.evaluate("""
                    const b = document.createElement('div');
                    b.style.cssText = 'position:fixed;top:0;left:0;width:100%;background:#006400;color:white;font-size:18px;font-weight:bold;text-align:center;padding:12px;z-index:999999;';
                    b.textContent = '✅ LOGIN HERE — Cookie Export Tool — Login then press ENTER in terminal';
                    document.body.prepend(b);
                """)
            except Exception:
                pass

            print("\nBrowser opened. Login to LinkedIn in that window.")
            print("Once on your LinkedIn FEED, press ENTER here.\n")
            input("Press ENTER after you see your LinkedIn feed → ")

            # Save cookies
            cookies = context.cookies()
            linkedin_cookies = [c for c in cookies if "linkedin" in c.get("domain", "")]

            if not linkedin_cookies:
                print("❌ No LinkedIn cookies found. Make sure you logged in.")
                context.close()
                return False

            with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                json.dump(linkedin_cookies, f, indent=2)

            context.close()
            print(f"\n✅ {len(linkedin_cookies)} LinkedIn cookies saved to:")
            print(f"   {COOKIE_FILE} (+ persistent profile: {profile_dir})")
            print("\n✅ Now run: python main.py")
            print("   Login step will be skipped automatically!")
            return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 55)
    print("  LinkedIn Cookie Export Tool")
    print("  Backup login method for job_applier")
    print("=" * 55)

    success = export_via_playwright()
    if not success:
        print("\n❌ Export failed. Please try running main.py directly.")
        sys.exit(1)
