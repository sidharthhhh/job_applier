"""
wellfound/scraper/job_scraper.py
Scrapes Wellfound job listings using Apollo GraphQL cache from __NEXT_DATA__.

Structure confirmed from debug:
  __NEXT_DATA__.props.pageProps.apolloState.data  →  flat dict of Apollo cache objects
    Keys like "JobListingSearchResult:1922156"     →  full job details
    Keys like "StartupResult:8383094"              →  company + job refs
    Key  "ROOT_QUERY"                              →  search result refs (page 1 only)

Apply URL: https://wellfound.com/jobs/<id>-<slug>
Pagination: page param in URL → /role/r/<slug>?page=2 etc.
"""

import json
import time
import random
import re
from playwright.sync_api import Page

WELLFOUND_BASE = "https://wellfound.com"


# ─── Helpers ──────────────────────────────────────────────────────

def _extract_emails(text: str) -> list[str]:
    """Extract email addresses from text."""
    return list(set(re.findall(
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text
    )))


def _parse_experience(text: str) -> tuple[int, int]:
    text = text.lower()
    m = re.search(r'(\d+)\s*[-–to]+\s*(\d+)\s*years?', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r'(\d+)\+\s*years?', text)
    if m:
        return int(m.group(1)), int(m.group(1)) + 3
    m = re.search(r'(\d+)\s*years?\s*of\s*exp', text)
    if m:
        y = int(m.group(1)); return y, y
    return 0, 99


def _wait_for_react(page: Page, seconds: int = 8):
    """Wait for React/Apollo to hydrate, then scroll to trigger lazy load."""
    time.sleep(seconds)
    for _ in range(4):
        page.evaluate("window.scrollBy(0, 600)")
        time.sleep(random.uniform(1.2, 2.0))
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)


# ─── Apollo Cache Parser ──────────────────────────────────────────

def _parse_apollo_state(page: Page) -> list[dict]:
    """
    Extract all jobs from Wellfound's Apollo GraphQL cache in __NEXT_DATA__.

    The cache is a flat dict where:
      "JobListingSearchResult:1922156" → job details
      "StartupResult:8383094"          → company + list of job refs
    """
    try:
        raw = page.evaluate(
            "() => { const e = document.getElementById('__NEXT_DATA__'); "
            "return e ? e.textContent : null; }"
        )
        if not raw:
            return []

        data      = json.loads(raw)
        apollo    = (data.get("props", {})
                        .get("pageProps", {})
                        .get("apolloState", {})
                        .get("data", {}))
        if not apollo:
            return []

        # Build company lookup: StartupResult id → company info
        companies: dict[str, dict] = {}
        for key, val in apollo.items():
            if not key.startswith("StartupResult:"):
                continue
            sid = key.split(":", 1)[1]
            job_refs = [
                r.get("__ref", "") for r in val.get("highlightedJobListings", [])
            ]
            companies[sid] = {
                "name":     val.get("name", ""),
                "slug":     val.get("slug", ""),
                "size":     val.get("companySize", ""),
                "concept":  val.get("highConcept", ""),
                "job_refs": job_refs,     # e.g. ["JobListingSearchResult:1922156"]
            }

        # Build reverse map: job cache key → company
        job_to_company: dict[str, dict] = {}
        for sid, cinfo in companies.items():
            for ref in cinfo["job_refs"]:
                job_to_company[ref] = cinfo

        # Extract all JobListingSearchResult objects
        jobs: list[dict] = []
        for key, val in apollo.items():
            if not key.startswith("JobListingSearchResult:"):
                continue

            jid     = str(val.get("id", key.split(":", 1)[1]))
            slug    = val.get("slug", "")
            title   = val.get("title", "")
            desc    = val.get("description", "") or ""
            comp    = val.get("compensation", "") or ""
            remote  = bool(val.get("remote", False))
            jtype   = val.get("jobType", "")
            locs    = val.get("locationNames", [])
            min_exp = val.get("yearsExperienceMin") or 0
            max_exp = val.get("yearsExperienceMax") or 99

            # Apply URL: wellfound.com/jobs/<id>-<slug>
            apply_url = f"{WELLFOUND_BASE}/jobs/{jid}-{slug}" if slug else f"{WELLFOUND_BASE}/jobs/{jid}"

            # Company info
            cinfo   = job_to_company.get(key, {})
            company = cinfo.get("name", "")

            # Extract emails from description
            emails = _extract_emails(desc)

            if title:
                jobs.append({
                    "job_id":      jid,
                    "title":       title,
                    "company":     company,
                    "company_size":cinfo.get("size", ""),
                    "description": desc,
                    "compensation":comp,
                    "location":    ", ".join(locs) if locs else "",
                    "remote":      remote,
                    "job_type":    jtype,
                    "apply_url":   apply_url,
                    "min_exp":     int(min_exp) if min_exp else 0,
                    "max_exp":     int(max_exp) if max_exp != 99 else 99,
                    "emails":      emails,
                    "source":      "wellfound_apollo",
                })

        return jobs

    except Exception as e:
        print(f"[WF Scraper] Apollo parse error: {e}")
        return []


