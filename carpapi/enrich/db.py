"""Thin psycopg helpers for the enrichment CLI.

The CLI runs outside of Django, so this module re-implements the small
subset of read/write operations it needs against ``public.listings`` —
just enough to fetch a VIN, persist enrichment results, and roll up
status counts. No ORM dependency.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import psycopg
from psycopg.types.json import Jsonb

log = logging.getLogger(__name__)


@dataclass
class ListingRow:
    id: str
    vin: str
    make: str | None
    model: str | None
    year: int | None
    trim: str | None
    listing_url: str | None
    maker_specs: dict[str, Any] | None
    window_sticker: dict[str, Any] | None
    window_sticker_url: str | None
    maker_enrich_status: str | None
    price_amount: float | None


def dsn() -> str:
    return (
        f"host={os.environ.get('CARPAPI_DB_HOST', 'localhost')} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5433')} "
        f"dbname={os.environ.get('CARPAPI_DB_NAME', 'carpapi')} "
        f"user={os.environ.get('CARPAPI_DB_USER', 'carpapi')} "
        f"password={os.environ.get('CARPAPI_DB_PASSWORD', 'carpapi')}"
    )


@contextmanager
def connect() -> Iterator[psycopg.Connection]:
    with psycopg.connect(dsn()) as conn:
        yield conn


def get_by_vin(cur, vin: str) -> ListingRow | None:
    cur.execute(
        """
        SELECT id, vin, make, model, year, trim, listing_url,
               maker_specs, window_sticker, window_sticker_url,
               maker_enrich_status, price_amount
        FROM public.listings
        WHERE vin = %s
        LIMIT 1
        """,
        (vin,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return ListingRow(*row)


def find_pending(
    cur,
    *,
    make: str | None = None,
    limit: int = 100,
) -> list[ListingRow]:
    """Listings that need cold-loop enrichment.

    Skips rows already enriched and rows we've decided are unsupported
    or login-gated (sticky statuses).
    """
    sql = """
        SELECT id, vin, make, model, year, trim, listing_url,
               maker_specs, window_sticker, window_sticker_url,
               maker_enrich_status, price_amount
        FROM public.listings
        WHERE vin IS NOT NULL
          AND maker_specs IS NULL
          AND (maker_enrich_status IS NULL
               OR maker_enrich_status NOT IN ('unsupported','login_required'))
    """
    params: list[Any] = []
    if make:
        sql += " AND lower(make) = lower(%s)"
        params.append(make)
    sql += " ORDER BY scraped_at DESC NULLS LAST LIMIT %s"
    params.append(limit)
    cur.execute(sql, params)
    return [ListingRow(*r) for r in cur.fetchall()]


def save_enrichment(
    cur,
    listing_id: str,
    *,
    maker_url: str | None,
    maker_specs: dict | None,
    window_sticker_url: str | None,
    window_sticker: dict | None,
    status: str,
    error: str | None = None,
) -> None:
    cur.execute(
        """
        UPDATE public.listings
        SET maker_url           = COALESCE(%s, maker_url),
            maker_specs         = %s,
            window_sticker_url  = COALESCE(%s, window_sticker_url),
            window_sticker      = COALESCE(%s, window_sticker),
            maker_enriched_at   = CASE WHEN %s = 'enriched' THEN now()
                                       ELSE maker_enriched_at END,
            maker_enrich_status = %s,
            maker_enrich_error  = %s
        WHERE id = %s
        """,
        (
            maker_url,
            Jsonb(maker_specs) if maker_specs is not None else None,
            window_sticker_url,
            Jsonb(window_sticker) if window_sticker is not None else None,
            status,
            status,
            error,
            listing_id,
        ),
    )


def save_status_only(cur, listing_id: str, status: str, error: str | None = None) -> None:
    cur.execute(
        "UPDATE public.listings SET maker_enrich_status=%s, maker_enrich_error=%s WHERE id=%s",
        (status, error, listing_id),
    )


def save_sticker_only(
    cur,
    listing_id: str,
    *,
    window_sticker_url: str | None,
    window_sticker: dict | None,
) -> None:
    cur.execute(
        """
        UPDATE public.listings
        SET window_sticker_url = COALESCE(%s, window_sticker_url),
            window_sticker     = %s
        WHERE id = %s
        """,
        (
            window_sticker_url,
            Jsonb(window_sticker) if window_sticker is not None else None,
            listing_id,
        ),
    )


def status_summary(cur) -> dict[str, int]:
    cur.execute(
        """
        SELECT
          count(*)                                                         AS total,
          count(*) FILTER (WHERE maker_specs IS NOT NULL)                  AS enriched,
          count(*) FILTER (WHERE window_sticker IS NOT NULL)               AS sticker_parsed,
          count(*) FILTER (WHERE maker_enrich_status = 'unsupported')      AS unsupported,
          count(*) FILTER (WHERE maker_enrich_status = 'login_required')   AS login_gated,
          count(*) FILTER (WHERE maker_enrich_status = 'failed')           AS failed,
          count(*) FILTER (WHERE maker_specs IS NULL
                            AND maker_enrich_status IS NULL)               AS untouched
        FROM public.listings
        """
    )
    row = cur.fetchone()
    cols = ["total", "enriched", "sticker_parsed", "unsupported",
            "login_gated", "failed", "untouched"]
    return dict(zip(cols, row))


def per_make_coverage(cur, *, limit: int = 25) -> list[tuple]:
    cur.execute(
        """
        SELECT make,
               count(*)                                              AS total,
               count(*) FILTER (WHERE maker_specs IS NOT NULL)       AS enriched,
               count(*) FILTER (WHERE window_sticker IS NOT NULL)    AS with_sticker,
               count(*) FILTER (WHERE maker_enrich_status = 'unsupported') AS unsupported
        FROM public.listings
        WHERE make IS NOT NULL
        GROUP BY make
        ORDER BY total DESC
        LIMIT %s
        """,
        (limit,),
    )
    return cur.fetchall()
