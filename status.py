#!/usr/bin/env python3
"""
Pipeline Status Dashboard:
Displays real-time metrics across crawled apps, developers, scan reports, and outreach email logs.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

import config
from db.connection import get_connection


def print_dashboard():
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Apps Count
            cur.execute("SELECT store, COUNT(*) FROM apps GROUP BY store ORDER BY store;")
            apps_by_store = dict(cur.fetchall())
            total_apps = sum(apps_by_store.values())

            # 2. Developers & Emails
            cur.execute("""
                SELECT
                    COUNT(*) AS total_devs,
                    COUNT(*) FILTER (WHERE email IS NOT NULL AND email != 'not_found' AND email != '') AS mailable_devs
                FROM developers;
            """)
            dev_row = cur.fetchone()
            total_devs, mailable_devs = dev_row[0], dev_row[1]

            # 3. Scan Reports by Status & Priority
            cur.execute("""
                SELECT status, COUNT(*)
                FROM scan_reports
                GROUP BY status
                ORDER BY status;
            """)
            scan_stats = dict(cur.fetchall())

            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE priority >= 80) AS high_priority,
                    COUNT(*) FILTER (WHERE priority >= 50 AND priority < 80) AS med_priority,
                    COUNT(*) FILTER (WHERE priority < 50) AS low_priority
                FROM scan_reports
                WHERE status = 'pending';
            """)
            p_row = cur.fetchone()
            high_p, med_p, low_p = p_row[0], p_row[1], p_row[2]

            # 4. Email Log
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE sent_at::date = CURRENT_DATE AND status = 'sent') AS sent_today,
                    COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '7 days' AND status = 'sent') AS sent_week,
                    COUNT(*) FILTER (WHERE status = 'sent') AS sent_total,
                    COUNT(*) FILTER (WHERE status = 'failed') AS failed_total,
                    COUNT(*) FILTER (WHERE status = 'dry_run') AS dry_run_total
                FROM email_log;
            """)
            email_row = cur.fetchone()
            sent_today, sent_week, sent_total, failed_total, dry_run_total = email_row

    # Render Dashboard
    print("\n" + "╔" + "═" * 60 + "╗")
    print(f"║ {'CMAA Pipeline Real-Time Dashboard':^58} ║")
    print(f"║ {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^58} ║")
    print("╠" + "═" * 60 + "╣")
    print(f"║ 📱 APP Inventory                                           ║")
    print(f"║   • Total Apps Recorded       : {total_apps:>12,}               ║")
    print(f"║     - Apple App Store         : {apps_by_store.get('app_store', 0):>12,}               ║")
    print(f"║     - Google Play             : {apps_by_store.get('google_play', 0):>12,}               ║")
    print(f"║   • Developers Recorded       : {total_devs:>12,}               ║")
    print(f"║   • Mailable Developers (Email): {mailable_devs:>12,}               ║")
    print("╠" + "═" * 60 + "╣")
    print(f"║ 🛡️ Security Scan Queue (scan_reports)                       ║")
    print(f"║   • Completed ('done')        : {scan_stats.get('done', 0):>12,}               ║")
    print(f"║   • In-Progress ('running')   : {scan_stats.get('running', 0):>12,}               ║")
    print(f"║   • Pending Queue             : {scan_stats.get('pending', 0):>12,}               ║")
    print(f"║     - High Priority (>=80)    : {high_p:>12,}               ║")
    print(f"║     - Medium Priority (50-79) : {med_p:>12,}               ║")
    print(f"║     - Low Priority (<50)      : {low_p:>12,}               ║")
    print(f"║   • Failed / Dead             : {scan_stats.get('dead', 0):>12,}               ║")
    print("╠" + "═" * 60 + "╣")
    print(f"║ ✉️ Outreach Email Outreach (Resend)                        ║")
    print(f"║   • Sent Today (Quota: 5)     : {sent_today:>12,}               ║")
    print(f"║   • Sent This Week (Quota: 25): {sent_week:>12,}               ║")
    print(f"║   • Sent All-Time             : {sent_total:>12,}               ║")
    print(f"║   • Failed Dispatches         : {failed_total:>12,}               ║")
    print(f"║   • Dry-Run Simulations       : {dry_run_total:>12,}               ║")
    print("╚" + "═" * 60 + "╝\n")


if __name__ == "__main__":
    print_dashboard()
