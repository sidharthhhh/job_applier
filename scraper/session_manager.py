"""
scraper/session_manager.py
Cookie-based LinkedIn authentication with FULL human-like behavior.
Maximum stealth — LinkedIn cannot distinguish from real user.
"""

import json
import os
import time
import random
import sys
from playwright.sync_api import sync_playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config  # Used for HEADLESS setting

COOKIE_FILE = os.path.join(os.path.dirname(__file__), "..", "session", "cookies.json")
SESSION_DIR  = os.path.join(os.path.dirname(__file__), "..", "session")
PROFILE_DIR  = os.path.join(SESSION_DIR, "chrome_profile")

# ── Realistic Chrome versions to rotate (only used as fallback UA) ──────────
CHROME_VERSIONS = [
    "131.0.0.0", "132.0.0.0", "133.0.0.0",
    "134.0.0.0", "135.0.0.0", "136.0.0.0",
]

# ── Realistic screen resolutions ──────────────────────────────────────────────
VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 800},
    {"width": 1920, "height": 1080},
]


def get_random_user_agent() -> str:
    """Return a randomized but realistic Chrome user agent string"""
    version = random.choice(CHROME_VERSIONS)
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{version} Safari/537.36"
    )


def get_random_viewport() -> dict:
    """Return a random realistic viewport"""
    return random.choice(VIEWPORTS)


