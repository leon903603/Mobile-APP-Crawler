from __future__ import annotations

import os
import random
import re
import time
import threading

from concurrent.futures import ThreadPoolExecutor, as_completed
from playwright.sync_api import sync_playwright

from db.connection import get_connection

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

MAX_WORKERS = 5  # each worker launches a Chromium instance (~150 MB each)
WAIT_MIN = 0.5
WAIT_MAX = 1.5
BATCH_SIZE = 500
JS_RENDER_WAIT = 1000  # ms to wait after DOM load for JS to finish rendering

_proxy_host = os.environ.get("PROXY_HOST")
_proxy_port = os.environ.get("PROXY_PORT", "8118")
_PROXY = (
    {"server": f"http://{_proxy_host}:{_proxy_port}"}
    if _proxy_host else None
)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

EMAIL_BLACKLIST = {
    "example.com", "domain.com", "email.com", "test.com",
    "sentry.io", "sentry-next.io", "bugsnag.com",
    "wix.com", "squarespace.com", "wordpress.com",
    "amazonaws.com", "cloudfront.net", "fastly.net",
    "apple.com", "google.com", "facebook.com",
    "2x.png", "3x.png",
}

CONTACT_PATHS = ["", "/contact", "/contact-us", "/support", "/about", "/privacy"]


# ──────────────────────────────────────────────
# Thread-local Playwright browser
# ──────────────────────────────────────────────

_local = threading.local()

# Every (playwright, browser) we launch is tracked here so it can be closed on
# shutdown. Without this, Chromium subprocesses are orphaned when their worker
# thread dies and leak indefinitely.
_browsers: list = []
_browsers_lock = threading.Lock()


def _get_browser():
    """One Playwright + Chromium instance per worker thread, reused across calls."""
    if not hasattr(_local, "browser"):
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(
            headless=True,
            proxy=_PROXY,
        )
        _local.playwright = playwright
        _local.browser = browser
        with _browsers_lock:
            _browsers.append((playwright, browser))
    return _local.browser


def _shutdown_browsers() -> None:
    """Close every Chromium/Playwright instance we launched."""
    with _browsers_lock:
        for playwright, browser in _browsers:
            try:
                browser.close()
            except Exception:
                pass
            try:
                playwright.stop()
            except Exception:
                pass
        _browsers.clear()


# ──────────────────────────────────────────────
# Email extraction
# ──────────────────────────────────────────────

def _extract_emails(text: str) -> list[str]:
    raw = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)

    # catch obfuscated patterns: user [at] domain [dot] com
    for match in re.findall(
        r"[a-zA-Z0-9._%+\-]+\s*[\[\(]at[\]\)]\s*[a-zA-Z0-9.\-]+\s*[\[\(]dot[\]\)]\s*[a-zA-Z]{2,}",
        text, re.IGNORECASE,
    ):
        normalized = re.sub(r"\s*[\[\(]at[\]\)]\s*", "@", match, flags=re.IGNORECASE)
        normalized = re.sub(r"\s*[\[\(]dot[\]\)]\s*", ".", normalized, flags=re.IGNORECASE)
        raw.append(normalized)

    seen: set[str] = set()
    results: list[str] = []
    for email in raw:
        email = email.lower().strip(".")
        domain = email.split("@")[-1]
        if domain in EMAIL_BLACKLIST or email in seen:
            continue
        seen.add(email)
        results.append(email)
    return results


# ──────────────────────────────────────────────
# Email scraping
# ──────────────────────────────────────────────

def _scrape_email_from_website(url: str) -> str | None:
    if not url:
        return None

    base = url.rstrip("/")
    browser = _get_browser()
    context = browser.new_context(user_agent=_USER_AGENT)

    try:
        for path in CONTACT_PATHS:
            target = base + path
            page = context.new_page()
            try:
                time.sleep(random.uniform(WAIT_MIN, WAIT_MAX))
                resp = page.goto(target, timeout=15000, wait_until="domcontentloaded")
                if not resp or resp.status != 200:
                    continue
                page.wait_for_timeout(JS_RENDER_WAIT)
                emails = _extract_emails(page.content())
                if emails:
                    return emails[0]
            except Exception:
                continue
            finally:
                page.close()
    finally:
        context.close()

    return None


# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────

def _fetch_unenriched_devs(limit: int) -> list[tuple[int, str]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, website
                FROM developers
                WHERE email IS NULL
                  AND website IS NOT NULL
                  AND website != ''
                LIMIT %s
            """, (limit,))
            return cur.fetchall()


def _update_developer_email(dev_id: int, email: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE developers
                SET email = %s
                WHERE id = %s AND email IS NULL
            """, (email, dev_id))
        conn.commit()


def _mark_developer_no_email(dev_id: int) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE developers
                SET email = 'not_found'
                WHERE id = %s AND email IS NULL
            """, (dev_id,))
        conn.commit()


# ──────────────────────────────────────────────
# Worker
# ──────────────────────────────────────────────

def _enrich_developer(dev_id: int, website: str) -> tuple[int, str | None]:
    email = _scrape_email_from_website(website)
    return dev_id, email


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def enrich_developer_emails() -> None:
    print("[ENRICHMENT] Starting developer email enrichment...")

    # One executor for the whole run: worker threads (and their thread-local
    # Chromium instances) are reused across batches instead of being recreated
    # — and leaked — every iteration.
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        while True:
            devs = _fetch_unenriched_devs(BATCH_SIZE)

            if not devs:
                print("[ENRICHMENT] No unenriched developers remaining. Done.")
                break

            print(f"[ENRICHMENT] Processing batch of {len(devs)} developers...")
            found = 0
            not_found = 0
            errors = 0

            futures = {
                executor.submit(_enrich_developer, dev_id, website): dev_id
                for dev_id, website in devs
            }
            for future in as_completed(futures):
                dev_id = futures[future]
                try:
                    dev_id, email = future.result()
                    if email:
                        _update_developer_email(dev_id, email)
                        print(f"  [✓] dev {dev_id} → {email}")
                        found += 1
                    else:
                        _mark_developer_no_email(dev_id)
                        not_found += 1
                except Exception as e:
                    errors += 1
                    print(f"  [ERROR] dev {dev_id}: {e}")

            print(f"[BATCH DONE] found: {found} | not found: {not_found} | errors: {errors}")

            # Progress guard: every developer normally ends up marked found or
            # not_found, which removes it from the next fetch. If a whole batch
            # only errored (e.g. DB writes failing), the same rows are fetched
            # forever — a tight infinite loop that floods the logs. Bail instead.
            if found == 0 and not_found == 0:
                print("[ENRICHMENT] Batch made no progress (all writes failed); aborting.")
                break

        print("[ENRICHMENT] Complete.")
    finally:
        executor.shutdown(wait=True)
        _shutdown_browsers()


if __name__ == "__main__":
    enrich_developer_emails()
