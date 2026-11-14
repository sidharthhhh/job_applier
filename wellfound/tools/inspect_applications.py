import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION_FILE = Path(__file__).resolve().parent.parent / "session" / "wf_cookies.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    ctx.add_cookies(json.loads(SESSION_FILE.read_text()))
    page = ctx.new_page()
    page.goto("https://wellfound.com/jobs/applications", wait_until="load", timeout=40000)
    time.sleep(6)
    
    # Scroll down to load all
    for _ in range(5):
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(1)
        
    apps = page.evaluate("""() => {
        // Collect links or application cards
        const results = [];
        const rows = document.querySelectorAll("a[href*='/jobs/'], a[href*='/company/'], [data-test*='application']");
        for (const r of rows) {
            const text = (r.innerText || '').trim();
            const href = r.href || '';
            if (href && text) {
                results.push({ href: href, text: text });
            }
        }
        return {
            pageText: document.body.innerText.substring(0, 2000),
            rowCount: results.length,
            rows: results.slice(0, 30)
        };
    }""")
    
    print("Page text preview:\n", apps["pageText"][:1200])
    print(f"\nRow count: {apps['rowCount']}")
    for r in apps["rows"][:10]:
        print("  ", r)
        
    browser.close()
