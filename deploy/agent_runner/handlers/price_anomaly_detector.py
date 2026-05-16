"""price-anomaly-detector — flag listings with price ratio > 1.5 or < 0.5.

Joins `listings` (current price) with `listing_price_history` (prior
prices) and finds rows whose latest delta is suspiciously large. Most
matches are scraper regressions (price column drift); a few are real
flash deals.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ._common import db_connect


def handle(event: dict, context: Any) -> dict:
    anomalies: list[dict] = []
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH latest AS (
              SELECT DISTINCT ON (listing_id)
                     listing_id, price_amount AS prev_price, observed_at
                FROM public.listing_price_history
               WHERE observed_at > NOW() - INTERVAL '14 days'
               ORDER BY listing_id, observed_at DESC
            )
            SELECT l.id::text, l.year, l.make, l.model,
                   l.price_amount, latest.prev_price,
                   l.price_amount::numeric / NULLIF(latest.prev_price, 0) AS ratio
              FROM public.listings l
              JOIN latest ON latest.listing_id = l.id
             WHERE l.price_amount IS NOT NULL
               AND latest.prev_price IS NOT NULL
               AND latest.prev_price > 0
               AND (
                 l.price_amount::numeric / latest.prev_price > 1.5
                 OR l.price_amount::numeric / latest.prev_price < 0.5
               )
             LIMIT 50
            """
        )
        for row in cur.fetchall():
            lid, year, make, model, price, prev, ratio = row
            anomalies.append({
                "id": lid,
                "label": f"{year or '?'} {make or '?'} {model or '?'}".strip(),
                "price": float(price) if price else None,
                "prev_price": float(prev) if prev else None,
                "ratio": round(float(ratio), 3),
                "kind": "spike" if ratio > 1.5 else "crash",
            })

    return {
        "ok": True,
        "agent": "price-anomaly-detector",
        "window": "14d",
        "anomalies": anomalies,
        "anomaly_count": len(anomalies),
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
