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
    url = "https://wellfound.com/jobs/3392128-machine-learning-engineer-voice"
    page.goto(url, wait_until="load", timeout=40000)
    time.sleep(3)
    
    apply_btn = page.query_selector("button:has-text('Apply')")
    apply_btn.evaluate("el => { el.click(); el.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true})); }")
    time.sleep(3)
    
    modal = page.query_selector(".ReactModal__Content")
    if modal:
        # Check all form groups/containers
        groups = modal.evaluate("""m => {
            const results = [];
            // find all inputs inside modal
            const inputs = m.querySelectorAll('input, textarea, select');
            for (const inp of inputs) {
                // Find parent container or preceding label
                let container = inp.closest('div[class*=\"field\"], div[class*=\"input\"], div[class*=\"group\"], label') || inp.parentElement;
                // find label or text around it
                let labelText = '';
                let p = inp.parentElement;
                for (let i = 0; i < 4 && p && p !== m; i++) {
                    const lbl = p.querySelector('label, [class*="label"], [class*="title"], [class*="question"]');
                    if (lbl && lbl !== inp) {
                        labelText = lbl.innerText.trim();
                        break;
                    }
                    p = p.parentElement;
                }
                results.push({
                    name: inp.name,
                    type: inp.type,
                    id: inp.id,
                    placeholder: inp.placeholder,
                    parentText: inp.parentElement ? inp.parentElement.innerText.trim() : '',
                    labelText: labelText,
                    outerHTML: inp.outerHTML
                });
            }
            return results;
        }""")
        for g in groups:
            print("---")
            print("Name:", g['name'])
            print("Type:", g['type'])
            print("ParentText:", repr(g['parentText']))
            print("LabelText:", repr(g['labelText']))
    browser.close()
