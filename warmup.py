"""
Warmup Script: Dedicated Seed/Internal Domain Warmup for mail.solitesterror.com
"""

from __future__ import annotations

import os
import sys
import time
import argparse
from datetime import datetime

import config  # Loads .env automatically
from email_pipeline.sender import dispatch_outreach_email
from email_pipeline.guard import get_random_throttle_delay
from email_pipeline.payload import DEFAULT_FROM_EMAIL, DEFAULT_REPLY_TO

WARMUP_SUBJECT = "APP平台組寄信測試"

WARMUP_TEXT = """同學 您好，

我是實驗室內的APP平台組，此信為了讓寄信網域成為被驗證網域而發，希望您幫忙回復一個"收到"即可，謝謝。

祝 學業順利！"""

WARMUP_HTML = """<p>同學 您好，</p>
<p>我是實驗室內的APP平台組，此信為了讓寄信網域成為被驗證網域而發，希望您幫忙回復一個"收到"即可，謝謝。</p>
<br>
<p>祝 學業順利！</p>"""


def build_warmup_payload(to_email: str) -> dict:
    return {
        "from": DEFAULT_FROM_EMAIL,
        "reply_to": DEFAULT_REPLY_TO,
        "to": [to_email],
        "subject": WARMUP_SUBJECT,
        "html": WARMUP_HTML,
        "text": WARMUP_TEXT,
    }


def main():
    parser = argparse.ArgumentParser(description="Send internal domain warmup emails to labmates/seed addresses")
    parser.add_argument(
        "--to",
        nargs="+",
        required=True,
        help="One or more recipient email addresses (e.g. --to a@gmail.com b@nycu.edu.tw)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate sending without contacting Resend API"
    )
    parser.add_argument(
        "--skip-delay",
        action="store_true",
        help="Skip sleep delay between multiple recipients"
    )
    args = parser.parse_args()

    api_key = os.environ.get("RESEND_API_KEY")
    if not args.dry_run and not api_key:
        print("[!] Error: RESEND_API_KEY environment variable is required.")
        print("    Please set it in .env or run with --dry-run.")
        sys.exit(1)

    print(f"\n[i] Starting warmup batch to {len(args.to)} recipient(s) at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"    From: {DEFAULT_FROM_EMAIL}")
    print(f"    Subject: {WARMUP_SUBJECT}\n")

    for idx, email in enumerate(args.to, start=1):
        payload = build_warmup_payload(email)
        print(f"[{idx}/{len(args.to)}] Sending to: {email}...")

        try:
            res = dispatch_outreach_email(email_payload=payload, dry_run=args.dry_run, api_key=api_key)
            if res.get("ok"):
                mode_str = "[DRY-RUN]" if args.dry_run else "[LIVE]"
                print(f"  {mode_str} [+] Sent successfully! (Msg ID: {res.get('id')})")
            else:
                print(f"  [!] Failed: {res.get('error')}")
        except Exception as e:
            print(f"  [!] Error: {e}")

        if idx < len(args.to):
            if args.skip_delay:
                print("  [i] Skipping delay...")
            else:
                delay = get_random_throttle_delay(180, 420)
                print(f"  [i] Sleeping for {delay}s ({delay // 60}m {delay % 60}s) to simulate human sending...")
                time.sleep(delay)

    print(f"\n[✓] Warmup batch finished.\n")


if __name__ == "__main__":
    main()

