#!/usr/bin/env python3
"""
Seed Priority Scan:
Fetches high-ranking, well-known apps from Google Play across key categories,
calculates popularity priority (based on installs, reviews, and valid developer emails),
downloads their APKs via apkeep, and injects them into the scan_reports priority queue.
Features exponential backoff to handle Google Play 429 rate limits gracefully.
"""

from __future__ import annotations

import os
import sys
import time
import random
import argparse
from typing import Dict, List, Set

from google_play_scraper import search, app as gplay_app

import config  # Loads .env
from crawlers.google_play import _download_apk, _insert_app
from db.scan_tasks import insert_scan_task, is_scan_completed
from db.connection import get_connection

# ──────────────────────────────────────────────────────────────────────────────
# HIGH-PROFILE CATEGORY KEYWORDS PER COUNTRY
# ──────────────────────────────────────────────────────────────────────────────

COUNTRY_PRESETS: Dict[str, Dict[str, any]] = {
    "tw": {
        "lang": "zh-TW",
        "keywords": [
            "金融", "銀行", "社群", "通訊", "購物",
            "生活", "工具", "交通", "旅遊", "新聞", "電子支付"
        ],
    },
    "us": {
        "lang": "en",
        "keywords": [
            "banking", "finance", "social", "shopping", "productivity",
            "tools", "communication", "travel", "lifestyle", "entertainment"
        ],
    },
    "jp": {
        "lang": "ja",
        "keywords": [
            "銀行", "金融", "SNS", "買い物", "生活",
            "ツール", "旅行", "ニュース", "仕事効率化"
        ],
    },
}


def _safe_search(term: str, country: str, lang: str, n_hits: int) -> list[dict]:
    """Search Google Play with exponential backoff on 429 rate limit."""
    for attempt in range(4):
        try:
            return search(term, lang=lang, country=country, n_hits=n_hits)
        except Exception as e:
            msg = str(e).lower()
            if any(k in msg for k in ("429", "too many", "connection", "timeout", "incompleteread")):
                sleep_s = 5 * (2 ** attempt) + random.uniform(1, 3)
                print(f"       [BACKOFF] Search 429/timeout for '{term}'. Backoff {sleep_s:.1f}s (Attempt {attempt+1}/4)...")
                time.sleep(sleep_s)
            else:
                print(f"       [WARN] Search failed for '{term}': {e}")
                return []
    return []


def _safe_fetch(app_id: str, country: str, lang: str) -> dict | None:
    """Fetch app details with exponential backoff on 429 rate limit."""
    for attempt in range(4):
        try:
            time.sleep(0.2)
            return gplay_app(app_id, lang=lang, country=country)
        except Exception as e:
            msg = str(e).lower()
            if any(k in msg for k in ("429", "too many", "connection", "timeout", "incompleteread")):
                sleep_s = 5 * (2 ** attempt) + random.uniform(1, 3)
                print(f"       [BACKOFF] Fetch 429/timeout for '{app_id}'. Backoff {sleep_s:.1f}s (Attempt {attempt+1}/4)...")
                time.sleep(sleep_s)
            else:
                print(f"       [WARN] Fetch failed for {app_id}: {e}")
                return None
    return None


def calculate_priority(app_info: dict) -> int:
    """
    Computes priority score (0 - 100) based on popularity metrics:
    - Base priority: 50
    - Downloads >= 1,000,000 (+30) or >= 100,000 (+20)
    - Has valid developer email (+20) (actionable for outreach)
    """
    score = 50
    min_installs = app_info.get("minInstalls") or 0
    if min_installs >= 1_000_000:
        score += 30
    elif min_installs >= 100_000:
        score += 20

    dev_email = app_info.get("developerEmail")
    if dev_email and "@" in dev_email and "not_found" not in dev_email.lower():
        score += 20

    return min(100, score)


