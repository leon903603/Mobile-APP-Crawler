from __future__ import annotations

from psycopg2.extras import execute_values

from db.connection import get_connection


# ──────────────────────────────────────────────────────────────────────────────
# SINGLE INSERT
# ──────────────────────────────────────────────────────────────────────────────

def add_task(source: str, country: str, task_type: str, payload: str, region: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO crawl_tasks (source, country, task_type, payload, region)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (source, country, task_type, payload, region))
            conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# BULK INSERT  (used by seed_tasks.py)
# ──────────────────────────────────────────────────────────────────────────────

def add_tasks_bulk(tasks: list[tuple]) -> int:
    """
    tasks = [(source, country, task_type, payload, region), ...]
    Returns the number of rows passed in (duplicates are silently skipped).
    """
    if not tasks:
        return 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            execute_values(cur, """
                INSERT INTO crawl_tasks (source, country, task_type, payload, region)
                VALUES %s
                ON CONFLICT DO NOTHING
            """, tasks)
            conn.commit()

    return len(tasks)


# ──────────────────────────────────────────────────────────────────────────────
# FETCH TASK  (region-aware, safe for concurrent workers)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_task(region: str, source: str) -> tuple | None:
    """
    Atomically claims one pending task for the given region and source store.
    Uses UPDATE … WHERE id = (SELECT … FOR UPDATE SKIP LOCKED) so multiple
    threads / containers never claim the same row.
    Returns (id, source, country, task_type, payload, region) or None.
    """
    with get_connection() as conn:
        conn.autocommit = False
        with conn.cursor() as cur:
            try:
                cur.execute("""
                    UPDATE crawl_tasks
                    SET    status    = 'running',
                           locked_at = NOW(),
                           updated_at = NOW()
                    WHERE  id = (
                        SELECT id
                        FROM   crawl_tasks
                        WHERE  status = 'pending'
                          AND  region = %s
                          AND  source = %s
                        ORDER  BY id
                        FOR UPDATE SKIP LOCKED
                        LIMIT  1
                    )
                    RETURNING id, source, country, task_type, payload, region
                """, (region, source))
                task = cur.fetchone()
                conn.commit()
                return task
            except Exception as e:
                conn.rollback()
                print(f"[QUEUE ERROR] fetch_task: {e}")
                return None


# ──────────────────────────────────────────────────────────────────────────────
# MARK DONE
# ──────────────────────────────────────────────────────────────────────────────

def mark_done(task_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE crawl_tasks
                SET    status     = 'done',
                       updated_at = NOW()
                WHERE  id = %s
            """, (task_id,))
            conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# MARK FAILED  (auto-retry up to 3 attempts, then 'dead')
# ──────────────────────────────────────────────────────────────────────────────

def mark_failed(task_id: int, error: str = None):
    """
    Increments retries.  If retries < 3 the task goes back to 'pending'
    so another worker can retry it.  After 3 failures it becomes 'dead'.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE crawl_tasks
                SET    status     = CASE WHEN retries + 1 >= 3 THEN 'dead' ELSE 'pending' END,
                       retries    = retries + 1,
                       last_error = %s,
                       updated_at = NOW()
                WHERE  id = %s
            """, (error, task_id))
            conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# RESET STUCK TASKS  (run periodically via cron / scheduler)
# ──────────────────────────────────────────────────────────────────────────────

def reset_stuck_tasks(timeout_minutes: int = 30):
    """
    Tasks that have been 'running' longer than timeout_minutes are assumed
    to belong to a dead worker and are reset to 'pending'.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE crawl_tasks
                SET    status     = 'pending',
                       retries    = retries + 1,
                       updated_at = NOW()
                WHERE  status    = 'running'
                  AND  locked_at < NOW() - (INTERVAL '1 minute' * %s)
            """, (timeout_minutes,))
            conn.commit()