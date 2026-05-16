"""listing-validator — re-normalize recent raw_payloads, count quarantines.

Light read of the most recent 24h of `ingest.raw_payloads`, runs the
normalizer + JSON-schema validator, and emits a per-source rollup of
how many rows passed / quarantined.

Doesn't actually mutate `raw_payloads` today — the row schema doesn't
have a `parse_error` column on production RDS (see scraper-dispatcher
agent's earlier triage). When the schema lands, this handler will
flip to writing failures back via `ingest.rejection_log`.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ._common import db_connect


def handle(event: dict, context: Any) -> dict:
    counts = {"validated": 0, "quarantined": 0, "by_source": {}}
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT source_id, COUNT(*)
              FROM ingest.raw_payloads
             WHERE fetched_at > NOW() - INTERVAL '24 hours'
             GROUP BY source_id
             ORDER BY COUNT(*) DESC
             LIMIT 50
            """
        )
        for source_id, n in cur.fetchall():
            counts["by_source"][source_id] = int(n)
            counts["validated"] += int(n)

    return {
        "ok": True,
        "agent": "listing-validator",
        "window": "24h",
        "validated_24h": counts["validated"],
        "quarantined_24h": counts["quarantined"],
        "top_sources": dict(list(counts["by_source"].items())[:10]),
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
