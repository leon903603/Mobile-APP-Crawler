from __future__ import annotations

import os
import smtplib
import json
import time
import random
import argparse
from email.message import EmailMessage
from db.connection import get_connection


# ──────────────────────────────────────────────
# Config (env vars with config.json fallback)
# ──────────────────────────────────────────────
def _load_credentials():
    gmail_user = os.environ.get("GMAIL_USER") or os.environ.get("EMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("EMAIL_PASSWORD")

    if (not gmail_user or not gmail_password) and os.path.exists("config.json"):
        try:
            with open("config.json") as f:
                config = json.load(f)
                gmail_user = gmail_user or config.get("email_user")
                gmail_password = gmail_password or config.get("email_password")
        except Exception as e:
            print(f"[WARN] Could not load config.json: {e}")

    return gmail_user, gmail_password


# ──────────────────────────────────────────────
# Fetch scan reports ready for emailing from DB
# ──────────────────────────────────────────────
def get_pending_report_emails(limit: int = 10, country: str = None) -> list[tuple]:
    """
    Fetch done scan reports for developers who have a valid email,
    excluding NULL and 'not_found', and excluding already sent reports in email_log.
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
                        AND el.scan_report_id = sr.id
                        AND el.status = 'sent'
                  )
            """
            params = []
            if country:
                query += " AND a.country = %s"
                params.append(country)

            query += " ORDER BY sr.id ASC LIMIT %s"
            params.append(limit)

            cur.execute(query, tuple(params))
            return cur.fetchall()


# ──────────────────────────────────────────────
# Log email sending status
# ──────────────────────────────────────────────
def log_email_result(developer_id: int, email: str, scan_report_id: int, status: str, error: str = None):
    """
    Records sending status in email_log table to prevent duplicate emails.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO email_log (developer_id, email, scan_report_id, status, error)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (email, scan_report_id) DO UPDATE SET
                    status  = EXCLUDED.status,
                    error   = EXCLUDED.error,
                    sent_at = NOW()
            """, (developer_id, email, scan_report_id, status, error))
            conn.commit()


# ──────────────────────────────────────────────
# Send email via Gmail SMTP
# ──────────────────────────────────────────────
def send_report_email(
    to_email: str,
    developer_name: str,
    app_name: str,
    excerpt_path: str,
    gmail_user: str,
    gmail_password: str,
    dry_run: bool = False
):
    """
    Sends personalized scan report excerpt PDF to developer.
    """
    if dry_run:
        print(f"[DRY-RUN] Would send report for '{app_name}' to {to_email} (attachment: {excerpt_path})")
        return

    if not gmail_user or not gmail_password:
        raise ValueError("Missing email_user or email_password credentials")

    msg = EmailMessage()
    msg["Subject"] = f"Mobile App Analysis Report: {app_name}"
    msg["From"] = gmail_user
    msg["To"] = to_email

    body = (
        f"Dear {developer_name},\n\n"
        f"Please find attached the analysis report excerpt for your application '{app_name}'.\n\n"
        "Best regards,\nMobile App Security & Analysis Team"
    )
    msg.set_content(body)

    if excerpt_path and os.path.exists(excerpt_path):
        with open(excerpt_path, "rb") as f:
            pdf_data = f.read()

        filename = os.path.basename(excerpt_path)
        msg.add_attachment(
            pdf_data,
            maintype="application",
            subtype="pdf",
            filename=filename
        )
    else:
        raise FileNotFoundError(f"Excerpt PDF not found: {excerpt_path}")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_password)
        server.send_message(msg)

    print(f"[+] Sent report for '{app_name}' to {to_email}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Send app analysis report excerpts to developers")
    parser.add_argument("--dry-run", action="store_true", help="Simulate email sending without contacting SMTP")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of emails to send (default: 10)")
    parser.add_argument("--country", type=str, default=None, help="Filter by country code (e.g. tw)")
    args = parser.parse_args()

    gmail_user, gmail_password = _load_credentials()

    if not args.dry_run and (not gmail_user or not gmail_password):
        raise ValueError("Missing email_user or email_password in environment or config.json (use --dry-run to test)")

    rows = get_pending_report_emails(limit=args.limit, country=args.country)

    if not rows:
        print("[i] No pending scan reports to send")
        return

    print(f"[i] Found {len(rows)} report(s) to send (dry_run={args.dry_run}, limit={args.limit}, country={args.country})...")

    for row in rows:
        dev_id, dev_name, email, app_db_id, app_id, app_name, store, scan_report_id, version, excerpt_path = row

        try:
            send_report_email(
                to_email=email,
                developer_name=dev_name,
                app_name=app_name,
                excerpt_path=excerpt_path,
                gmail_user=gmail_user,
                gmail_password=gmail_password,
                dry_run=args.dry_run
            )

            status = "dry_run" if args.dry_run else "sent"
            log_email_result(
                developer_id=dev_id,
                email=email,
                scan_report_id=scan_report_id,
                status=status
            )

        except Exception as e:
            print(f"[!] Failed for {email} ({app_name}): {e}")
            log_email_result(
                developer_id=dev_id,
                email=email,
                scan_report_id=scan_report_id,
                status="failed",
                error=str(e)
            )

        # Rate limiting: 3 to 5 seconds per email
        delay = random.uniform(3.0, 5.0)
        print(f"[i] Rate limit delay: {delay:.2f}s...")
        time.sleep(delay)


if __name__ == "__main__":
    main()