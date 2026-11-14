"""
wellfound/tools/debug_scraper.py  (v2 — faster, one URL, full output)
Quickly snapshots ONE Wellfound page and prints key info to console.

Usage:
    python wellfound\\tools\\debug_scraper.py
"""

import sys
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

SESSION_FILE = ROOT / "wellfound" / "session" / "wf_cookies.json"
DEBUG_DIR    = ROOT / "wellfound" / "tools" / "debug_output"
DEBUG_DIR.mkdir(exist_ok=True)

# ── Only test ONE fast URL ────────────────────────────────────────
TEST_URL = "https://wellfound.com/role/r/machine-learning-engineer"


def run():
    print("[Debug] Opening Wellfound page...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )
        context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )

        if SESSION_FILE.exists():
            cookies = json.loads(SESSION_FILE.read_text())
            context.add_cookies(cookies)
            print(f"[Debug] Loaded {len(cookies)} cookies")
        else:
            print("[Debug] No saved cookies — continuing without login")

        page = context.new_page()
        print(f"[Debug] Loading: {TEST_URL}")
        page.goto(TEST_URL, wait_until="load", timeout=40000)

        print("[Debug] Waiting 8s for React...")
        time.sleep(8)

        # Scroll
        for i in range(5):
            page.evaluate("window.scrollBy(0, 500)")
            time.sleep(1.5)

        # Screenshot
        shot = DEBUG_DIR / "snapshot.png"
        page.screenshot(path=str(shot), full_page=True)
        print(f"[Debug] Screenshot: {shot}")

        # HTML
        html = page.content()
        html_file = DEBUG_DIR / "page.html"
        html_file.write_text(html, encoding="utf-8")
        print(f"[Debug] HTML saved ({len(html)} bytes): {html_file}")

        # __NEXT_DATA__
        nd = page.evaluate(
            "() => { const e=document.getElementById('__NEXT_DATA__'); "
            "return e ? e.textContent : 'NOT_FOUND'; }"
        )
        nd_file = DEBUG_DIR / "next_data.json"
        nd_file.write_text(nd, encoding="utf-8")
        print(f"[Debug] __NEXT_DATA__ ({len(nd)} chars): {nd_file}")
        print(f"[Debug] __NEXT_DATA__ preview: {nd[:300]}")

        # All hrefs
        hrefs = page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                       .map(a => a.href)
                       .filter(h => h.includes('wellfound'))
                       .slice(0, 30)
        """)
        print(f"\n[Debug] Wellfound links on page ({len(hrefs)}):")
        for h in hrefs:
            print(f"   {h}")

        # Text preview
        body_text = page.evaluate("() => document.body.innerText")
        txt_file = DEBUG_DIR / "page_text.txt"
        txt_file.write_text(body_text, encoding="utf-8")
        print(f"\n[Debug] Page text preview (first 1000 chars):")
        print(body_text[:1000])
        print(f"\n[Debug] Full text saved: {txt_file}")
        print(f"[Debug] Final URL: {page.url}")

        browser.close()

    print(f"\n[Debug] Done. Files saved to: {DEBUG_DIR}")


if __name__ == "__main__":
    run()
