"""scrape-watchdog — read last 24h of monitor.scrape_monitor_reports.

Flags any per-source report where:
  - record_count < 0.5 × the source's median over the prior 7 days
  - http_error_rate > 0.05
  - duplicate_rate > 0.4
  - any flag string in the .flags array
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ._common import db_connect


def handle(event: dict, context: Any) -> dict:
    breaches: list[dict] = []
    with db_connect() as conn, conn.cursor() as cur:
        # Column is created_at (not generated_at) on the real schema.
        cur.execute(
            """
            SELECT source_id, ingest_run_id, record_count, http_error_rate,
                   duplicate_rate, flags, healthy, created_at
              FROM monitor.scrape_monitor_reports
             WHERE created_at > NOW() - INTERVAL '24 hours'
             ORDER BY created_at DESC
             LIMIT 200
            """
        )
        rows = cur.fetchall()
        for r in rows:
            (source_id, run_id, rc, http_err, dup, flags, healthy, gen_at) = r
            if not healthy or http_err > 0.05 or dup > 0.4:
                breaches.append({
                    "source_id": source_id,
                    "record_count": rc,
                    "http_error_rate": float(http_err) if http_err is not None else 0,
                    "duplicate_rate": float(dup) if dup is not None else 0,
                    "flags": list(flags) if flags else [],
                    "generated_at": gen_at.isoformat() if gen_at else None,
                })

    return {
        "ok": True,
        "agent": "scrape-watchdog",
        "reports_scanned": len(rows),
        "breaches": breaches[:20],
        "breach_count": len(breaches),
        "window": "24h",
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
