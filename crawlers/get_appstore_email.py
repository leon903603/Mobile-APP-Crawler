import os
import random
import re
import requests
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from db.connection import get_connection

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

MAX_WORKERS = 10
WAIT_MIN = 0.5
WAIT_MAX = 1.5
BATCH_SIZE = 500  # how many devs to pull from DB per iteration

_proxy_host = os.environ.get("PROXY_HOST")
_proxy_port = os.environ.get("PROXY_PORT", "8118")
PROXIES = (
    {
        "http":  f"http://{_proxy_host}:{_proxy_port}",
        "https": f"http://{_proxy_host}:{_proxy_port}",
    }
    if _proxy_host else None
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Domains commonly found in HTML that are not real developer emails
EMAIL_BLACKLIST = {
    "example.com", "domain.com", "email.com", "test.com",
    "sentry.io", "sentry-next.io", "bugsnag.com",
    "wix.com", "squarespace.com", "wordpress.com",
    "amazonaws.com", "cloudfront.net", "fastly.net",
    "apple.com", "google.com", "facebook.com",
    "2x.png", "3x.png",  # catches image filenames that look like emails
}

# Pages to try beyond the root URL — devs often put contact info here
CONTACT_PATHS = ["", "/contact", "/contact-us", "/support", "/about", "/privacy"]


# ──────────────────────────────────────────────
# Email extraction
# ──────────────────────────────────────────────

def _extract_emails(text: str) -> list[str]:
    """Pull all email addresses from raw HTML/text, filtered against blacklist."""
    raw = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    seen = set()
    results = []
    for email in raw:
        email = email.lower().strip(".")
        domain = email.split("@")[-1]
        if domain in EMAIL_BLACKLIST:
            continue
        if email in seen:
            continue
        seen.add(email)
        results.append(email)
    return results


def _scrape_email_from_website(url: str) -> str | None:
    """
    Try root URL + common contact paths. Return first valid email found.
    Tries /contact, /support, /about before giving up.
    """
    if not url:
        return None

    # Normalise — strip trailing slash
    base = url.rstrip("/")

    for path in CONTACT_PATHS:
        target = base + path
        try:
            time.sleep(random.uniform(WAIT_MIN, WAIT_MAX))
            resp = requests.get(
                target,
                headers=HEADERS,
                timeout=10,
                proxies=PROXIES,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                continue

            emails = _extract_emails(resp.text)
            if emails:
                return emails[0]  # take first valid hit

        except Exception:
            continue  # dead link, timeout, SSL error — move on

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

    while True:
        devs = _fetch_unenriched_devs(BATCH_SIZE)

        if not devs:
            print("[ENRICHMENT] No unenriched developers remaining. Done.")
            break

        print(f"[ENRICHMENT] Processing batch of {len(devs)} developers...")
        found = 0
        not_found = 0

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
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
                    print(f"  [ERROR] dev {dev_id}: {e}")

        print(f"[BATCH DONE] found: {found} | not found: {not_found}")

    print("[ENRICHMENT] Complete.")


if __name__ == "__main__":
    enrich_developer_emails()