#!/usr/bin/env python3
"""
Backfill Scan Tasks (Pure Offline DB Selection):
Extracts high-priority Google Play apps already stored in the database that:
1. Have valid developer emails (non-empty, not 'not_found')
2. Have NEVER been queued into scan_reports before
3. Have NEVER received an outreach email before
Downloads their APKs via host apkeep and injects them directly into scan_reports.
"""

from __future__ import annotations

import os
import sys
import argparse
from typing import List, Tuple

import config  # Loads .env automatically
from db.connection import get_connection
from db.scan_tasks import insert_scan_task
from crawlers.google_play import _download_apk


def fetch_candidate_apps(limit: int = 50, country: str | None = None) -> List[Tuple]:
    """
    Selects un-scanned Google Play apps with valid developer emails from existing DB inventory.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT
                    a.id          AS app_db_id,
                    a.app_id      AS app_id,
                    a.app_name    AS app_name,
                    a.country     AS country,
                    d.name        AS developer_name,
                    d.email       AS developer_email,
                    COALESCE(a.min_installs, 0) AS min_installs
                FROM apps a
                JOIN developers d ON a.developer_id = d.id
                WHERE a.store = 'google_play'
                  AND d.email IS NOT NULL
                  AND d.email NOT IN ('', 'not_found')
                  -- Never queued for scan before
                  AND NOT EXISTS (
                      SELECT 1
                      FROM scan_reports sr
                      WHERE sr.app_db_id = a.id
                  )
                  -- Never emailed before
                  AND NOT EXISTS (
                      SELECT 1
                      FROM email_log el
                      WHERE el.email = d.email
                        AND el.status = 'sent'
                  )
            """
            params = []
            if country:
                query += " AND a.country = %s"
                params.append(country)

            query += """
                ORDER BY
                    COALESCE(a.min_installs, 0) DESC,
                    COALESCE(a.ratings_count, 0) DESC,
                    a.id ASC
                LIMIT %s;
            """
            params.append(limit)

            cur.execute(query, tuple(params))
            return cur.fetchall()


def run_backfill(limit: int = 50, country: str | None = None, dry_run: bool = False, priority: int = 100):
    print("=" * 65)
    print(" [BACKFILL] Starting Offline DB Scan Task Ingestion")
    print(f" Target Limit: {limit} | Country: {country or 'ALL'} | Dry-Run: {dry_run} | Priority: {priority}")
    print("=" * 65)

    candidates = fetch_candidate_apps(limit=limit, country=country)
    if not candidates:
        print("[i] No candidate apps found matching criteria in database.")
        return

    print(f"[*] Found {len(candidates)} un-scanned candidate app(s) in database.\n")

    queued_count = 0
    failed_download = 0

    for idx, (app_db_id, app_id, app_name, app_country, dev_name, dev_email, installs) in enumerate(candidates, start=1):
        print(f"--- [{idx}/{len(candidates)}] App: {app_name} ({app_id}) ---")
        print(f"    Country: {app_country} | Dev: {dev_name} | Email: {dev_email} | Installs: {installs:,}")

        if dry_run:
            print(f"    [DRY-RUN] Would download APK and queue scan_reports (priority={priority})")
            queued_count += 1
            continue

        # Download APK using host apkeep
        print(f"    [DOWNLOAD] Downloading APK via apkeep...")
        apk_path = _download_apk(app_id, version=None)

        if apk_path and os.path.exists(apk_path):
            file_size_mb = os.path.getsize(apk_path) / (1024 * 1024)
            print(f"    [SUCCESS] APK downloaded: {apk_path} ({file_size_mb:.2f} MB)")

            task_id = insert_scan_task(
                app_db_id=app_db_id,
                version="latest",
                apk_path=apk_path,
                priority=priority,
            )
            print(f"    [QUEUED] Created scan_reports task #{task_id} with priority={priority}")
            queued_count += 1
        else:
            print(f"    [FAILED] Could not download APK for {app_id}. Skipping.")
            failed_download += 1

    print("\n" + "=" * 65)
    print(f" [BACKFILL SUMMARY] Total Processed: {len(candidates)} | Queued: {queued_count} | Download Failed: {failed_download}")
    print("=" * 65)


def main():
    parser = argparse.ArgumentParser(
        description="Backfill un-scanned apps from existing DB inventory into scan_reports queue"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of apps to backfill (default: 50)"
    )
    parser.add_argument(
        "--country",
        type=str,
        default=None,
        help="Filter candidates by country code (e.g. tw, us, jp)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview candidate list without downloading APKs or modifying DB"
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=100,
        help="Priority weighting for queued scan tasks (default: 100)"
    )
    args = parser.parse_args()

    run_backfill(
        limit=args.limit,
        country=args.country,
        dry_run=args.dry_run,
        priority=args.priority,
    )


if __name__ == "__main__":
    main()
