from __future__ import annotations

import os
from contextlib import contextmanager
from psycopg2 import pool

_pool: pool.ThreadedConnectionPool | None = None


def _get_pool() -> pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.ThreadedConnectionPool(
            minconn=2,
            maxconn=int(os.environ.get("DB_POOL_SIZE", 10)),
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", 5433)),
            dbname=os.environ.get("DB_NAME", "appcrawler"),
            user=os.environ.get("DB_USER", "crawler"),
            password=os.environ.get("DB_PASS", "crawlerpass"),
        )
    return _pool


@contextmanager
def get_connection():
    """
    Yields a psycopg2 connection from the thread-safe pool.
    Always use as:
        with get_connection() as conn:
            ...
    The connection is returned to the pool on exit (not closed).
    """
    p = _get_pool()
    conn = p.getconn()
    try:
        yield conn
    finally:
        p.putconn(conn)