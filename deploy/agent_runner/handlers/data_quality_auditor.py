"""data-quality-auditor — weekly DB-quality rollup.

Interactive in spirit (a human reviews the resulting markdown), but
worth running on a daily Lambda cadence anyway: the scheduled fire
keeps the dashboard state fresh + emits the same numbers via the
state file so the operator can spot trends without manually running
the script.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ._common import db_connect


def handle(event: dict, context: Any) -> dict:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*) AS total,
              COUNT(*) FILTER (WHERE vin IS NULL)                            AS null_vin,
              COUNT(*) FILTER (WHERE price_amount IS NULL OR price_amount<=0) AS null_price,
              COUNT(*) FILTER (WHERE image_url IS NULL)                       AS null_image,
              COUNT(*) FILTER (WHERE scraped_at < NOW() - INTERVAL '14 days') AS stale
            FROM public.listings
            """
        )
        total, null_vin, null_price, null_image, stale = cur.fetchone()
        cur.execute(
            """
            SELECT COUNT(*),
                   COUNT(*) FILTER (WHERE last_scraped_at IS NULL),
                   COUNT(*) FILTER (WHERE cms IS NULL)
              FROM public.dealers WHERE status='active'
            """
        )
        d_total, d_never_scraped, d_no_cms = cur.fetchone()

    return {
        "ok": True,
        "agent": "data-quality-auditor",
        "listings": {
            "total": int(total),
            "null_vin_pct": round(100 * null_vin / max(total, 1), 2),
            "null_price_pct": round(100 * null_price / max(total, 1), 2),
            "null_image_pct": round(100 * null_image / max(total, 1), 2),
            "stale_14d_pct": round(100 * stale / max(total, 1), 2),
        },
        "active_dealers": {
            "total": int(d_total),
            "never_scraped": int(d_never_scraped),
            "no_cms_classified": int(d_no_cms),
        },
        "verdict": (
            "RED" if (null_price > total * 0.10 or null_image > total * 0.95)
            else "AMBER" if d_never_scraped > d_total * 0.30
            else "GREEN"
        ),
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
