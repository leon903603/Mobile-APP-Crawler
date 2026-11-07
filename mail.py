from __future__ import annotations

import os
import sys
import time
import argparse
from datetime import datetime
from db.connection import get_connection
import config  # Ensure environment variables are loaded via config.load_env()

from email_pipeline import (
    can_dispatch_email,
    get_random_throttle_delay,
    build_outreach_email,
    dispatch_outreach_email,
    DEFAULT_FROM_EMAIL,
    DEFAULT_REPLY_TO,
    OPT_OUT_STATEMENT,
)


# ──────────────────────────────────────────────
# Daily sent count query from DB (Timezone-Aware)
# ──────────────────────────────────────────────
def get_daily_sent_count() -> int:
    """
    Returns the total number of emails dispatched today (status = 'sent')
    aligned to the local Asia/Taipei calendar date.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM email_log
                WHERE status = 'sent'
                  AND (sent_at AT TIME ZONE 'Asia/Taipei')::date = (NOW() AT TIME ZONE 'Asia/Taipei')::date;
            """)
            row = cur.fetchone()
            return row[0] if row else 0


# ──────────────────────────────────────────────
# Weekly sent count query from DB
# ──────────────────────────────────────────────
def get_weekly_sent_count() -> int:
    """
    Returns the total number of emails dispatched in the last 7 days (status = 'sent').
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM email_log
                WHERE status = 'sent'
                  AND sent_at > NOW() - INTERVAL '7 days';
            """)
            row = cur.fetchone()
            return row[0] if row else 0


# ──────────────────────────────────────────────
# Fetch scan reports ready for emailing from DB
# ──────────────────────────────────────────────
def get_pending_report_emails(limit: int = 10, country: str = None) -> list[tuple]:
    """
    Fetch done scan reports ordered by PRIORITY DESC, excluding:
    - Invalid or 'not_found' developer emails
    - Developers who have received any outreach email within the last 14 days (Anti-Spam Cooldown)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT
                    d.id            AS developer_id,
                    d.name          AS developer_name,
                    d.email         AS developer_email,
                    a.id            AS app_db_id,
                    a.app_id        AS app_id,
                    a.app_name      AS app_name,
                    a.store         AS store,
                    sr.id           AS scan_report_id,
                    sr.version      AS version,
                    sr.excerpt_path AS excerpt_path
                FROM scan_reports sr
                JOIN apps a ON sr.app_db_id = a.id
                JOIN developers d ON a.developer_id = d.id
                WHERE d.email IS NOT NULL
                  AND d.email <> 'not_found'
                  AND d.email <> ''
                  AND sr.status = 'done'
                  AND sr.excerpt_path IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM email_log el
                      WHERE el.email = d.email
                        AND el.status = 'sent'
                        AND el.sent_at > NOW() - INTERVAL '14 days'
                  )
            """
            params = []
            if country:
                query += " AND a.country = %s"
                params.append(country)

            query += " ORDER BY sr.priority DESC, sr.id ASC LIMIT %s"
            params.append(limit)

            cur.execute(query, tuple(params))
            return cur.fetchall()


# ──────────────────────────────────────────────
# Log email sending status
# ──────────────────────────────────────────────
def log_email_result(developer_id: int, email: str, scan_report_id: int, status: str, error: str = None):
    """
    Records sending status in email_log table to prevent duplicate emails.
    Maintains ON CONFLICT (email, scan_report_id) DO UPDATE.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO email_log (developer_id, email, scan_report_id, status, error, sent_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (email, scan_report_id) DO UPDATE SET
                    status  = EXCLUDED.status,
                    error   = EXCLUDED.error,
                    sent_at = NOW()
            """, (developer_id, email, scan_report_id, status, error))
            conn.commit()


# ──────────────────────────────────────────────
# Send outreach email via Resend API
# ──────────────────────────────────────────────
def send_outreach_email(
    to_email: str,
    developer_name: str,
    app_name: str,
    attachments: list[dict] | None = None,
    attachment_paths: list[str] | None = None,
    dry_run: bool = True,
    api_key: str | None = None,
) -> dict:
    """
    Constructs the official outreach payload with responsive HTML & PDF excerpt
    and dispatches via Resend API.
    """
    payload = build_outreach_email(
        to_email=to_email,
        developer_name=developer_name,
        app_name=app_name,
        attachments=attachments,
        attachment_paths=attachment_paths,
    )
    return dispatch_outreach_email(
        email_payload=payload,
        dry_run=dry_run,
        api_key=api_key,
    )


def send_report_email(*args, **kwargs):
    """
    Backward-compatibility alias. Redirects legacy calls to send_outreach_email.
    """
    to_email = kwargs.get("to_email") or (args[0] if len(args) > 0 else "")
    developer_name = kwargs.get("developer_name") or (args[1] if len(args) > 1 else "")
    app_name = kwargs.get("app_name") or (args[2] if len(args) > 2 else "")
    dry_run = kwargs.get("dry_run", False)
    return send_outreach_email(
        to_email=to_email,
        developer_name=developer_name,
        app_name=app_name,
        dry_run=dry_run,
    )


