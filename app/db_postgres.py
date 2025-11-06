from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterable, Optional, Sequence

import psycopg
from psycopg.rows import dict_row


def _build_conninfo() -> str:
    dsn = os.getenv("PG_DSN")
    if dsn:
        return dsn

    parts = []
    mapping = {
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "dbname": "PGDATABASE",
        "host": "PGHOST",
        "port": "PGPORT",
    }
    for key, env in mapping.items():
        value = os.getenv(env)
        if value:
            parts.append(f"{key}={value}")

    return " ".join(parts)


@contextmanager
def get_conn():
    """
    Yield a psycopg3 connection using environment-configured credentials.
    Commits on success, rolls back on error, and always closes the connection.
    """
    conn = psycopg.connect(_build_conninfo(), row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def fetch_all(sql: str, params: Optional[Sequence[Any]] = None) -> list[dict[str, Any]]:
    params = params or ()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return rows


def fetch_one(sql: str, params: Optional[Sequence[Any]] = None) -> Optional[dict[str, Any]]:
    params = params or ()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return row


def execute(sql: str, params: Optional[Sequence[Any]] = None) -> int:
    params = params or ()
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def executemany(sql: str, param_list: Iterable[Sequence[Any]]) -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.executemany(sql, list(param_list))
