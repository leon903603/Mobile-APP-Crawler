from __future__ import annotations

from db.connection import get_connection


# ──────────────────────────────────────────────────────────────────────────────
# CHECK IF SCAN ALREADY COMPLETED (Deduplication)
# ──────────────────────────────────────────────────────────────────────────────

def is_scan_completed(app_db_id: int, version: str) -> bool:
    """
    Checks if a scan report for this app and version is already completed ('done').
    Allows crawlers to completely skip expensive APK download and analysis.
    """
    if not app_db_id:
        return False
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 1 FROM scan_reports
                WHERE app_db_id = %s AND version = %s AND status = 'done'
                LIMIT 1
            """, (app_db_id, version))
            return cur.fetchone() is not None


# ──────────────────────────────────────────────────────────────────────────────
# INSERT SCAN TASK
# ──────────────────────────────────────────────────────────────────────────────

def insert_scan_task(app_db_id: int, version: str, apk_path: str, priority: int = 0) -> int | None:
    """
    Inserts a new scan task for an app version with priority weighting.
    Returns the task id, or existing id if duplicate.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scan_reports (app_db_id, version, apk_path, status, priority)
                VALUES (%s, %s, %s, 'pending', %s)
                ON CONFLICT (app_db_id, version) DO UPDATE SET
                    apk_path   = EXCLUDED.apk_path,
                    priority   = GREATEST(EXCLUDED.priority, scan_reports.priority),
                    status     = CASE
                        WHEN scan_reports.status = 'dead' THEN 'pending'
                        ELSE scan_reports.status
                    END,
                    updated_at = NOW()
                RETURNING id
            """, (app_db_id, version, apk_path, priority))
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None


# ──────────────────────────────────────────────────────────────────────────────
# FETCH SCAN TASK (safe for concurrent workers with FOR UPDATE SKIP LOCKED)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_scan_task() -> tuple | None:
    """
    Atomically claims one pending scan task ordered by priority DESC, id ASC.
    Uses UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED) so multiple
    threads / containers never claim the same row.
    Returns (id, app_db_id, version, apk_path) or None.
    """
    with get_connection() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    UPDATE scan_reports
                    SET    status     = 'running',
                           locked_at  = NOW(),
                           updated_at = NOW()
                    WHERE  id = (
                        SELECT id
                        FROM   scan_reports
                        WHERE  status = 'pending'
                        ORDER  BY priority DESC, id ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT  1
                    )
                    RETURNING id, app_db_id, version, apk_path
                """)
                task = cur.fetchone()
                conn.commit()
                return task
            except Exception as e:
                conn.rollback()
                print(f"[SCAN QUEUE ERROR] fetch_scan_task: {e}")
                return None


# ──────────────────────────────────────────────────────────────────────────────
# MARK SCAN DONE
# ──────────────────────────────────────────────────────────────────────────────

def mark_scan_done(task_id: int, report_path: str, excerpt_path: str = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE scan_reports
                SET    status       = 'done',
                       report_path  = %s,
                       excerpt_path = %s,
                       updated_at   = NOW()
                WHERE  id = %s
            """, (report_path, excerpt_path, task_id))
            conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# MARK SCAN FAILED
# ──────────────────────────────────────────────────────────────────────────────

def mark_scan_failed(task_id: int, error: str = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE scan_reports
                SET    status     = CASE WHEN retries + 1 >= 3 THEN 'dead' ELSE 'pending' END,
                       retries    = retries + 1,
                       last_error = %s,
                       updated_at = NOW()
                WHERE  id = %s
            """, (error, task_id))
            conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# RESET STUCK SCAN TASKS
# ──────────────────────────────────────────────────────────────────────────────

def reset_stuck_scan_tasks(timeout_minutes: int = 60):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE scan_reports
                SET    status     = 'pending',
                       retries    = retries + 1,
                       updated_at = NOW()
                WHERE  status    = 'running'
                  AND  locked_at < NOW() - (INTERVAL '1 minute' * %s)
            """, (timeout_minutes,))
            conn.commit()
