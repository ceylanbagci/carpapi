"""rds-steward — daily RDS health check.

Queries `pg_stat_database` + `pg_stat_activity` for free-space-ish
signals (we can't see free disk directly without RDS API, but we can
see connections + slow queries via `pg_stat_statements`).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ._common import db_connect


def handle(event: dict, context: Any) -> dict:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT setting::int FROM pg_settings WHERE name='max_connections'
            """
        )
        max_conns = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT COUNT(*) FROM pg_stat_activity
             WHERE datname = current_database()
               AND state <> 'idle'
            """
        )
        active_conns = int(cur.fetchone()[0])

        cur.execute(
            "SELECT pg_database_size(current_database())"
        )
        db_size_bytes = int(cur.fetchone()[0])

        # Top slow queries via pg_stat_statements (we installed it earlier).
        try:
            cur.execute(
                """
                SELECT calls, total_exec_time::int, mean_exec_time::int,
                       LEFT(query, 80)
                  FROM pg_stat_statements
                 ORDER BY mean_exec_time DESC
                 LIMIT 5
                """
            )
            slow = [
                {"calls": c, "total_ms": t, "mean_ms": m, "query_head": q}
                for (c, t, m, q) in cur.fetchall()
            ]
        except Exception:  # noqa: BLE001
            slow = []

    return {
        "ok": True,
        "agent": "rds-steward",
        "max_connections": max_conns,
        "active_connections": active_conns,
        "conn_pct": round(100 * active_conns / max_conns, 2),
        "db_size_bytes": db_size_bytes,
        "db_size_mb": round(db_size_bytes / 1024 / 1024, 1),
        "slow_queries": slow,
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
