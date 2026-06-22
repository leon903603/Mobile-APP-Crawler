import os
import smtplib
import json
from email.mime.text import MIMEText

from db.connection import get_connection


# ──────────────────────────────────────────────
# Config (use env vars)
# ──────────────────────────────────────────────
with open("config.json") as f:
    config = json.load(f)
GMAIL_USER = config["email_user"]
GMAIL_APP_PASSWORD = config["email_password"]


# ──────────────────────────────────────────────
# Fetch emails from DB
# ──────────────────────────────────────────────
def get_developer_emails(limit=10):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT email
        FROM developers
        WHERE email IS NOT NULL
        LIMIT %s
    """, (limit,))

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return [row[0] for row in rows]


# ──────────────────────────────────────────────
# Send email via Gmail SMTP
# ──────────────────────────────────────────────
def send_email(to_email):
    msg = MIMEText("Hello World")
    msg["Subject"] = "Test Email"
    msg["From"] = GMAIL_USER
    msg["To"] = to_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"[+] Sent to {to_email}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise Exception("Missing GMAIL_USER or GMAIL_APP_PASSWORD environment variables")

    emails = get_developer_emails(limit=5)

    if not emails:
        print("[!] No emails found in database")
        return

    print(f"[i] Sending to {len(emails)} emails...")

    for email in emails:
        try:
            send_email(email)
        except Exception as e:
            print(f"[!] Failed for {email}: {e}")


if __name__ == "__main__":
    main()