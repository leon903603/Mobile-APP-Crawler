from __future__ import annotations

from db.connection import get_connection


# ──────────────────────────────────────────────────────────────────────────────
# INSERT SCAN TASK
# ──────────────────────────────────────────────────────────────────────────────

def insert_scan_task(app_db_id: int, version: str, apk_path: str) -> int | None:
    """
    Inserts a new scan task for an app version.
    Returns the task id, or existing id if duplicate.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO scan_reports (app_db_id, version, apk_path, status)
                VALUES (%s, %s, %s, 'pending')
                ON CONFLICT (app_db_id, version) DO UPDATE SET
                    apk_path = EXCLUDED.apk_path,
                    status   = CASE
                        WHEN scan_reports.status = 'dead' THEN 'pending'
                        ELSE scan_reports.status
                    END,
                    updated_at = NOW()
                RETURNING id
            """, (app_db_id, version, apk_path))
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None


# ──────────────────────────────────────────────────────────────────────────────
# FETCH SCAN TASK (safe for concurrent workers with FOR UPDATE SKIP LOCKED)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_scan_task() -> tuple | None:
    """
    Atomically claims one pending scan task.
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
                        ORDER  BY id
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

def mark_scan_done(task_id: int, report_path: str, excerpt_path: str):
    """
    Marks the scan task as 'done' and saves the report and excerpt file paths.
    """
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
# MARK SCAN FAILED (auto-retry up to 3 attempts, then 'dead')
# ──────────────────────────────────────────────────────────────────────────────

def mark_scan_failed(task_id: int, error: str = None):
    """
    Increments retries. If retries < 3 the task goes back to 'pending'
    so another worker can retry it. After 3 failures it becomes 'dead'.
    """
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
# RESET STUCK SCAN TASKS (run periodically / at container startup)
# ──────────────────────────────────────────────────────────────────────────────

def reset_stuck_scan_tasks(timeout_minutes: int = 30):
    """
    Scan tasks that have been 'running' longer than timeout_minutes are assumed
    to belong to a dead worker and are reset to 'pending'.
    """
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