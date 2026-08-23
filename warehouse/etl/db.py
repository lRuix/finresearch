"""PostgreSQL connection helpers."""
from __future__ import annotations

from contextlib import contextmanager

import psycopg


@contextmanager
def connect(dsn: str):
    with psycopg.connect(dsn) as conn:
        yield conn


def execute_sql(dsn: str, sql: str) -> None:
    with connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
