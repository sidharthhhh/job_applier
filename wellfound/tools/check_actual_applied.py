"""
Inspect Wellfound applications page to see the exact 57 applied jobs.
"""
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SESSION_FILE = Path(__file__).resolve().parent.parent / "session" / "wf_cookies.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    if SESSION_FILE.exists():
        context.add_cookies(json.loads(SESSION_FILE.read_text()))
    
    page = context.new_page()
    page.goto("https://wellfound.com/jobs/applications", wait_until="load", timeout=40000)
    time.sleep(5)
    
    # Extract applied job cards
    data = page.evaluate("""() => {
        const jobs = [];
        // Extract from Next.js __NEXT_DATA__ or DOM
        const el = document.getElementById('__NEXT_DATA__');
        if (el) {
            try {
                const parsed = JSON.parse(el.textContent);
                return { source: 'next_data', text: el.textContent.substring(0, 1000) };
            } catch(e) {}
        }
        return { source: 'dom', text: document.body.innerText.substring(0, 1500) };
    }""")
    print("Page source:", data.get("source"))
    print("Preview:\n", data.get("text", "")[:1000])
    browser.close()
