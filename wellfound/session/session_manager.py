"""
wellfound/session/session_manager.py
Session management for Wellfound.
Handles cookie saving/loading and authentication.
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION_DIR = Path(__file__).resolve().parent
SESSION_FILE = SESSION_DIR / "wf_cookies.json"
LOGIN_URL = "https://wellfound.com/login"
JOBS_URL = "https://wellfound.com/jobs"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def get_authenticated_browser(email: str = "", password: str = "", headless: bool = True):
    """
    Launches browser and authenticates with Wellfound.
    Returns: (playwright, browser, context, page)
    """
    playwright = sync_playwright().start()

    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    )

    context = browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="en-US",
        timezone_id="Asia/Kolkata",
    )

    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)

    # 1. Try saved cookies
    if SESSION_FILE.exists():
        try:
            cookies = json.loads(SESSION_FILE.read_text())
            context.add_cookies(cookies)
            print(f"[Wellfound Session] Loaded {len(cookies)} saved cookies from {SESSION_FILE.name}")
        except Exception as e:
            print(f"[Wellfound Session] ⚠️ Could not load cookies: {e}")

    page = context.new_page()

    # 2. Verify login by navigating to jobs page
    try:
        page.goto(JOBS_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        if "login" not in page.url.lower():
            print("[Wellfound Session] ✅ Authenticated via existing session!")
            return playwright, browser, context, page
    except Exception as e:
        print(f"[Wellfound Session] ⚠️ Session check error: {e}")

    # 3. If not logged in and credentials provided, attempt automated login
    print("[Wellfound Session] ⚠️ Not logged in or session expired.")
    if email and password:
        print(f"[Wellfound Session] Attempting login with {email}...")
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            page.fill('input[type="email"], input[name="user[email]"], #user_email', email)
            page.fill('input[type="password"], input[name="user[password]"], #user_password', password)
            page.click('button[type="submit"], input[type="submit"]')
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            time.sleep(3)

            if "login" not in page.url.lower():
                cookies = context.cookies()
                SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                SESSION_FILE.write_text(json.dumps(cookies, indent=2))
                print(f"[Wellfound Session] ✅ Logged in and saved {len(cookies)} cookies to {SESSION_FILE.name}")
                return playwright, browser, context, page
        except Exception as err:
            print(f"[Wellfound Session] Automated login attempt error: {err}")

    # If headless is True and not logged in, warn user to run save_session.py
    if headless:
        print("[Wellfound Session] ❌ Headless session not authenticated.")
        print("[Wellfound Session] 💡 Tip: Run 'python wellfound/tools/save_session.py' in visible mode first.")

    return playwright, browser, context, page
