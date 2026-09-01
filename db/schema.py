from __future__ import annotations

from db.connection import get_connection


def create_tables():
    with get_connection() as conn:
        with conn.cursor() as cur:

            # Advisory lock — only one container runs CREATE TABLE at a time.
            # Others wait, then skip because of IF NOT EXISTS.
            cur.execute("SELECT pg_advisory_lock(1)")

            try:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS developers (
                        id         SERIAL PRIMARY KEY,
                        name       TEXT NOT NULL,
                        email      TEXT,
                        website    TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (name)
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS apps (
                        id           SERIAL PRIMARY KEY,
                        developer_id INTEGER REFERENCES developers(id),
                        store        TEXT NOT NULL,
                        app_id       TEXT NOT NULL,
                        app_name     TEXT NOT NULL,
                        category     TEXT,
                        country      TEXT,
                        created_at   TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (store, app_id)
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS app_versions (
                        id         SERIAL PRIMARY KEY,
                        app_db_id  INTEGER REFERENCES apps(id),
                        version    TEXT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (app_db_id, version)
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS crawl_tasks (
                        id         SERIAL PRIMARY KEY,
                        source     TEXT        NOT NULL,           -- app_store / google_play
                        country    TEXT        NOT NULL,
                        task_type  TEXT        NOT NULL,           -- category / keyword / language
                        payload    TEXT,                           -- category_id / keyword / lang::term
                        region     TEXT        NOT NULL DEFAULT 'default',
                        status     TEXT        NOT NULL DEFAULT 'pending',  -- pending / running / done / dead
                        retries    INTEGER     NOT NULL DEFAULT 0,
                        last_error TEXT,
                        locked_at  TIMESTAMPTZ,
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (source, country, task_type, payload)
                    )
                """)

                # Migrate existing tables that predate the region/retries columns.
                # ADD COLUMN IF NOT EXISTS is a no-op when the column already exists,
                # so this is safe to run on every startup.
                cur.execute("""
                    ALTER TABLE crawl_tasks
                        ADD COLUMN IF NOT EXISTS region     TEXT        NOT NULL DEFAULT 'default',
                        ADD COLUMN IF NOT EXISTS retries    INTEGER     NOT NULL DEFAULT 0,
                        ADD COLUMN IF NOT EXISTS last_error TEXT,
                        ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()
                """)

                # Partial index — only covers pending rows, stays small as tasks are consumed
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_crawl_tasks_queue
                        ON crawl_tasks (source, region, status, id)
                        WHERE status = 'pending'
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scan_reports (
                        id           SERIAL PRIMARY KEY,
                        app_db_id    INTEGER REFERENCES apps(id),
                        version      TEXT,
                        apk_path     TEXT,
                        report_path  TEXT,
                        excerpt_path TEXT,
                        status       TEXT        NOT NULL DEFAULT 'pending',  -- pending / running / done / dead
                        retries      INTEGER     NOT NULL DEFAULT 0,
                        last_error   TEXT,
                        locked_at    TIMESTAMPTZ,
                        updated_at   TIMESTAMPTZ DEFAULT NOW(),
                        created_at   TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (app_db_id, version)
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS email_log (
                        id             SERIAL PRIMARY KEY,
                        developer_id   INTEGER REFERENCES developers(id),
                        email          TEXT NOT NULL,
                        scan_report_id INTEGER REFERENCES scan_reports(id),
                        status         TEXT NOT NULL DEFAULT 'sent',  -- sent / failed / dry_run
                        error          TEXT,
                        sent_at        TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE (email, scan_report_id)
                    )
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_scan_reports_queue
                        ON scan_reports (status, id)
                        WHERE status = 'pending'
                """)

                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_email_log_lookup
                        ON email_log (email, scan_report_id, status)
                """)

                conn.commit()

            finally:
                cur.execute("SELECT pg_advisory_unlock(1)")