from __future__ import annotations

import os
import time
import threading

from db.schema import create_tables
from db.crawl_tasks import reset_stuck_tasks
from db.scan_tasks import reset_stuck_scan_tasks

CRAWLER_TYPE    = os.environ.get("CRAWLER_TYPE")   # app_store | google_play | scanner
SCANNER_ENABLED = os.environ.get("SCANNER_ENABLED", "false").lower() in ("true", "1", "yes")
REGION          = os.environ.get("REGION", "default")
STARTUP_DELAY   = int(os.environ.get("STARTUP_DELAY", 45))


def main():
    create_tables()
    reset_stuck_tasks()
    reset_stuck_scan_tasks()

    if CRAWLER_TYPE == "scanner":
        from scanner.worker import worker as scanner_worker
        print(f"[CONTAINER] Starting Scanner worker", flush=True)
        scanner_worker()
        return

    if CRAWLER_TYPE in ("app_store", "google_play"):
        print(f"[CONTAINER] Waiting {STARTUP_DELAY}s for Tor to bootstrap...", flush=True)
        time.sleep(STARTUP_DELAY)

    if SCANNER_ENABLED:
        from scanner.worker import worker as scanner_worker
        print(f"[CONTAINER] Starting background Scanner worker (SCANNER_ENABLED=true)", flush=True)
        scanner_thread = threading.Thread(target=scanner_worker, name="scanner-worker", daemon=True)
        scanner_thread.start()

    if CRAWLER_TYPE == "app_store":
        from crawlers.apple_store import worker
        print(f"[CONTAINER] Starting App Store worker  region={REGION}", flush=True)
        worker()

    elif CRAWLER_TYPE == "google_play":
        from crawlers.google_play import worker
        print(f"[CONTAINER] Starting Google Play worker  region={REGION}", flush=True)
        worker()

    else:
        # ── Local debug mode — run both crawlers in-process ──────────────────
        from crawlers.apple_store import worker as as_worker
        from crawlers.google_play import worker as gp_worker

        print("[LOCAL] Running workers", flush=True)

        t1 = threading.Thread(target=as_worker, name="app-store",   daemon=True)
        t2 = threading.Thread(target=gp_worker, name="google-play", daemon=True)

        t1.start()
        t2.start()

        t1.join()
        t2.join()


if __name__ == "__main__":
    main()