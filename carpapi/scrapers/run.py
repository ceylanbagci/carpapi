from __future__ import annotations

"""CLI: `python -m carpapi.scrapers.run`

Routes to per-dealer scrapers and ingests results into Postgres.

Usage:
  python -m carpapi.scrapers.run --dealer-slug <slug>
  python -m carpapi.scrapers.run --cms dealer.com --limit-dealers 5 --max-listings 25

Per project policy:
  - Honors robots.txt (the runner refuses on disallow).
  - Stops on 403/429 per dealer; moves on instead of escalating.
  - Daily cadence is the default in operations; this CLI runs ad-hoc.
"""

import argparse
import logging
import sys
from typing import Optional

from carpapi.db import session_scope
from carpapi.db.models import Dealer
from carpapi.scrapers.runner import run_for_dealer

log = logging.getLogger(__name__)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="carpapi.scrapers.run")
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument(
        "--dealer-slug",
        help="Run a single dealer by slug (see public.dealers.slug).",
    )
    sel.add_argument(
        "--cms",
        help="Run all dealers with this CMS (e.g. 'dealer.com').",
    )

    p.add_argument(
        "--limit-dealers",
        type=int,
        default=0,
        help="With --cms: cap number of dealers processed (0 = all matching).",
    )
    p.add_argument(
        "--max-listings",
        type=int,
        default=25,
        help="Per-dealer cap on listings extracted (limits VDP fetches).",
    )
    p.add_argument(
        "--rate-limit-seconds",
        type=float,
        default=1.5,
        help="Sleep between requests to the same host.",
    )
    return p.parse_args(argv)


def _select_dealers(cms: str, limit: int) -> list[str]:
    """Return slugs of dealers to scrape, ordered for predictability."""
    from sqlalchemy import select

    with session_scope(autocommit=False) as session:
        stmt = (
            select(Dealer.slug)
            .where(Dealer.cms == cms, Dealer.status == "active")
            .where(Dealer.inventory_url.is_not(None))
            .order_by(Dealer.slug)
        )
        if limit > 0:
            stmt = stmt.limit(limit)
        return [row[0] for row in session.execute(stmt)]


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    args = parse_args(argv)

    slugs: list[str]
    if args.dealer_slug:
        slugs = [args.dealer_slug]
    else:
        slugs = _select_dealers(args.cms, args.limit_dealers)
        if not slugs:
            log.error(
                "no active dealers with cms=%r and inventory_url set", args.cms
            )
            return 2

    log.info("running %d dealer(s)", len(slugs))
    grand_extracted = 0
    grand_inserted = 0
    grand_skipped = 0
    for i, slug in enumerate(slugs, 1):
        log.info("=" * 60)
        log.info("[%d/%d] dealer: %s", i, len(slugs), slug)
        try:
            r = run_for_dealer(
                slug,
                max_listings=args.max_listings,
                rate_limit_seconds=args.rate_limit_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("[%s] runner crashed: %s", slug, exc)
            continue

        if r.skipped_reason:
            grand_skipped += 1
            log.warning("[%s] skipped: %s", slug, r.skipped_reason)
            continue

        grand_extracted += r.listings_extracted
        grand_inserted += r.listings_inserted
        log.info(
            "[%s] extracted=%d inserted=%d updated=%d rejected=%d "
            "pages=%d http_errors=%d monitor_healthy=%s flags=%s",
            slug,
            r.listings_extracted,
            r.listings_inserted,
            r.listings_updated,
            r.listings_rejected,
            r.pages_fetched,
            r.http_errors,
            r.monitor_healthy,
            r.monitor_flags or "[]",
        )

    log.info("=" * 60)
    log.info(
        "TOTAL: %d dealers tried, %d skipped, %d listings extracted, %d inserted",
        len(slugs), grand_skipped, grand_extracted, grand_inserted,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
