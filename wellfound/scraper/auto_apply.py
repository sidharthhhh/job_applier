"""
wellfound/scraper/auto_apply.py
Automates the Wellfound native "Apply" button + modal submission.

Key Features:
1. Waits for React to mount the Apply button.
2. Detects and dismisses any blocking modal/overlay before and after actions.
3. React modal overlay intercepts pointer events, so we use
   JavaScript element.click() / dispatchEvent instead of Playwright .click()
   to bypass overlay blocking.
4. Detects ineligibility early:
   - Visa sponsorship not offered & candidate outside country
   - Location / timezone restrictions
   - Form submit button disabled by Wellfound
5. Handles custom screening questions inside the modal:
   - Textareas: Tailored pitch / intro note / 'Why us' answers
   - Text inputs: Phone, LinkedIn, GitHub, Portfolio, Salary, Experience
   - Radio buttons: Work auth (Yes), Sponsorship required (No), Relocation (Yes)
   - Checkboxes: Terms / consent acknowledgments
6. Accurate success verification:
   - Success = Modal closes OR confirmation text ('Application sent') OR main page 'Applied'
   - Clean dismissal: Uses 'Escape' key and close buttons so next job starts cleanly
"""

import sys
import time
import random
import requests
from playwright.sync_api import Page

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _js_click_el(page: Page, element) -> None:
    """Click a Playwright element handle via JavaScript — bypasses overlay."""
    try:
        element.evaluate("""el => {
            try { el.click(); } catch (e) {}
            el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        }""")
    except Exception:
        pass


def _close_any_blocking_modal(page: Page):
    """Dismiss any modal or overlay via Escape key and close buttons."""
    try:
        page.keyboard.press("Escape")
        time.sleep(0.4)
    except Exception:
        pass

    try:
        close_btns = page.query_selector_all(
            "button[aria-label='Close'], "
            "button[aria-label='Dismiss'], "
            "button:has-text('Cancel'), "
            "[class*='close-button'], "
            "[class*='modal-close']"
        )
        for btn in close_btns:
            try:
                _js_click_el(page, btn)
                time.sleep(0.2)
            except Exception:
                pass
    except Exception:
        pass


def _generate_intro_note(job: dict, your_name: str, your_role: str,
                          your_skills: str, your_exp: str,
                          ollama_base: str, ollama_model: str,
                          max_words: int = 80) -> str:
    """Generate a short AI intro note for the Wellfound apply modal."""
    try:
        prompt = (
            f"You are {your_name}, a {your_role} with {your_exp} of experience.\n"
            f"Skills: {your_skills}\n\n"
            f"Write a SHORT (under {max_words} words), confident, professional intro note "
            f"for a job application to '{job.get('title', 'this role')}' at "
            f"'{job.get('company', 'this company')}'.\n"
            f"Job context:\n{job.get('description', '')[:500]}\n\n"
            "Note: 2-3 sentences only. No greetings, no sign-off. Just the pitch. "
            "Be direct and specific to their tech stack."
        )
        resp = requests.post(
            f"{ollama_base}/api/generate",
            json={"model": ollama_model, "prompt": prompt,
                  "stream": False, "options": {"num_predict": 150}},
            timeout=15,
        )
        text = (resp.json().get("response") or "").strip()
        if text:
            return text
    except Exception:
        pass

    # Fallback
    return (
        f"I'm an {your_role} with {your_exp} of hands-on experience in "
        f"{your_skills[:80]}. My background aligns well with what your team is building. "
        f"Happy to discuss further."
    )