def seed_priority_apps(
    countries: List[str],
    top_per_kw: int = 15,
    min_installs_filter: int = 100_000,
    dry_run: bool = False,
    override_priority: int | None = None,
):
    print("=" * 65)
    print(" [PRIORITY SEEDER] Starting High-Profile App Seeder")
    print(f" Countries: {countries} | Top/Keyword: {top_per_kw} | Min Installs: {min_installs_filter:,}")
    print(f" Mode: {'[DRY RUN]' if dry_run else '[LIVE DOWNLOAD & QUEUE]'}")
    print("=" * 65)

    seen_app_ids: Set[str] = set()
    total_found = 0
    total_queued = 0
    total_skipped = 0

    for country in countries:
        preset = COUNTRY_PRESETS.get(country, {"lang": "en", "keywords": ["finance", "tools", "social"]})
        lang = preset["lang"]
        keywords = preset["keywords"]

        print(f"\n[*] Scanning Country: {country.upper()} (lang: {lang}, keywords: {len(keywords)})")

        for kw in keywords:
            print(f"    -> Searching keyword: 「{kw}」...")
            results = _safe_search(kw, country=country, lang=lang, n_hits=top_per_kw)

            for item in results:
                app_id = item.get("appId")
                if not app_id or app_id in seen_app_ids:
                    continue
                seen_app_ids.add(app_id)
                total_found += 1

                # Fetch full metadata with backoff protection
                info = _safe_fetch(app_id, country=country, lang=lang)
                if not info:
                    continue

                title = info.get("title", app_id)
                dev = info.get("developer", "Unknown")
                email = info.get("developerEmail", "None")
                installs = info.get("minInstalls") or 0
                version = info.get("version") or "unknown"
                priority = override_priority if override_priority is not None else calculate_priority(info)

                # Skip apps below install threshold unless explicitly requested
                if installs < min_installs_filter:
                    continue

                print(f"       [CANDIDATE] {title} ({app_id})")
                print(f"                   Installs: {installs:,}+ | Dev: {dev} | Email: {email} | Priority: {priority}")

                if dry_run:
                    total_queued += 1
                    continue

                # Live DB insert
                try:
                    app_db_id = _insert_app(info, country=country)
                    if not app_db_id:
                        continue

                    # Check deduplication
                    if is_scan_completed(app_db_id, version):
                        print(f"                   [SKIP] Already scanned (v{version}).")
                        total_skipped += 1
                        continue

                    # Download APK
                    print(f"                   [DOWNLOAD] Downloading APK via apkeep...")
                    apk_path = _download_apk(app_id, version)
                    if apk_path and os.path.exists(apk_path):
                        task_id = insert_scan_task(
                            app_db_id=app_db_id,
                            version=version,
                            apk_path=apk_path,
                            priority=priority,
                        )
                        print(f"                   [QUEUED] scan_reports Task #{task_id} (Priority: {priority})")
                        total_queued += 1
                    else:
                        print(f"                   [WARN] APK download failed for {app_id}")

                except Exception as e:
                    print(f"                   [ERROR] Failed to process {app_id}: {e}")

    print("\n" + "=" * 65)
    print(f" [SEEDER SUMMARY] Found unique: {total_found} | Queued: {total_queued} | Already Scanned: {total_skipped}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(description="Seed priority well-known apps into scan queue")
    parser.add_argument(
        "--countries",
        type=str,
        default="tw,us,jp",
        help="Comma-separated country codes (default: tw,us,jp)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Top hits per category keyword (default: 10)"
    )
    parser.add_argument(
        "--min-installs",
        type=int,
        default=500_000,
        help="Minimum downloads required to queue (default: 500,000)"
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=None,
        help="Force static priority value (default: computed 70-100)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview candidate apps without downloading or writing DB"
    )
    args = parser.parse_args()

    country_list = [c.strip().lower() for c in args.countries.split(",") if c.strip()]
    seed_priority_apps(
        countries=country_list,
        top_per_kw=args.top,
        min_installs_filter=args.min_installs,
        dry_run=args.dry_run,
        override_priority=args.priority,
    )


if __name__ == "__main__":
    main()
