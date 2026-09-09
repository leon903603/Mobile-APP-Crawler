from __future__ import annotations

import json
import os
import time
import random
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from google_play_scraper import app as gplay_app, search

from db.queries import insert_developer, insert_app, insert_app_version
from db.crawl_tasks import fetch_task, mark_done, mark_failed
from db.scan_tasks import insert_scan_task

from crawlers.search_terms import get_country_lang

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG  (all tunable via env vars — no redeploy needed)
# ──────────────────────────────────────────────────────────────────────────────

STORE        = "google_play"
REGION       = os.environ.get("REGION", "default")
WORKER_COUNT  = int(os.environ.get("WORKER_COUNT", 4))
FETCH_WORKERS = int(os.environ.get("FETCH_WORKERS", 24))
APK_DIR       = os.environ.get("APK_DIR", "downloads/apks")

WAIT_TASK = (0.1, 0.3)

N_HITS = 30

with open("listings/google-play-apps-categories.json") as _f:
    _CATEGORY_DESC: dict[str, str] = {
        c["category"]: c.get("category_description", c["category"])
        for c in json.load(_f)
    }

# ──────────────────────────────────────────────────────────────────────────────

def _sleep(range_: tuple[float, float] = WAIT_TASK):
    time.sleep(random.uniform(*range_))


# ──────────────────────────────────────────────────────────────────────────────
# API WRAPPERS  (retry on 429, per-thread session)
# ──────────────────────────────────────────────────────────────────────────────

def _backoff(msg: str) -> float:
    if "429" in msg or "too many" in msg:
        return 15 + random.random() * 10   # rate-limited — give Google time to ease off
    return 2 + random.random() * 3         # transient proxy/network error — retry quickly


def _is_retryable(msg: str) -> bool:
    return any(k in msg for k in ("429", "too many", "503", "tunnel", "forwarding", "connection", "incompleteread"))


def _search_by_term(term: str, country: str, lang: str = "en") -> list[dict]:
    for attempt in range(5):
        try:
            _sleep()
            return search(
                term,
                lang=lang,
                country=country,
                n_hits=N_HITS,
            )
        except Exception as e:
            msg = str(e).lower()
            if _is_retryable(msg) and attempt < 4:
                time.sleep(_backoff(msg))
                continue
            print(f"[WARN] search '{term}' ({country}/{lang}): {e}")
            return []
    return []


def _fetch_app(app_id: str, country: str) -> dict | None:
    for attempt in range(5):
        try:
            _sleep()
            return gplay_app(app_id, lang="en", country=country)
        except Exception as e:
            msg = str(e).lower()
            if _is_retryable(msg) and attempt < 4:
                time.sleep(_backoff(msg))
                continue
            print(f"[WARN] fetch app {app_id} ({country}): {e}")
            return None
    return None


# ──────────────────────────────────────────────────────────────────────────────
# DB INSERT
# ──────────────────────────────────────────────────────────────────────────────

