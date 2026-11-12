"""
scraper/linkedin_scraper.py
LinkedIn hashtag post scraper with FULL human-like behaviour.
Every action mimics real user: mouse moves, natural scrolling,
random pauses, typo-style timing — undetectable by LinkedIn.
"""

import time
import random
import math
import urllib.parse
import re
import sys
import os
from datetime import datetime
from playwright.sync_api import Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config
from scraper.session_manager import COOKIE_FILE, resilient_goto


class SessionInterruptedError(Exception):
    """Raised when LinkedIn redirects an active scrape to login/checkpoint."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# HUMAN BEHAVIOUR HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def human_pause(min_s: float = 0.5, max_s: float = 2.0):
    """Random pause — simulates human thinking / reading time"""
    time.sleep(random.uniform(min_s, max_s))


def human_scroll(page: Page, direction: str = "down", intensity: str = "normal"):
    """
    Smooth, human-like scroll using small incremental steps.
    Intensity: 'slow' | 'normal' | 'fast'
    """
    scroll_map = {
        "slow":   (80,  150),
        "normal": (200, 400),
        "fast":   (400, 700),
    }
    step_min, step_max = scroll_map.get(intensity, (200, 400))

    # Scroll in 3-6 small steps with micro-pauses (like a real mouse wheel)
    steps = random.randint(3, 6)
    for _ in range(steps):
        scroll_amount = random.randint(step_min, step_max)
        if direction == "up":
            scroll_amount = -scroll_amount

        page.evaluate(f"window.scrollBy({{ top: {scroll_amount}, behavior: 'smooth' }})")
        time.sleep(random.uniform(0.08, 0.25))   # micro-pause between each step

    # Brief pause after full scroll — human reads content
    human_pause(0.8, 2.0)


def human_mouse_move(page: Page):
    """
    Move mouse in a natural curved path across the page.
    Prevents 'mouse never moved' detection.
    """
    vp = page.viewport_size or {"width": 1280, "height": 800}
    w, h = vp["width"], vp["height"]

    # Pick a random target on the page
    target_x = random.randint(100, w - 100)
    target_y = random.randint(100, h - 100)

    # Current position (simulate starting from center area)
    start_x = random.randint(w // 4, 3 * w // 4)
    start_y = random.randint(h // 4, 3 * h // 4)

    # Move in small curved steps (Bezier-like)
    steps = random.randint(8, 15)
    for i in range(steps):
        t = i / steps
        # Add slight curve via sine wave offset
        curve_x = start_x + (target_x - start_x) * t + math.sin(t * math.pi) * random.randint(-30, 30)
        curve_y = start_y + (target_y - start_y) * t

        page.mouse.move(curve_x, curve_y)
        time.sleep(random.uniform(0.01, 0.04))


def human_hover_post(page: Page, element):
    """Hover over a post element briefly — like a human reading it"""
    try:
        box = element.bounding_box()
        if box:
            x = box["x"] + random.randint(10, int(box["width"]) - 10)
            y = box["y"] + random.randint(5, min(50, int(box["height"]) - 5))
            page.mouse.move(x, y)
            human_pause(0.3, 1.2)   # read time simulation
    except Exception:
        pass


def human_click(page: Page, element):
    """
    Click an element like a human — hover first, slight delay, then click.
    Avoids robotic instant-click detection.
    """
    try:
        box = element.bounding_box()
        if box:
            # Move to element with slight offset from center
            x = box["x"] + box["width"]  / 2 + random.uniform(-5, 5)
            y = box["y"] + box["height"] / 2 + random.uniform(-3, 3)
            page.mouse.move(x, y)
            human_pause(0.2, 0.6)   # hover before clicking
            page.mouse.click(x, y)
            human_pause(0.3, 0.8)   # pause after click
    except Exception:
        element.click()


def random_idle_behaviour(page: Page):
    """
    Occasionally simulate idle human behaviour:
    random mouse wiggle, scroll up a bit, pause — looks very natural.
    """
    behaviour = random.choices(
        ["wiggle", "scroll_up", "idle", "nothing"],
        weights=[20, 15, 30, 35]
    )[0]

    if behaviour == "wiggle":
        human_mouse_move(page)
    elif behaviour == "scroll_up":
        # Scroll up a tiny bit then back down — humans do this
        page.evaluate("window.scrollBy({ top: -150, behavior: 'smooth' })")
        human_pause(0.5, 1.5)
        page.evaluate("window.scrollBy({ top: 200, behavior: 'smooth' })")
        human_pause(0.5, 1.0)
    elif behaviour == "idle":
        human_pause(1.5, 4.0)   # longer "reading" pause


# ─────────────────────────────────────────────────────────────────────────────
# URL BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_search_url(hashtag_query: str, date_filter: str) -> str:
    """Build LinkedIn content search URL for given hashtags and date filter"""
    filter_map = {
        "past-week":    '["past-week"]',
        "past-2-weeks": '["past-2-weeks"]',
        "past-month":   '["past-month"]',
    }
    date_param      = filter_map.get(date_filter, '["past-week"]')
    encoded_keywords = urllib.parse.quote(hashtag_query.strip())
    encoded_date    = urllib.parse.quote(date_param)

    # Use standard search results URL
    return (
        f"https://www.linkedin.com/search/results/content/"
        f"?keywords={encoded_keywords}"
        f"&origin=GLOBAL_SEARCH_HEADER"
        f"&datePosted={encoded_date}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN SCRAPER
# ─────────────────────────────────────────────────────────────────────────────

_NOISE_LINES = {
    "like", "comment", "repost", "send", "follow", "+ follow",
    "copy", "more", "feed post", "activate to view larger image,",
}
_NOISE_SUBSTRINGS = ("subtitles", "descriptions off", "dialog", "playback", "feed post")


def _clean_post_text(raw_text: str) -> str:
    """Strip LinkedIn UI chrome and accessibility noise from extracted post text."""
    lines = []
    for line in raw_text.split("\n"):
        cleaned = line.strip()
        if not cleaned:
            continue
        low = cleaned.lower()
        if low in _NOISE_LINES or any(skip in low for skip in _NOISE_SUBSTRINGS):
            continue
        lines.append(cleaned)
    return "\n".join(lines)


def _navigate_like_human(page: Page, url: str) -> bool:
    """
    Navigate to URL with human-like pre/post behaviour.
    Avoids robotic instant navigation pattern.
    """
    # Occasionally move mouse before navigating
    if random.random() > 0.5:
        human_mouse_move(page)
        human_pause(0.3, 0.8)

    if not resilient_goto(page, url, timeout_ms=45000):
        return False

    # Simulate page load reading time
    human_pause(2.5, 4.5)

    # Initial mouse movement after page load
    human_mouse_move(page)
    human_pause(0.8, 1.8)
    return True


def scrape_posts_for_hashtag(page: Page, hashtag_query: str) -> list[dict]:
    """
    Scrape LinkedIn posts for a search query (hashtag or plain text keywords) with full human behaviour.
    Uses robust action-bar anchoring that works across modern LinkedIn layouts.
    """
    date_filter = Config.get_linkedin_date_filter()
    url = build_search_url(hashtag_query, date_filter)

    print(f"\n[Scraper] 🔍 Search Query: '{hashtag_query}' | Last {Config.LINKEDIN_SCRAPE_DAYS} days")

    if not _navigate_like_human(page, url):
        print(f"[Scraper] ⚠️  Timed out loading search page for '{hashtag_query}' — skipping query.")
        return []

    if any(p in page.url for p in ["/login", "/authwall", "/checkpoint", "/challenge"]):
        raise SessionInterruptedError(f"LinkedIn redirected to {page.url[:80]}")

    # Wait briefly for LinkedIn SPA search cards or 'no results' state to render
    try:
        page.wait_for_selector(
            "button[aria-label*='eaction'], button[aria-label*='ike'], .search-no-results__image",
            timeout=10000,
        )
    except Exception:
        pass

    posts_data    = []
    seen_keys     = set()
    scroll_count  = 0
    max_scrolls   = (Config.MAX_POSTS_PER_SEARCH // 5) + 8
    no_new_streak = 0
    pause_base    = max(1.0, Config.SCROLL_PAUSE_TIME)

    while len(posts_data) < Config.MAX_POSTS_PER_SEARCH and scroll_count < max_scrolls:

        if any(p in page.url for p in ["/login", "/authwall", "/checkpoint", "/challenge"]):
            raise SessionInterruptedError(f"LinkedIn redirected mid-scroll to {page.url[:80]}")

        # ── 1. Expand truncated post text ('...see more' toggles only) ─
        try:
            page.evaluate("""() => {
                const toggles = new Set([
                    ...document.querySelectorAll(
                        "button.feed-shared-inline-show-more-text__see-more-less-toggle, button[aria-label*='see more' i]"
                    ),
                    ...Array.from(document.querySelectorAll("button, span")).filter(el => {
                        const txt = (el.innerText || "").trim().toLowerCase();
                        return txt.length > 0 && txt.length <= 20 && /^(?:(?:…|\\.{3})\\s*(?:see\\s+)?more|see\\s+more)$/.test(txt);
                    })
                ]);
                toggles.forEach(btn => {
                    try { btn.click(); } catch(e) {}
                });
            }""")
            human_pause(0.4, 0.8)
        except Exception:
            pass

        # ── 2. Extract cards anchored to the Action / Reaction bar ────────
        try:
            extracted_batch = page.evaluate(r"""() => {
                // Find reaction buttons (supports new reaction-count icon buttons and classic 'Like' text)
                const actionBtns = Array.from(document.querySelectorAll("button")).filter(b => {
                    const aria = (b.getAttribute("aria-label") || "").toLowerCase();
                    const txt = (b.innerText || "").trim().toLowerCase();
                    return aria.includes("reaction button") || aria.includes("like") || txt === "like";
                });

                const uniqueCards = [];
                const seenCards = new Set();

                actionBtns.forEach(btn => {
                    let p = btn;
                    for (let i = 0; i < 20; i++) {
                        if (!p || !p.parentElement || p.parentElement.tagName === "BODY" || p.parentElement.id === "root") break;
                        if (p.matches && p.matches("[data-urn*='urn:li:activity:'], [data-id*='urn:li:activity:'], [data-urn*='urn:li:ugcPost:']")) break;
                        const parentUrns = p.parentElement.querySelectorAll("[data-urn*='urn:li:activity:'], [data-urn*='urn:li:ugcPost:']").length;
                        const countLikes = p.parentElement.querySelectorAll("button[aria-label*='eaction'], button[aria-label*='ike']").length;
                        const txt = p.parentElement.innerText || "";
                        if (parentUrns > 1 || countLikes > 8 || txt.length > 5000) break;
                        p = p.parentElement;
                    }
                    if (!p || seenCards.has(p)) return;
                    seenCards.add(p);

                    // Extract poster name
                    let name = "Recruiter";
                    const nameLink = Array.from(p.querySelectorAll("a[href*='/in/']"))
                        .find(a => a.innerText && a.innerText.trim().length > 2 && !a.innerText.toLowerCase().includes("portfolio"));
                    if (nameLink) {
                        const rawText = nameLink.innerText.trim();
                        name = rawText.split("•")[0].split(String.fromCharCode(10))[0].trim() || "Recruiter";
                    }

                    // Extract poster subtitle / company snippet
                    let company = "";
                    const actorDesc = p.querySelector(
                        ".update-components-actor__description, .feed-shared-actor__description, .update-components-actor__sub-description"
                    );
                    if (actorDesc && actorDesc.innerText) {
                        company = actorDesc.innerText.split(String.fromCharCode(10))[0].trim().slice(0, 100);
                    }

                    // Extract post link or URN fallback
                    let postUrl = "";
                    const postLink = p.querySelector("a[href*='/feed/update/'], a[href*='/posts/'], a[href*='activity:'], a[href*='/jobs/view/']");
                    if (postLink && postLink.href) {
                        postUrl = postLink.href.split("?")[0];
                    } else {
                        const urnHolder = p.closest("[data-urn*='urn:li:'], [data-id*='urn:li:']") ||
                                          p.querySelector("[data-urn*='urn:li:'], [data-id*='urn:li:']");
                        if (urnHolder) {
                            const urn = urnHolder.getAttribute("data-urn") || urnHolder.getAttribute("data-id") || "";
                            const m = urn.match(/urn:li:(?:activity|ugcPost):\d+/);
                            if (m) postUrl = `https://www.linkedin.com/feed/update/${m[0]}/`;
                        }
                    }

                    // Prefer dedicated post commentary container over full card chrome
                    let postText = "";
                    const commentarySelectors = [
                        "[data-test-id='main-feed-activity-card__commentary']",
                        ".feed-shared-update-v2__description",
                        ".update-components-text",
                        ".feed-shared-inline-show-more-text",
                        "div.update-components-update-v2__commentary",
                    ];
                    for (const sel of commentarySelectors) {
                        const el = p.querySelector(sel);
                        if (el && el.innerText && el.innerText.trim().length >= 20) {
                            postText = el.innerText.trim();
                            break;
                        }
                    }
                    if (!postText) {
                        postText = p.innerText || "";
                    }

                    uniqueCards.push({
                        name: name,
                        profile_url: nameLink ? nameLink.href.split("?")[0] : "",
                        company: company,
                        post_url: postUrl,
                        text: postText
                    });
                });

                return uniqueCards;
            }""")
        except Exception as e:
            print(f"[Scraper] ⚠️ Extraction error: {e}")
            extracted_batch = []

        before_count = len(posts_data)

        for raw_item in extracted_batch:
            raw_text = raw_item.get("text", "").strip()
            if not raw_text or len(raw_text) < 15:
                continue

            clean_text = _clean_post_text(raw_text)
            if len(clean_text) < 15:
                continue

            # Deduplication key
            key = raw_item.get("post_url") or clean_text[:100]
            if key in seen_keys:
                continue
            seen_keys.add(key)

            post_record = {
                "post_text": clean_text,
                "poster_name": raw_item.get("name") or "Recruiter",
                "poster_profile_url": raw_item.get("profile_url") or "",
                "company": raw_item.get("company") or "",
                "post_url": raw_item.get("post_url") or "",
                "hashtags": re.findall(r"#\w+", clean_text),
                "scraped_at": datetime.utcnow().isoformat(),
            }
            posts_data.append(post_record)

            display_preview = clean_text[:70].replace('\n', ' ')
            print(f"[Scraper] 📌 Post #{len(posts_data)} collected: {post_record['poster_name']} - '{display_preview}...'")

            if len(posts_data) >= Config.MAX_POSTS_PER_SEARCH:
                break

        # ── Check if new posts were found ─────────────────────
        if len(posts_data) == before_count:
            no_new_streak += 1
            if no_new_streak >= 5:
                print("[Scraper] No new posts after several scrolls — stopping.")
                break
        else:
            no_new_streak = 0

        print(f"[Scraper] 📄 Total collected so far: {len(posts_data)} posts")

        # ── Check 'no results' indicator ──────────────────────
        if page.query_selector(".search-no-results__image"):
            print("[Scraper] LinkedIn says: no more results.")
            break

        # ── Human-like scroll down with configured pause ──────
        print("[Scraper] ⏳ Scrolling down to load more posts...")
        human_scroll(page, direction="down", intensity="normal")

        time.sleep(random.uniform(pause_base * 0.8, pause_base * 1.4))

        if random.random() < 0.25:
            random_idle_behaviour(page)

        scroll_count += 1

    print(f"[Scraper] ✅ '{hashtag_query}' → {len(posts_data)} posts scraped")
    return posts_data


def run_scraper(page: Page) -> list[dict]:
    """
    Master scraper: iterates all unique configured search queries.
    Returns globally deduplicated list of all posts.
    """
    all_posts = []
    all_keys  = set()

    # Deduplicate search queries while preserving order
    unique_queries = []
    seen_queries = set()
    for q in Config.LINKEDIN_HASHTAGS:
        q_norm = q.strip()
        if q_norm and q_norm.lower() not in seen_queries:
            seen_queries.add(q_norm.lower())
            unique_queries.append(q_norm)

    for i, hashtag_query in enumerate(unique_queries):
        try:
            posts = scrape_posts_for_hashtag(page, hashtag_query)
        except SessionInterruptedError as e:
            print(f"\n[Scraper] 🛑 LinkedIn session interrupted ({e})")
            print("[Scraper]    Stopping further queries cleanly instead of looping on a logged-out browser.")
            if os.path.exists(COOKIE_FILE):
                try:
                    os.remove(COOKIE_FILE)
                    print("[Scraper]    Removed expired cookies.json — next run will re-authenticate.")
                except OSError:
                    pass
            break

        for post in posts:
            key = post.get("post_url") or post["post_text"][:100]
            if key not in all_keys:
                all_keys.add(key)
                all_posts.append(post)

        # Human-like gap between different searches
        if i < len(unique_queries) - 1:
            gap = random.uniform(6.0, 14.0)
            print(f"\n[Scraper] ⏳ Waiting {gap:.1f}s before next search query (human behaviour)...")
            human_scroll(page, intensity="slow")
            remaining = gap - 2.0
            if remaining > 0:
                time.sleep(remaining)

    print(f"\n[Scraper] 🎯 Total unique posts: {len(all_posts)}")
    return all_posts
