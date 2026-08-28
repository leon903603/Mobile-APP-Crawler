import os
import smtplib
import json
from collections import defaultdict
from email.mime.text import MIMEText
from email.message import EmailMessage
from db.connection import get_connection


# ──────────────────────────────────────────────
# Config (use env vars)
# ──────────────────────────────────────────────
with open("config.json") as f:
    config = json.load(f)
GMAIL_USER = config.get("email_user")
GMAIL_APP_PASSWORD = config.get("email_password")


# ──────────────────────────────────────────────
# Fetch emails from DB
# ──────────────────────────────────────────────
def get_developer_apps(limit=10, country=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if country:
                cur.execute("""
                    SELECT d.email, a.store
                    FROM developers d
                    JOIN apps a ON a.developer_id = d.id
                    WHERE d.email IS NOT NULL AND d.email <> 'not_found'
                    AND a.country = %s
                    LIMIT %s
                """, (country, limit))
            else:
                cur.execute("""
                    SELECT d.email, a.store
                    FROM developers d
                    JOIN apps a ON a.developer_id = d.id
                    WHERE d.email IS NOT NULL AND d.email <> 'not_found'
                    LIMIT %s
                """, (limit,))

            rows = cur.fetchall()
    return rows


# ──────────────────────────────────────────────
# Send email via Gmail SMTP
# ──────────────────────────────────────────────
def send_email(to_email, pdf_paths):
    msg = EmailMessage()
    msg["Subject"] = "Mobile app analysis services"
    msg["From"] = GMAIL_USER
    msg["To"] = to_email

    msg.set_content("Please find the attached analysis catalog of our service.")

    for path in pdf_paths:
        with open(path, "rb") as f:
            pdf_data = f.read()

        msg.add_attachment(
            pdf_data,
            maintype="application",
            subtype="pdf",
            filename=path.split("/")[-1]
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"[+] Sent to {to_email}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
IOS_PDF = "ios_static_capability_catalog.pdf"
ANDROID_PDF = "android_static_capability_catalog.pdf"

def main():
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise Exception("Missing email_user or email_password in config.json")

    rows = get_developer_apps(limit=10, country="tw")

    if not rows:
        print("[!] No emails found")
        return

    # Group stores by email so each developer gets one email
    grouped = defaultdict(set)
    for email, store in rows:
        grouped[email].add(store)

    print(f"[i] Sending to {len(grouped)} developers...")

    for email, stores in grouped.items():
        try:
            pdfs = []

            if "app_store" in stores:
                pdfs.append(IOS_PDF)

            if "google_play" in stores:
                pdfs.append(ANDROID_PDF)

            if not pdfs:
                print(f"[!] No valid store for {email}")
                continue

            send_email(email, pdfs)

        except Exception as e:
            print(f"[!] Failed for {email}: {e}")


if __name__ == "__main__":
    main()