def _insert_app(app_info: dict, country: str) -> int | None:
    try:
        dev_name = app_info.get("developer")
        if not dev_name:
            return None

        dev_id = insert_developer(
            name=dev_name,
            email=app_info.get("developerEmail"),
            website=app_info.get("developerWebsite"),
        )
        app_db_id = insert_app(
            developer_id=dev_id,
            store=STORE,
            app_id=app_info.get("appId"),
            app_name=app_info.get("title"),
            category=app_info.get("genre") or "Unknown",
            country=country,
        )
        if version := app_info.get("version"):
            insert_app_version(app_db_id, version)

        return app_db_id

    except Exception as e:
        print(f"[DB ERROR] {app_info.get('appId')}: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# DOWNLOAD APK (using apkeep)
# ──────────────────────────────────────────────────────────────────────────────

def _download_apk(app_id: str, version: str = None) -> str | None:
    """
    Downloads APK using apkeep.
    Supports APKPure (no login) and optional Google Play credentials.
    Automatically handles split .xapk archives by extracting the core APK.
    """
    os.makedirs(APK_DIR, exist_ok=True)
    apk_file = os.path.join(APK_DIR, f"{app_id}.apk")

    if os.path.exists(apk_file):
        return apk_file

    cmd = ["apkeep", "-a", app_id]

    gp_email = os.environ.get("GOOGLE_PLAY_EMAIL")
    gp_auth = os.environ.get("GOOGLE_PLAY_AUTH_TOKEN") or os.environ.get("GOOGLE_PLAY_AAS_TOKEN")
    if gp_email and gp_auth:
        cmd.extend(["-d", "google-play", "-e", gp_email, "--auth-token", gp_auth])
    else:
        cmd.extend(["-d", "apk-pure"])

    cmd.append(APK_DIR)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            if os.path.exists(apk_file):
                return apk_file
            # Check for downloaded files with matching prefix (including .xapk/.apks)
            if os.path.exists(APK_DIR):
                for f in os.listdir(APK_DIR):
                    fpath = os.path.join(APK_DIR, f)
                    if f.startswith(app_id) and f.endswith(".apk"):
                        return fpath
                    elif f.startswith(app_id) and (f.endswith(".xapk") or f.endswith(".apks") or f.endswith(".zip")):
                        import zipfile
                        with zipfile.ZipFile(fpath, "r") as zf:
                            for member in zf.namelist():
                                if member.endswith(".apk") and not member.startswith("config."):
                                    zf.extract(member, APK_DIR)
                                    extracted = os.path.join(APK_DIR, member)
                                    return extracted
            return apk_file
        else:
            print(f"[WARN] apkeep failed for {app_id}: {result.stderr.strip()}")
            return None
    except FileNotFoundError:
        print(f"[WARN] apkeep binary not found. Skipping APK download for {app_id}")
        return None
    except Exception as e:
        print(f"[WARN] Failed to download APK for {app_id}: {e}")
        return None


# ──────────────────────────────────────────────────────────────────────────────
# PARALLEL FETCH + INSERT + DOWNLOAD + SCAN TASK
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_and_process_app(app_id: str, country: str) -> None:
    app_info = _fetch_app(app_id, country)
    if not app_info:
        return

    app_db_id = _insert_app(app_info, country)
    if not app_db_id:
        return

    version = app_info.get("version") or "unknown"
    apk_path = _download_apk(app_id, version)

    if apk_path:
        insert_scan_task(
            app_db_id=app_db_id,
            version=version,
            apk_path=apk_path
        )


def _bulk_fetch_and_insert(app_ids: list[str], country: str) -> None:
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
        futures = {ex.submit(_fetch_and_process_app, aid, country): aid for aid in app_ids}
        total = len(futures)
        for done, f in enumerate(as_completed(futures), 1):
            try:
                f.result()
                print(f"[GP] {country} {done}/{total} {futures[f]}", flush=True)
            except Exception as e:
                print(f"[GP ERROR] {futures[f]}: {e}", flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# TASK PROCESSORS
# ──────────────────────────────────────────────────────────────────────────────

def process_category(country: str, category_id: str):
    desc = _CATEGORY_DESC.get(category_id, category_id)
    term = desc.lower().replace(" apps", "").replace(" games", "").strip()
    print(f"[GP] searching {country} | {term}", flush=True)

    langs = ["en"]
    local_lang = get_country_lang(country)
    if local_lang != "en":
        langs.append(local_lang)

    all_ids: set[str] = set()
    for lang in langs:
        for r in _search_by_term(term, country, lang):
            if aid := r.get("appId"):
                all_ids.add(aid)

    if all_ids:
        _bulk_fetch_and_insert(list(all_ids), country)


def process_keyword(country: str, keyword: str):
    print(f"[GP] searching {country} | {keyword}", flush=True)
    app_ids = [r["appId"] for r in _search_by_term(keyword, country, "en") if r.get("appId")]
    if app_ids:
        _bulk_fetch_and_insert(app_ids, country)


def process_language(country: str, lang: str, term: str):
    app_ids = [r["appId"] for r in _search_by_term(term, country, lang) if r.get("appId")]
    if app_ids:
        _bulk_fetch_and_insert(app_ids, country)


# ──────────────────────────────────────────────────────────────────────────────
# SINGLE WORKER LOOP
# ──────────────────────────────────────────────────────────────────────────────

def _worker(worker_id: int):
    print(f"[GP WORKER-{worker_id}] started  region={REGION}", flush=True)

    while True:
        task = fetch_task(REGION, STORE)

        if not task:
            time.sleep(0.5)
            continue

        task_id, _, country, task_type, payload, _ = task

        try:
            if task_type == "category":
                process_category(country, payload)

            elif task_type == "keyword":
                process_keyword(country, payload)

            elif task_type == "language":
                lang, term = payload.split("::", 1)
                process_language(country, lang, term)

            else:
                print(f"[GP WORKER-{worker_id}] unknown task_type '{task_type}', skipping")

            mark_done(task_id)
            print(f"[GP WORKER-{worker_id}][DONE] {country} | {task_type} | {payload}", flush=True)

        except Exception as e:
            print(f"[GP WORKER-{worker_id}][ERROR] task {task_id}: {e}", flush=True)
            mark_failed(task_id, error=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# ENTRYPOINT  (called from main.py)
# ──────────────────────────────────────────────────────────────────────────────

def worker():
    """Spawns WORKER_COUNT threads, each running an independent worker loop."""
    threads = [
        threading.Thread(target=_worker, args=(i,), daemon=True)
        for i in range(WORKER_COUNT)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()