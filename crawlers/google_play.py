import json
import os
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from google_play_scraper import app as gplay_app, search

from db.queries import insert_developer, insert_app, insert_app_version
from db.crawl_tasks import fetch_task, mark_done, mark_failed

from crawlers.search_terms import get_country_lang

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG  (all tunable via env vars — no redeploy needed)
# ──────────────────────────────────────────────────────────────────────────────

STORE        = "google_play"
REGION       = os.environ.get("REGION", "default")
WORKER_COUNT  = int(os.environ.get("WORKER_COUNT", 4))
FETCH_WORKERS = int(os.environ.get("FETCH_WORKERS", 24))

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

def _insert_app(app_info: dict, country: str):
    try:
        dev_name = app_info.get("developer")
        if not dev_name:
            return

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

    except Exception as e:
        print(f"[DB ERROR] {app_info.get('appId')}: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# PARALLEL FETCH + INSERT
# ──────────────────────────────────────────────────────────────────────────────

def _bulk_fetch_and_insert(app_ids: list[str], country: str) -> None:
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
        futures = {ex.submit(_fetch_app, aid, country): aid for aid in app_ids}
        total = len(futures)
        for done, f in enumerate(as_completed(futures), 1):
            if app_info := f.result():
                _insert_app(app_info, country)
                print(f"[GP] {country} {done}/{total} {app_info.get('appId')}", flush=True)


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


# ──────────────────────────────────────────────────────────────────────────────
# download_apk(prototype, can be revised)
# ──────────────────────────────────────────────────────────────────────────────
def _fetch_app(app_id: str, country: str) -> dict | None:
    # 1. 抓 metadata
    app_info = gplay_app(app_id, lang="en", country=country)
    
    # 2. 寫入 DB
    app_db_id = _insert_app(app_info, country)
    
    # 3. 下載 APK ← 在這裡！
    version = app_info.get("version")
    apk_path = _download_apk(app_id, version)
    
    # 4. 新增 scan_reports 任務（告訴 Scanner 有 APK 可以檢測了）
    insert_scan_task(
        app_db_id=app_db_id,
        version=version,
        apk_path=apk_path  # ← 告訴 Scanner APK 在哪裡
    )