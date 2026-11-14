"""
One-click sync script:
Reconciles MongoDB's wf_applied_jobs with actual applications on Wellfound.
Keeps genuine applied jobs, removes false positives so they can be applied to properly.
"""
import json
import time
import re
from pathlib import Path
from pymongo import MongoClient
from playwright.sync_api import sync_playwright

SESSION_FILE = Path(__file__).resolve().parent.parent / "session" / "wf_cookies.json"

client = MongoClient("mongodb://localhost:27017")
db = client["linkedin_scraper"]
col = db["wf_applied_jobs"]

print("[Sync] Connecting to Wellfound to fetch actual applied list...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context()
    ctx.add_cookies(json.loads(SESSION_FILE.read_text()))
    page = ctx.new_page()
    page.goto("https://wellfound.com/jobs/applications", wait_until="load", timeout=40000)
    time.sleep(5)
    
    # Scroll down to load all application cards
    prev_count = 0
    for _ in range(15):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)
        count = page.evaluate("() => document.querySelectorAll(\"a[href*='/jobs/applications/']\").length")
        if count == prev_count and count > 0:
            break
        prev_count = count
        
    apps = page.evaluate("""() => {
        const list = [];
        const links = document.querySelectorAll("a[href*='/jobs/applications/']");
        for (const a of links) {
            const href = a.href || '';
            list.push(href);
        }
        return list;
    }""")
    browser.close()

real_applied_job_ids = set()
for href in apps:
    m = re.search(r'/jobs/applications/\d+-(\d+)', href)
    if m:
        real_applied_job_ids.add(m.group(1))

print(f"[Sync] Found {len(real_applied_job_ids)} genuinely applied jobs on Wellfound.")

# Find all records in MongoDB
mongo_applied = list(col.find({"status": "applied"}))
print(f"[Sync] MongoDB currently has {len(mongo_applied)} jobs marked as 'applied'.")

removed_count = 0
kept_count = 0

for doc in mongo_applied:
    jid = doc.get("job_id", "")
    if jid in real_applied_job_ids:
        kept_count += 1
    else:
        # False positive: remove from wf_applied_jobs so it can be retried
        col.delete_one({"_id": doc["_id"]})
        removed_count += 1

print(f"\n[Sync] 🏁 Complete:")
print(f"   ✅ Kept {kept_count} genuinely applied jobs in MongoDB.")
print(f"   🧹 Removed {removed_count} false positives from MongoDB for retry.")
print(f"   📊 Current applied count in MongoDB: {col.count_documents({'status': 'applied'})}")