# ─── Paginated Role Scraper ───────────────────────────────────────

def _scrape_role_pages(
    page: Page,
    slug: str,
    max_pages: int = 3,
) -> list[dict]:
    """
    Scrape multiple pages of a role listing.
    URL: wellfound.com/role/r/<slug>?page=N  (no location — works globally)
    """
    all_jobs: list[dict] = []
    seen_ids: set        = set()

    for pg in range(1, max_pages + 1):
        if pg == 1:
            url = f"{WELLFOUND_BASE}/role/r/{slug}"
        else:
            url = f"{WELLFOUND_BASE}/role/r/{slug}?page={pg}"

        print(f"[WF Scraper]   Page {pg}: {url}")
        try:
            page.goto(url, wait_until="load", timeout=40000)
            _wait_for_react(page, seconds=7)

            jobs = _parse_apollo_state(page)
            new  = [j for j in jobs if j["job_id"] not in seen_ids]
            seen_ids.update(j["job_id"] for j in new)
            all_jobs.extend(new)
            print(f"[WF Scraper]   → {len(new)} jobs on page {pg} ({len(all_jobs)} total)")

            if not new:
                break   # no more pages

        except Exception as e:
            print(f"[WF Scraper]   Page {pg} error: {e}")
            break

        time.sleep(random.uniform(2, 4))

    return all_jobs


# ─── Main Entry Point ─────────────────────────────────────────────

def scrape_wellfound_jobs(
    page: Page,
    role_slugs: list[str],
    location_slug: str = "",     # NOTE: Wellfound serves personalised results
    max_per_role: int = 60,      # jobs per role (3 pages × 20)
) -> list[dict]:
    """
    Scrape Wellfound jobs for all given role slugs.
    Returns deduplicated list of job dicts with full descriptions.
    """
    all_jobs: list[dict] = []
    seen_ids: set        = set()

    for slug in role_slugs:
        print(f"\n[WF Scraper] Scraping role: '{slug}'")

        # Scrape up to 3 pages per role
        max_pages = max(1, min(3, max_per_role // 20))
        jobs      = _scrape_role_pages(page, slug, max_pages=max_pages)

        # Deduplicate globally
        new_count = 0
        for j in jobs:
            jid = j.get("job_id", "")
            if jid and jid not in seen_ids:
                seen_ids.add(jid)
                j["role_slug"] = slug
                # Parse exp from description if API didn't return it
                if j["min_exp"] == 0 and j["max_exp"] == 99 and j.get("description"):
                    j["min_exp"], j["max_exp"] = _parse_experience(j["description"])
                all_jobs.append(j)
                new_count += 1

        status = "📌" if new_count else "⚠️ "
        print(f"[WF Scraper] {status} {new_count} unique jobs added from '{slug}'")
        time.sleep(random.uniform(2, 3))

    print(f"\n[WF Scraper] Total: {len(all_jobs)} jobs across {len(role_slugs)} roles")
    return all_jobs