def _handle_screening_questions(modal, candidate: dict) -> list[str]:
    """
    Auto-detect and fill screening questions inside Wellfound apply modal:
    - Textareas: pitch / intro note / 'why us' note
    - Text inputs: Phone, LinkedIn, GitHub, Portfolio, Salary, Experience, etc.
    - Radio buttons: Work auth (Yes), Visa sponsorship (No), Relocation (Yes), etc.
    - Checkboxes: Consent / terms / confirmation
    """
    return modal.evaluate("""(m, c) => {
        const logs = [];

        function setVal(el, val) {
            const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
            if (setter) setter.call(el, val);
            else el.value = val;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }

        // 1. Textareas (intro note / cover letter / 'why this company')
        const textareas = m.querySelectorAll('textarea');
        for (const ta of textareas) {
            if (!ta.value.trim() && !ta.disabled) {
                setVal(ta, c.intro_note || `I am an ${c.role} with hands-on experience building ML pipelines and deploying scalable models. Excited to contribute to this team.`);
                logs.push(`Filled textarea [${ta.name || 'note'}]`);
            }
        }

        // 2. Text / Tel / URL Inputs
        const textInputs = m.querySelectorAll('input[type="text"], input[type="tel"], input[type="url"], input:not([type])');
        for (const inp of textInputs) {
            if (inp.disabled || inp.value.trim()) continue;

            // Gather context from label, placeholder, name
            let label = '';
            let p = inp.parentElement;
            for (let i = 0; i < 4 && p && p !== m; i++) {
                const lbl = p.querySelector('label, [class*="label"], [class*="title"], [class*="question"]');
                if (lbl && lbl !== inp && !lbl.querySelector('input')) {
                    label = lbl.innerText.toLowerCase();
                    break;
                }
                p = p.parentElement;
            }
            const name = (inp.name || '').toLowerCase();
            const placeholder = (inp.placeholder || '').toLowerCase();
            const ctx = `${label} ${name} ${placeholder}`;

            if (/phone|mobile|tel|number/i.test(ctx)) {
                setVal(inp, c.mobile);
                logs.push(`Filled phone: ${c.mobile}`);
            } else if (/linkedin/i.test(ctx)) {
                setVal(inp, c.linkedin);
                logs.push(`Filled linkedin: ${c.linkedin}`);
            } else if (/github|git/i.test(ctx)) {
                setVal(inp, c.github);
                logs.push(`Filled github: ${c.github}`);
            } else if (/website|portfolio|url/i.test(ctx)) {
                setVal(inp, c.linkedin || c.github);
                logs.push(`Filled portfolio: ${c.linkedin || c.github}`);
            } else if (/salary|compensation|expected/i.test(ctx)) {
                setVal(inp, c.salary || 'Competitive');
                logs.push(`Filled salary: ${c.salary}`);
            } else if (/year|experience/i.test(ctx)) {
                setVal(inp, c.exp || '2.5');
                logs.push(`Filled experience: ${c.exp}`);
            } else if (/notice|start|availability/i.test(ctx)) {
                setVal(inp, 'Immediately');
                logs.push(`Filled availability: Immediately`);
            } else {
                setVal(inp, 'Yes');
                logs.push(`Filled default 'Yes' for [${label || name}]`);
            }
        }

        // 3. Radio Groups (screening questions)
        const radioGroups = {};
        for (const r of m.querySelectorAll('input[type="radio"]')) {
            if (!radioGroups[r.name]) radioGroups[r.name] = [];
            radioGroups[r.name].push(r);
        }
        for (const rname in radioGroups) {
            const group = radioGroups[rname];
            if (group.some(r => r.checked)) continue;
            if (group[0].disabled) continue;

            // Find question text
            let qText = '';
            let p = group[0].parentElement;
            for (let i = 0; i < 4 && p && p !== m; i++) {
                const heading = p.querySelector('label, [class*="label"], [class*="title"], [class*="question"]');
                if (heading && !heading.querySelector('input[type="radio"]')) {
                    qText = heading.innerText.toLowerCase();
                    break;
                }
                p = p.parentElement;
            }

            // Decide choice:
            // "Do you require sponsorship?" -> choose 'no'
            // "Are you authorized to work?" / "willing to relocate?" / "18+?" -> choose 'yes'
            let target = 'yes';
            if (/require.*sponsor|need.*sponsor|visa.*sponsor/i.test(qText)) {
                target = 'no';
            }

            let chosen = null;
            for (const r of group) {
                const lbl = (r.closest('label') || r.parentElement)?.innerText.toLowerCase() || '';
                if (lbl.includes(target)) {
                    chosen = r;
                    break;
                }
            }
            if (!chosen) chosen = group[0];

            try {
                const clickTarget = chosen.closest('label') || chosen;
                clickTarget.click();
            } catch (e) {}
            chosen.checked = true;
            chosen.dispatchEvent(new Event('change', { bubbles: true }));
            logs.push(`Selected radio '${target}' for [${qText.substring(0, 35)}...]`);
        }

        // 4. Checkboxes (consent, terms)
        for (const cb of m.querySelectorAll('input[type="checkbox"]:not(:checked):not(:disabled)')) {
            try {
                const clickTarget = cb.closest('label') || cb;
                clickTarget.click();
            } catch (e) {}
            cb.checked = true;
            cb.dispatchEvent(new Event('change', { bubbles: true }));
            logs.push(`Checked checkbox [${cb.name || 'consent'}]`);
        }

        // 5. Select Dropdowns (Greenhouse / Lever custom questions)
        for (const sel of m.querySelectorAll('select:not([disabled])')) {
            if (sel.value && sel.selectedIndex > 0) continue;
            let chosenIndex = -1;
            for (let i = 1; i < sel.options.length; i++) {
                const optText = (sel.options[i].text || '').toLowerCase();
                const optVal = (sel.options[i].value || '').toLowerCase();
                if (/yes|authorized|india|remote|full time|bachelor|master|engineering/i.test(optText + ' ' + optVal)) {
                    chosenIndex = i;
                    break;
                }
            }
            if (chosenIndex === -1 && sel.options.length > 1) {
                chosenIndex = 1;
            }
            if (chosenIndex > 0) {
                sel.selectedIndex = chosenIndex;
                sel.dispatchEvent(new Event('change', { bubbles: true }));
                logs.push(`Selected option '${sel.options[chosenIndex].text.trim()}' for dropdown [${sel.name || 'select'}]`);
            }
        }

        return logs;
    }""", candidate)


