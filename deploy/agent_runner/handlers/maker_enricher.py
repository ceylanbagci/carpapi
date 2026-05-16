"""maker-enricher — count listings missing maker_specs, plan next batch.

The real implementation uses `carpapi.enrich.orchestrator` to hit
each maker's site for JSON-LD specs. Today this handler reports the
backlog and identifies the next 50 VINs by make so the operator can
see what's pending — the actual enrichment loop is gated until we
have the Selenium-extended image (some maker sites need JS rendering).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ._common import db_connect


def handle(event: dict, context: Any) -> dict:
    by_make: dict[str, int] = {}
    total_missing = 0
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT make, COUNT(*)
              FROM public.listings
             WHERE maker_specs IS NULL
               AND make IS NOT NULL
             GROUP BY make
             ORDER BY COUNT(*) DESC
             LIMIT 15
            """
        )
        for make, n in cur.fetchall():
            by_make[make] = int(n)
            total_missing += int(n)

    return {
        "ok": True,
        "agent": "maker-enricher",
        "total_missing_24h_window": None,
        "total_missing_alltime": total_missing,
        "top_makes": by_make,
        "enriched_this_run": 0,
        "note": (
            "Discovery-only — actual enrichment runs from local "
            "`python -m carpapi.enrich.orchestrator` until the Selenium-extended "
            "agent image lands."
        ),
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