# ── Minimal JS patch injected into every page ────────────────────────────────
# Real Chrome already provides authentic plugins, WebGL, CPU/RAM, and languages.
# Overriding WebGL/plugins with synthetic values triggers LinkedIn bot checks.
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
    configurable: true
});
"""


def ensure_session_dir():
    os.makedirs(Config.get_session_dir(), exist_ok=True)


def save_cookies(context: BrowserContext):
    """Save browser cookies to profile-scoped cookie file"""
    ensure_session_dir()
    cookie_file = Config.get_cookie_file()
    cookies = context.cookies()
    with open(cookie_file, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
    print(f"[Session] ✅ Cookies saved → {cookie_file}")


def load_cookies(context: BrowserContext) -> bool:
    """Load cookies from profile-scoped file. Returns True if loaded."""
    cookie_file = Config.get_cookie_file()
    if not os.path.exists(cookie_file):
        return False
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        if not isinstance(cookies, list) or not cookies:
            return False
        context.add_cookies(cookies)
        print(f"[Session] ✅ Cookies loaded from saved session ({Config.PROFILE_NAME})")
        return True
    except Exception as e:
        print(f"[Session] ⚠️  Failed to load saved cookies ({e}) — removing stale file")
        try:
            os.remove(cookie_file)
        except OSError:
            pass
        return False


def _human_pause(min_s: float = 1.0, max_s: float = 3.0):
    """Random pause to mimic human thinking time"""
    time.sleep(random.uniform(min_s, max_s))


def resilient_goto(page: Page, url: str, timeout_ms: int = 45000, retries: int = 2) -> bool:
    """
    Navigate safely without failing on slow SPA analytics/assets.
    Uses wait_until='commit' to resolve server redirects quickly, then softly waits
    for DOMContentLoaded with retries on transient timeouts.
    """
    for attempt in range(1, retries + 1):
        try:
            page.goto(url, timeout=timeout_ms, wait_until="commit")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=20000)
            except PlaywrightTimeoutError:
                pass
            return True
        except PlaywrightTimeoutError:
            print(f"[Session] ⚠️  Navigation timeout ({timeout_ms // 1000}s) on attempt {attempt}/{retries}: {url[:60]}")
            if attempt < retries:
                time.sleep(2)
        except Exception as e:
            print(f"[Session] ⚠️  Navigation error for {url[:60]}: {e}")
            return False
    return False


def _build_persistent_context(playwright, headless: bool = False):
    """
    Launch a persistent Chrome profile in session/<profile>/chrome_profile.
    Preserves localStorage, IndexedDB, service workers, and device tokens
    across runs so LinkedIn does not treat each run as a new device.
    """
    ensure_session_dir()
    profile_dir = Config.get_chrome_profile_dir()
    os.makedirs(profile_dir, exist_ok=True)

    common_args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ]
    if not headless:
        common_args.append("--start-maximized")

    launch_kwargs = {
        "user_data_dir": profile_dir,
        "headless": headless,
        "args": common_args,
        "viewport": {"width": 1440, "height": 900},
        "locale": "en-US",
        "timezone_id": "Asia/Kolkata",
        "color_scheme": "light",
    }
    if headless:
        # Never expose 'HeadlessChrome' in User-Agent when running headless
        launch_kwargs["user_agent"] = get_random_user_agent()

    try:
        context = playwright.chromium.launch_persistent_context(
            channel="chrome",
            **launch_kwargs,
        )
        print(f"[Session] Using persistent real Chrome profile (headless={headless})")
    except Exception:
        context = playwright.chromium.launch_persistent_context(**launch_kwargs)
        print(f"[Session] Using persistent Chromium profile (headless={headless})")

    context.set_default_navigation_timeout(45000)
    context.set_default_timeout(30000)
    context.add_init_script(STEALTH_JS)
    page = context.pages[0] if context.pages else context.new_page()
    return context, page


def _build_login_context(playwright):
    """Backward-compatible helper opening visible persistent login context."""
    context, _page = _build_persistent_context(playwright, headless=False)
    return context, context


def _build_scrape_context(playwright, headless: bool | None = None):
    """Backward-compatible helper opening persistent scrape context."""
    use_headless = Config.HEADLESS if headless is None else headless
    context, _page = _build_persistent_context(playwright, headless=use_headless)
    return context, context


def manual_login(page: Page, context: BrowserContext):
    """
    Opens LinkedIn login in Playwright browser.
    Simple polling loop — checks URL every 2 seconds.
    No threading (Playwright sync API is not thread-safe).
    """
    print("\n" + "=" * 60)
    print("🔐  FIRST TIME SETUP — MANUAL LOGIN REQUIRED")
    print("=" * 60)
    print("  ⚠️  A NEW browser window has opened (separate from your Chrome)")
    print("  ⚠️  Switch to THAT window and login there")
    print("")
    print("  Steps in the Playwright browser:")
    print("    1. Enter your LinkedIn email & password")
    print("    2. Click 'Sign in'")
    print("    3. Complete CAPTCHA / OTP / verification if asked")
    print("    4. WAIT until you see your LinkedIn FEED")
    print("")
    print("  This terminal will auto-detect when you are logged in.")
    print("=" * 60 + "\n")

    resilient_goto(page, "https://www.linkedin.com/login", timeout_ms=45000)
    _human_pause(1, 2)

    # ── Inject a BIG RED BANNER so user knows this is the right window ─
    try:
        page.evaluate("""
            const banner = document.createElement('div');
            banner.id = 'playwright-banner';
            banner.style.cssText = `
                position: fixed;
                top: 0; left: 0;
                width: 100%;
                background: #cc0000;
                color: white;
                font-size: 18px;
                font-weight: bold;
                text-align: center;
                padding: 14px;
                z-index: 999999;
                letter-spacing: 0.5px;
                box-shadow: 0 3px 10px rgba(0,0,0,0.4);
            `;
            banner.textContent = '⚠️  LOGIN HERE — This is the AUTOMATED BROWSER (not your regular Chrome)  ⚠️';
            document.body.prepend(banner);
            document.body.style.marginTop = '55px';
        """)
    except Exception:
        pass

    # Bring the Playwright browser to front
    try:
        page.bring_to_front()
    except Exception:
        pass

    print("[Session] Checking every 2 seconds for login...")
    print("[Session] (Waiting — do NOT press anything here yet)\n")

    # ── Simple polling loop — no threading ────────────────────
    # Track initial li_at cookie value so we only trigger on a NEW login/signup cookie
    initial_li_at = {
        c.get("value")
        for c in context.cookies("https://www.linkedin.com")
        if c.get("name") == "li_at" and c.get("value")
    }
    max_wait = 300    # 5 minutes
    interval = 2
    elapsed  = 0
    last_url = ""
    active_page = page

    while elapsed < max_wait:
        time.sleep(interval)
        elapsed += interval

        try:
            pages = [p for p in context.pages if not p.is_closed()]
            if not pages:
                break
            # Prefer a tab that has navigated away from /login
            active_page = next(
                (p for p in pages if "/login" not in (p.url or "")),
                pages[0],
            )
            urls = [p.url or "" for p in pages]
            current_url = active_page.url or ""
        except Exception:
            # Page closed or crashed
            break

        # Show URL change so user knows script is working
        if current_url != last_url:
            print(f"[Session] URL changed → {current_url[:80]}")
            last_url = current_url

        # Handle checkpoint / OTP / post-signup onboarding pages across any open tab
        if any("/checkpoint" in u or "/challenge" in u or "/onboarding" in u for u in urls):
            print("\n[Session] ⚠️  LinkedIn needs verification/OTP or signup onboarding.")
            print("[Session]    Complete it in the browser window.")
            print("[Session]    Press ENTER here AFTER you see your LinkedIn feed.\n")
            input("[Session] ▶ Press ENTER when on LinkedIn feed → ")
            _human_pause(2, 3)
            pages = [p for p in context.pages if not p.is_closed()]
            active_page = next((p for p in pages if _is_on_feed(p.url or "")), pages[0])
            current_url = active_page.url or ""

        # Check if any tab reached LinkedIn feed/home/network
        feed_page = next((p for p in context.pages if not p.is_closed() and _is_on_feed(p.url or "")), None)
        if feed_page is not None:
            print(f"\n[Session] ✅ Login detected!")
            _human_pause(1, 2)
            save_cookies(context)
            print("[Session] ✅ Session saved — future runs are fully automatic!")
            return

        # Fallback: detect a brand-new li_at cookie (e.g. Google OAuth popup or another tab)
        current_li_at = {
            c.get("value")
            for c in context.cookies("https://www.linkedin.com")
            if c.get("name") == "li_at" and c.get("value")
        }
        if current_li_at - initial_li_at:
            print("\n[Session] ✅ New LinkedIn session cookie detected — verifying feed...")
            resilient_goto(active_page, "https://www.linkedin.com/feed/", timeout_ms=30000)
            _human_pause(1, 2)
            if _is_on_feed(active_page.url or ""):
                save_cookies(context)
                print("[Session] ✅ Session saved — future runs are fully automatic!")
                return

        # Show progress dot every 10 seconds
        if elapsed % 10 == 0:
            print(f"[Session] Still waiting... {elapsed}s | Current URL: {current_url[:60]}")

    # ── Timeout fallback — ask user to confirm manually ───────
    print("\n[Session] Auto-detect timed out after 5 minutes.")
    print("[Session] If you are now on your LinkedIn feed, press ENTER.")
    print("[Session] The script will verify and save the session.\n")
    input("[Session] ▶ Press ENTER when you are on LinkedIn feed → ")

    _human_pause(1, 2)

    # Navigate to feed explicitly to verify
    resilient_goto(active_page, "https://www.linkedin.com/feed/", timeout_ms=30000)
    _human_pause(2, 3)

    if _is_on_feed(active_page.url or ""):
        save_cookies(context)
        print("[Session] ✅ Session saved!")
        return

    print("[Session] ❌ Still not on feed. Please re-run the script and try again.")
    raise Exception("LinkedIn login could not be confirmed")


def _is_on_feed(url: str) -> bool:
    return any(x in url for x in ["/feed", "/mynetwork", "/home"])


def get_authenticated_browser():
    """
    Main entry point.
    Returns (playwright, browser_handle, context, page) — logged in & persistent.

    Flow:
    - Open persistent Chrome profile (session/chrome_profile)
    - Check if session is already active on /feed/; if not, seed session/cookies.json
    - If cookies are expired or redirected to login, open visible browser for manual login
    """
    playwright = sync_playwright().start()
    active_context = None

    try:
        # ── STEP 1: Open persistent profile and verify session ──────
        context, page = _build_persistent_context(playwright, headless=Config.HEADLESS)
        active_context = context

        # Seed persistent profile with cookies.json before first request if li_at isn't present yet
        cookie_file = Config.get_cookie_file()
        existing_cookies = context.cookies("https://www.linkedin.com")
        has_li_at = any(c.get("name") == "li_at" for c in existing_cookies)
        if not has_li_at and os.path.exists(cookie_file):
            print("[Session] Seeding persistent profile from cookies.json...")
            load_cookies(context)

        loaded = resilient_goto(page, "https://www.linkedin.com/feed/", timeout_ms=45000)
        _human_pause(2, 4)

        if _is_on_feed(page.url):
            save_cookies(context)
            print("[Session] ✅ Session active via persistent Chrome profile!")
            return playwright, context, context, page

        # If headless timed out (not redirected to login), retry in visible mode
        if (not loaded or "linkedin.com" not in page.url) and Config.HEADLESS:
            print("[Session] ⚠️  Headless feed check timed out — retrying in visible Chrome...")
            context.close()
            active_context = None
            context, page = _build_persistent_context(playwright, headless=False)
            active_context = context
            loaded = resilient_goto(page, "https://www.linkedin.com/feed/", timeout_ms=45000)
            _human_pause(2, 4)
            if _is_on_feed(page.url):
                save_cookies(context)
                print("[Session] ✅ Session restored in visible Chrome!")
                return playwright, context, context, page

        # Session genuinely expired / logged out
        if os.path.exists(cookie_file):
            print(f"[Session] ⚠️  Saved session expired ({page.url[:60]}). Re-login required...")
            try:
                os.remove(cookie_file)
            except OSError:
                pass

        # Ensure visible window for manual login
        if Config.HEADLESS:
            context.close()
            active_context = None
            context, page = _build_persistent_context(playwright, headless=False)
            active_context = context

        manual_login(page, context)

        # If user prefers headless scraping, restart in headless mode with refreshed profile
        if Config.HEADLESS:
            context.close()
            active_context = None
            print("[Session] Switching back to headless scrape profile...")
            context, page = _build_persistent_context(playwright, headless=True)
            active_context = context
            resilient_goto(page, "https://www.linkedin.com/feed/", timeout_ms=45000)
            _human_pause(2, 3)

        print("[Session] ✅ Persistent scrape session ready!")
        return playwright, context, context, page
    except Exception:
        if active_context is not None:
            try:
                active_context.close()
            except Exception:
                pass
        try:
            playwright.stop()
        except Exception:
            pass
        raise
