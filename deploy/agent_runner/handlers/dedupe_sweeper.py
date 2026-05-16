"""dedupe-sweeper — count cross-source duplicate candidates in last 24h.

Real implementation would call `pipeline.carapi_pipeline.dedupe.build_dedupe_key`
and cluster into `public.listing_groups`. For now this handler does the
discovery pass (counts candidates by VIN + dedupe_key) and emits the
counts. The actual merging is gated behind a follow-up commit so the
first writes get reviewed by a human.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ._common import db_connect


def handle(event: dict, context: Any) -> dict:
    with db_connect() as conn, conn.cursor() as cur:
        # Candidates: VINs that appear in more than one source_id in
        # the last 24h. These would be merged into one listing_group
        # by build_dedupe_key — for now we just count them.
        cur.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT vin
                FROM public.listings
               WHERE vin IS NOT NULL
                 AND COALESCE(listing_updated_at, scraped_at)
                     > NOW() - INTERVAL '24 hours'
               GROUP BY vin
              HAVING COUNT(DISTINCT source_id) > 1
            ) t
            """
        )
        cross_source_vins = int(cur.fetchone()[0])

        cur.execute(
            "SELECT COUNT(*) FROM public.listing_groups"
        )
        existing_groups = int(cur.fetchone()[0])

    return {
        "ok": True,
        "agent": "dedupe-sweeper",
        "window": "24h",
        "cross_source_vin_candidates": cross_source_vins,
        "existing_listing_groups": existing_groups,
        "merges_executed": 0,
        "note": (
            "Discovery-only pass — merges are gated on a human review until "
            "the dedupe rules in context/deduplication-rules.md are signed off."
        ),
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