# ──────────────────────────────────────────────
# Main Runner
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Hardened Resend Cold Outreach Runner for App Developers"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate email sending without contacting Resend API"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of emails to send in this run (default: 5)"
    )
    parser.add_argument(
        "--daily-quota",
        type=int,
        default=int(os.environ.get("OUTREACH_DAILY_QUOTA", 5)),
        help="Maximum total daily sent limit across all runs (default: 5)"
    )
    parser.add_argument(
        "--weekly-quota",
        type=int,
        default=int(os.environ.get("OUTREACH_WEEKLY_QUOTA", 25)),
        help="Maximum total weekly sent limit across all runs (default: 25)"
    )
    parser.add_argument(
        "--country",
        type=str,
        default=None,
        help="Filter by country code (e.g. tw)"
    )
    parser.add_argument(
        "--test-email",
        type=str,
        default=None,
        help="Override recipient email for manual verification / single live test"
    )
    parser.add_argument(
        "--skip-delay",
        action="store_true",
        help="Skip 180-420s throttle delay (strictly for dry-run or testing)"
    )
    parser.add_argument(
        "--bypass-hours",
        action="store_true",
        help="Bypass working hour and weekend check (strictly for offline testing / emergency manual runs)"
    )
    args = parser.parse_args()

    api_key = os.environ.get("RESEND_API_KEY")
    if not args.dry_run and not api_key:
        print("[!] Error: RESEND_API_KEY environment variable is required for live dispatch.")
        print("    Set RESEND_API_KEY in .env or run with --dry-run for simulation.")
        sys.exit(1)

    # 1. Guard check before starting batch
    now = datetime.now()
    daily_count = get_daily_sent_count()
    weekly_count = get_weekly_sent_count()
    allowed, reason = can_dispatch_email(
        now=now,
        daily_sent_count=daily_count,
        weekly_sent_count=weekly_count,
        quota_limit=args.daily_quota,
        weekly_quota_limit=args.weekly_quota,
        bypass_hours=args.bypass_hours,
    )

    print(f"[i] Pre-dispatch Guard check: Sent today={daily_count}/{args.daily_quota}, week={weekly_count}/{args.weekly_quota}, Time={now.strftime('%H:%M:%S')}")
    if not allowed:
        print(f"[!] Dispatch halted by Guard policy: {reason}")
        return

    # 2. Query pending records
    rows = get_pending_report_emails(limit=args.limit, country=args.country)
    if not rows:
        print("[i] No pending scan reports found to email.")
        return

    print(
        f"[i] Retrieved {len(rows)} pending report(s) "
        f"(dry_run={args.dry_run}, limit={args.limit}, country={args.country}, test_email={args.test_email})"
    )

    dispatched_count = 0
    project_root = os.path.dirname(os.path.abspath(__file__))

    for idx, row in enumerate(rows, start=1):
        dev_id, dev_name, db_email, app_db_id, app_id, app_name, store, scan_report_id, version, excerpt_path = row
        recipient = args.test_email if args.test_email else db_email

        # Guard re-check for each recipient
        current_time = datetime.now()
        allowed, reason = can_dispatch_email(
            now=current_time,
            daily_sent_count=daily_count,
            weekly_sent_count=weekly_count,
            quota_limit=args.daily_quota,
            weekly_quota_limit=args.weekly_quota,
            bypass_hours=args.bypass_hours,
        )
        if not allowed:
            print(f"[!] Stopping batch dispatch: {reason}")
            break

        print(f"\n--- [{idx}/{len(rows)}] Processing App: {app_name} (ID: {app_id}) ---")
        print(f"    Recipient: {recipient} (Dev: {dev_name})")
        if args.test_email:
            print(f"    [TEST MODE] Original Dev Email: {db_email} overridden to {args.test_email}")

        # Resolve excerpt path
        attachment_paths = []
        if excerpt_path:
            abs_path = excerpt_path if os.path.isabs(excerpt_path) else os.path.join(project_root, excerpt_path)
            if os.path.exists(abs_path):
                attachment_paths.append(abs_path)
                print(f"    [ATTACHMENT] Attached 2-page PDF excerpt: {abs_path}")
            else:
                print(f"    [WARN] Excerpt file not found at: {abs_path}")

        try:
            res = send_outreach_email(
                to_email=recipient,
                developer_name=dev_name,
                app_name=app_name,
                attachment_paths=attachment_paths,
                dry_run=args.dry_run,
                api_key=api_key,
            )

            if res.get("ok"):
                mode_str = "[DRY-RUN]" if args.dry_run else "[LIVE]"
                msg_id = res.get("id", "N/A")
                print(f"{mode_str} [+] Successfully processed outreach to {recipient} (Msg ID: {msg_id})")

                # If test mode, log as 'test' so it doesn't block actual developer or pollute stats
                if args.test_email:
                    log_status = "test"
                else:
                    log_status = "dry_run" if args.dry_run else "sent"

                log_email_result(
                    developer_id=dev_id,
                    email=recipient if args.test_email else db_email,
                    scan_report_id=scan_report_id,
                    status=log_status,
                )
                if not args.dry_run and not args.test_email:
                    daily_count += 1
                    weekly_count += 1
                dispatched_count += 1
            else:
                err_msg = res.get("error", "Unknown dispatch failure")
                print(f"[!] Dispatch failed for {recipient}: {err_msg}")
                log_email_result(
                    developer_id=dev_id,
                    email=recipient if args.test_email else db_email,
                    scan_report_id=scan_report_id,
                    status="failed",
                    error=err_msg,
                )

        except Exception as e:
            print(f"[!] Exception during dispatch for {recipient}: {e}")
            log_email_result(
                developer_id=dev_id,
                email=recipient if args.test_email else db_email,
                scan_report_id=scan_report_id,
                status="failed",
                error=str(e),
            )

        # 3. Throttle delay between emails
        if idx < len(rows):
            if args.skip_delay:
                print("[i] Skip delay flag active; proceeding immediately to next email.")
            else:
                delay = get_random_throttle_delay(180, 420)
                print(f"[i] Simulating human throttle delay: sleeping for {delay} seconds ({delay // 60}m {delay % 60}s)...")
                time.sleep(delay)

    print(f"\n[✓] Batch completed. Total dispatched in this run: {dispatched_count}")


if __name__ == "__main__":
    main()