def auto_apply_to_job(
    page: Page,
    job: dict,
    your_name: str,
    your_role: str,
    your_skills: str,
    your_exp: str,
    ollama_base: str,
    ollama_model: str,
    max_note_words: int = 80,
    your_mobile: str = "",
    your_linkedin: str = "",
    your_github: str = "",
) -> dict:
    """
    Navigate to job page, click Apply, handle screening questions, fill intro note, submit.
    Uses JS click to bypass React modal overlay blocking.
    """
    result = {
        "job_id":      job.get("job_id", ""),
        "title":       job.get("title", ""),
        "company":     job.get("company", ""),
        "apply_url":   job.get("apply_url", ""),
        "status":      "failed",
        "message":     "",
        "is_external": False,
    }

    try:
        # Clean up any leftover overlay before navigation
        _close_any_blocking_modal(page)

        url = job.get("apply_url", "")
        if not url:
            result["message"] = "No apply URL"
            return result

        page.goto(url, wait_until="load", timeout=35000)

        # Wait up to 6 seconds for Apply button or status to mount in React DOM
        try:
            page.wait_for_selector(
                "button:has-text('Apply'), "
                "a:has-text('Apply'), "
                "[data-test='apply-button'], "
                "button:has-text('Applied')",
                timeout=6000
            )
        except Exception:
            pass
        time.sleep(1)

        # ── Find Active Apply button first ────────────────────────
        apply_btn = page.query_selector(
            "button:has-text('Apply'):not([disabled]), "
            "button:has-text('Easy Apply'):not([disabled]), "
            "[data-test='apply-button']:not([disabled]), "
            "a:has-text('Apply'):not([disabled]), "
            "a[href*='/jobs/'][href*='/apply']:not([disabled])"
        )

        if not apply_btn:
            # Check if job is closed / expired
            closed_el = page.query_selector(
                "div:has-text('no longer accepting applications'), "
                "div:has-text('This job is closed'), "
                "span:has-text('Job Closed')"
            )
            if closed_el:
                result["status"]  = "closed"
                result["message"] = "Job is closed / no longer accepting applications"
                return result

            # If no active Apply button, check if it's already applied or shows Undo
            already = page.query_selector(
                "button:has-text('Undo'), "
                "div:has-text('Undo ·'), "
                "button[disabled]:has-text('Applied'), "
                "div:has-text('You applied on'), "
                "div:has-text('Application submitted')"
            )
            if already:
                result["status"]  = "already_applied"
                result["message"] = "Already applied to this job"
                return result

            result["message"] = "Apply button not found on page"
            return result

        # Check if external ATS link
        tag  = apply_btn.evaluate("el => el.tagName.toLowerCase()")
        href = apply_btn.get_attribute("href") or ""
        if tag == "a" and href and "wellfound.com" not in href:
            result["status"]      = "external_ats"
            result["is_external"] = True
            result["message"]     = f"External ATS: {href}"
            return result

        # ── Click Apply via JS (bypasses overlay) ─────────────────
        apply_btn.scroll_into_view_if_needed()
        time.sleep(0.5)
        _js_click_el(page, apply_btn)

        # ── Wait for modal content to render (innerText > 0) ──────
        modal = None
        for _ in range(12):
            time.sleep(0.5)
            modal = page.query_selector(".ReactModal__Content")
            if modal:
                text_len = modal.evaluate("e => (e.innerText || '').trim().length")
                if text_len > 10:
                    break

        if not modal:
            result["message"] = "Modal did not open"
            return result

        # ── Check for Ineligibility / Location Restrictions ───────
        modal_text = modal.evaluate("e => e.innerText")
        restriction_match = None
        for phrase in [
            "does not offer visa sponsorship",
            "requires all remote workers to be in-country",
            "not accepting applications from your current location",
            "Your profile indicates you require sponsorship",
        ]:
            if phrase.lower() in modal_text.lower():
                restriction_match = phrase
                break

        submit_btn = modal.query_selector(
            "button[type='submit'], "
            "button:has-text('Send application'), "
            "button:has-text('Submit application'), "
            "button:has-text('Submit'), "
            "button:has-text('Send')"
        )

        # If restricted or submit button disabled from start
        if restriction_match or (submit_btn and submit_btn.get_attribute("disabled") is not None):
            reason = restriction_match or "Employer disabled application from candidate's location/profile"
            print(f"[WF Apply] 🚫 Ineligible: {reason}")
            result["status"]  = "ineligible"
            result["message"] = f"Ineligible: {reason}"
            _close_any_blocking_modal(page)
            return result

        # ── Prepare Candidate Information for Screening ───────────
        intro_note = _generate_intro_note(
            job, your_name, your_role, your_skills, your_exp,
            ollama_base, ollama_model, max_note_words
        )

        candidate_data = {
            "name":       your_name,
            "role":       your_role,
            "skills":     your_skills,
            "exp":        your_exp,
            "mobile":     your_mobile,
            "linkedin":   your_linkedin,
            "github":     your_github,
            "salary":     "Competitive / Flexible",
            "intro_note": intro_note,
        }

        # ── Auto-fill screening questions & textareas ─────────────
        screening_logs = _handle_screening_questions(modal, candidate_data)
        for log in screening_logs:
            print(f"[WF Apply] 📝 {log}")

        time.sleep(random.uniform(1.0, 1.8))

        # Re-query submit button
        submit_btn = modal.query_selector(
            "button[type='submit'], "
            "button:has-text('Send application'), "
            "button:has-text('Submit application'), "
            "button:has-text('Submit'), "
            "button:has-text('Send')"
        )

        if not submit_btn:
            result["message"] = "Submit button not found in modal"
            _close_any_blocking_modal(page)
            return result

        # Check if submit button is still disabled
        if submit_btn.get_attribute("disabled") is not None:
            print(f"[WF Apply] ⚠️  Submit button remained disabled after filling form")
            result["status"]  = "ineligible"
            result["message"] = "Ineligible or unfilled custom constraint"
            _close_any_blocking_modal(page)
            return result

        # ── Click Submit ──────────────────────────────────────────
        _js_click_el(page, submit_btn)
        time.sleep(random.uniform(2.5, 3.5))

        # ── Accurate Success / Failure Verification ───────────────
        # 1. Success confirmation text inside modal
        modal_success = page.query_selector(
            ".ReactModal__Content :has-text('Application sent'), "
            ".ReactModal__Content :has-text('Your application was sent'), "
            ".ReactModal__Content :has-text('Application submitted')"
        )

        # 2. Main page Apply button switched to 'Applied' or shows 'Undo'
        page_success = page.query_selector(
            "button:has-text('Undo'), "
            "div:has-text('Undo ·'), "
            "button[disabled]:has-text('Applied'), "
            "div:has-text('You applied on')"
        )

        # 3. Modal closed completely (.ReactModal__Content is gone)
        modal_still_open = page.query_selector(".ReactModal__Content, .ReactModal__Overlay--after-open") is not None

        if modal_success or page_success or not modal_still_open:
            result["status"]  = "applied"
            result["message"] = "Successfully applied via Wellfound"
            _close_any_blocking_modal(page)
        else:
            result["status"]  = "failed"
            result["message"] = "Modal submission incomplete (required screening question or error)"
            _close_any_blocking_modal(page)

    except Exception as e:
        result["status"]  = "failed"
        result["message"] = str(e)[:200]
        _close_any_blocking_modal(page)

    return result
