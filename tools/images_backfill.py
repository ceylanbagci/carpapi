"""Backfill `listings.image_url` by re-fetching dealer pages.

Usage:
    # default: pick up to 10 listings with no image yet
    source data/secrets/rds.env
    python tools/images_backfill.py

    # bigger batch + custom rate limit
    python tools/images_backfill.py --limit 200 --sleep 2

    # force re-process one specific listing (by id or vin)
    python tools/images_backfill.py --listing-id <uuid>
    python tools/images_backfill.py --vin 4T1C11AK3MU527833

Per `context/scraper-rules.md` and `skills/rds-first-skill.md`:
  - Source `data/secrets/rds.env` first (writes go to RDS).
  - Honor robots.txt — this script uses an identifying User-Agent and
    serializes requests with a configurable sleep.
  - Don't run a 4,391-row backfill in one go without splitting by
    `source_id` and rate-limiting per host.

Reads `car_url` (preferred — the VDP) or `listing_url` (fallback) for
each listing, runs the carpapi.images pipeline, and writes the
resulting S3/CloudFront URL back to `image_url` + `image_svg_url`.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import Iterable, Optional

# Allow `python tools/images_backfill.py` from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg

from carpapi.images.extractor import fetch_listing_html, first_image_url
from carpapi.images.processor import process_for_listing

log = logging.getLogger("carpapi.images.backfill")


def _dsn() -> str:
    return (
        f"host={os.environ.get('CARPAPI_DB_HOST', 'localhost')} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5433')} "
        f"dbname={os.environ.get('CARPAPI_DB_NAME', 'carpapi')} "
        f"user={os.environ.get('CARPAPI_DB_USER', 'carpapi')} "
        f"password={os.environ.get('CARPAPI_DB_PASSWORD', 'carpapi')}"
    )


def _pick_rows(
    conn,
    *,
    limit: int,
    listing_id: Optional[str],
    vin: Optional[str],
    reprocess_existing: bool = False,
):
    with conn.cursor() as cur:
        if listing_id:
            cur.execute(
                """
                SELECT id::text, vin, COALESCE(car_url, listing_url), make, model, year
                FROM public.listings
                WHERE id::text = %s
                """,
                (listing_id,),
            )
        elif vin:
            cur.execute(
                """
                SELECT id::text, vin, COALESCE(car_url, listing_url), make, model, year
                FROM public.listings
                WHERE vin = %s
                """,
                (vin.upper(),),
            )
        else:
            # Pick rows with a *real* VDP URL — not the dealer's
            # inventory landing page. The Filters.where_clause uses
            # the same pair of conditions.
            #
            # Default mode targets unpopulated rows (`image_url IS NULL`).
            # `--reprocess-existing` flips that to NOT NULL — used to
            # overwrite thumbnails that came from a buggy extractor.
            image_filter = (
                "image_url IS NOT NULL" if reprocess_existing else "image_url IS NULL"
            )
            cur.execute(
                f"""
                SELECT id::text, vin, COALESCE(car_url, listing_url), make, model, year
                FROM public.listings
                WHERE {image_filter}
                  AND COALESCE(car_url, listing_url) IS NOT NULL
                  AND COALESCE(car_url, listing_url) ~ '\\.html?(\\?|$)'
                  AND COALESCE(car_url, listing_url) !~ '/(new|used|certified)?-?(inventory|vehicles|stock)/?(index\\.html?)?(\\?|$)'
                ORDER BY scraped_at DESC NULLS LAST
                LIMIT %s
                """,
                (limit,),
            )
        return cur.fetchall()


def _write(conn, listing_id: str, image_url: Optional[str], svg_url: Optional[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE public.listings
               SET image_url = %s,
                   image_svg_url = %s
             WHERE id::text = %s
            """,
            (image_url, svg_url, listing_id),
        )


def _listing_key(row) -> str:
    """Use the VIN when present (stable across re-scrapes); fall back
    to the listing UUID otherwise. This becomes the S3 object name."""
    listing_id, vin, *_ = row
    return (vin or listing_id).strip()


def run(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if os.environ.get("CARPAPI_DB_HOST", "").startswith("localhost"):
        log.warning(
            "CARPAPI_DB_HOST=localhost — running against the local dev "
            "DB. Source data/secrets/rds.env to write to RDS instead."
        )

    with psycopg.connect(_dsn(), autocommit=True) as conn:
        rows = _pick_rows(
            conn,
            limit=args.limit,
            listing_id=args.listing_id,
            vin=args.vin,
            reprocess_existing=args.reprocess_existing,
        )
        if not rows:
            log.info("no candidate listings to process")
            return 0

        log.info("processing %d listings", len(rows))
        ok = 0
        miss = 0
        fail = 0
        for row in rows:
            listing_id, vin, page_url, make, model, year = row
            key = _listing_key(row)
            log.info("→ %s %s %s | %s", make, model, year or "?", page_url)
            html = fetch_listing_html(page_url)
            img_url = first_image_url(html, base_url=page_url)
            if not img_url:
                log.info("  no image found on page (404? JS-only?)")
                miss += 1
                time.sleep(args.sleep)
                continue
            log.info("  source: %s", img_url[:140])
            result = process_for_listing(
                listing_key=key,
                source_url=img_url,
                generate_svg=not args.no_svg,
            )
            if result.likely_placeholder:
                # Source page yielded a dealer logo / placeholder asset.
                # NULL out any stale URL so the chat card falls back to
                # the bi-car-front-fill icon instead of showing a logo.
                _write(conn, listing_id, None, None)
                log.info(
                    "  skipped (placeholder): svg=%db jpg=%db",
                    result.bytes_svg, result.bytes_jpg,
                )
                miss += 1
            elif not result.ok:
                log.info("  process failed: %s", result.error)
                fail += 1
            else:
                _write(conn, listing_id, result.image_url, result.image_svg_url)
                log.info(
                    "  ok: jpg=%db svg=%db url=%s",
                    result.bytes_jpg, result.bytes_svg, result.image_url,
                )
                ok += 1
            time.sleep(args.sleep)

        log.info(
            "done: %d ok, %d no-image, %d failed (of %d)",
            ok, miss, fail, len(rows),
        )
        return 0 if ok > 0 else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=10, help="rows to process")
    p.add_argument("--sleep", type=float, default=1.5,
                   help="seconds between requests (rate-limit)")
    p.add_argument("--listing-id", help="process exactly one listing by UUID")
    p.add_argument("--vin", help="process exactly one listing by VIN")
    p.add_argument("--no-svg", action="store_true",
                   help="skip the SVG silhouette pass")
    p.add_argument(
        "--reprocess-existing", action="store_true",
        help="overwrite rows that already have image_url set "
             "(used after an extractor fix)",
    )
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
