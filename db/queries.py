from db.connection import get_connection


# ──────────────────────────────────────────────────────────────────────────────
# DEVELOPERS
# ──────────────────────────────────────────────────────────────────────────────

def insert_developer(name: str, email: str = None, website: str = None) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO developers (name, email, website)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    email   = COALESCE(EXCLUDED.email,   developers.email),
                    website = COALESCE(EXCLUDED.website, developers.website)
                RETURNING id
            """, (name, email, website))
            dev_id = cur.fetchone()[0]
            conn.commit()
    return dev_id


# ──────────────────────────────────────────────────────────────────────────────
# APPS
# ──────────────────────────────────────────────────────────────────────────────

def insert_app(
    developer_id: int,
    store: str,
    app_id: str,
    app_name: str,
    category: str,
    country: str = None,
) -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO apps (developer_id, store, app_id, app_name, category, country)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (store, app_id) DO UPDATE SET
                    app_name = EXCLUDED.app_name,
                    category = CASE
                        WHEN apps.category IS NULL OR apps.category = 'Unknown'
                        THEN EXCLUDED.category
                        ELSE apps.category
                    END,
                    country  = EXCLUDED.country
                RETURNING id
            """, (developer_id, store, app_id, app_name, category, country))
            row = cur.fetchone()[0]
            conn.commit()
    return row


# ──────────────────────────────────────────────────────────────────────────────
# APP VERSIONS
# ──────────────────────────────────────────────────────────────────────────────

def insert_app_version(app_db_id: int, version: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO app_versions (app_db_id, version)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (app_db_id, version))
            conn.commit()


# ──────────────────────────────────────────────────────────────────────────────
# QUERIES
# ──────────────────────────────────────────────────────────────────────────────

def get_developer_emails(limit: int = 10) -> list[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT email
                FROM   developers
                WHERE  email IS NOT NULL
                LIMIT  %s
            """, (limit,))
            return [row[0] for row in cur.fetchall()]