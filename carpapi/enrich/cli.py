"""Command-line entry points for the enrichment pipeline.

Subcommands:

  enrich-vin <vin>        — full cold-loop run for one VIN
  enrich-stale [--make M] [--limit N]
                          — backfill all rows where maker_specs IS NULL
                            and not in a sticky-failed status
  parse-sticker <vin>     — re-parse the existing window_sticker_url
                            without re-running the maker-site lookup
  status                  — print enrichment counts (top-line + per-make)
  refresh-prices          — placeholder for the hot loop (not yet wired)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Sequence

from . import db
from .orchestrator import enrich_one, parse_sticker_only

log = logging.getLogger("carpapi.enrich")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m carpapi.enrich",
        description="Listing enrichment pipeline (price hot loop + maker/sticker cold loop).",
    )
    p.add_argument("--debug", action="store_true", help="verbose logging")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("enrich-vin", help="cold-loop for one VIN")
    sp.add_argument("vin")
    sp.add_argument("--force-sticker", action="store_true",
                    help="re-parse the sticker even if window_sticker is set")

    sp = sub.add_parser("enrich-stale", help="cold-loop for every pending row")
    sp.add_argument("--make", help="restrict to one make")
    sp.add_argument("--limit", type=int, default=100,
                    help="max rows to process this run (default 100)")

    sp = sub.add_parser("parse-sticker", help="re-parse the sticker for one VIN")
    sp.add_argument("vin")

    sub.add_parser("status", help="enrichment status summary")
    sub.add_parser("refresh-prices",
                   help="(placeholder) hot loop — price-only refresh")

    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "enrich-vin":
        return _cmd_enrich_vin(args.vin, force_sticker=args.force_sticker)
    if args.command == "enrich-stale":
        return _cmd_enrich_stale(make=args.make, limit=args.limit)
    if args.command == "parse-sticker":
        return _cmd_parse_sticker(args.vin)
    if args.command == "status":
        return _cmd_status()
    if args.command == "refresh-prices":
        print("refresh-prices: not yet implemented in this build "
              "(see plan phase 1; the hot loop is a follow-up).",
              file=sys.stderr)
        return 2
    return 2


# --------------------------------------------------------------------- #
# Subcommand impls
# --------------------------------------------------------------------- #


def _cmd_enrich_vin(vin: str, *, force_sticker: bool = False) -> int:
    with db.connect() as conn, conn.cursor() as cur:
        listing = db.get_by_vin(cur, vin)
    if not listing:
        print(f"no listing found for VIN={vin}", file=sys.stderr)
        return 1
    res = enrich_one(listing, force_sticker=force_sticker)
    _print_result(res, listing)
    return 0 if res.status in ("enriched", "skipped") else 1


def _cmd_enrich_stale(*, make: str | None, limit: int) -> int:
    with db.connect() as conn, conn.cursor() as cur:
        pending = db.find_pending(cur, make=make, limit=limit)
    print(f"enrich-stale: {len(pending)} listings to process "
          f"(make={make or 'all'}, limit={limit})")
    counts = {"enriched": 0, "skipped": 0, "unsupported": 0,
              "login_required": 0, "failed": 0}
    for i, listing in enumerate(pending, 1):
        res = enrich_one(listing)
        counts[res.status] = counts.get(res.status, 0) + 1
        marker = {"enriched": "✓", "skipped": "·", "unsupported": "—",
                  "login_required": "🔒", "failed": "✗"}.get(res.status, "?")
        print(f"  [{i:4}/{len(pending)}] {marker} {(listing.make or '?'):<14} "
              f"{listing.year or '????'} {(listing.model or '?'):<18} "
              f"{listing.vin}  {res.status}: {res.detail}")
    print()
    print("summary:", "  ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


def _cmd_parse_sticker(vin: str) -> int:
    with db.connect() as conn, conn.cursor() as cur:
        listing = db.get_by_vin(cur, vin)
    if not listing:
        print(f"no listing found for VIN={vin}", file=sys.stderr)
        return 1
    if not listing.window_sticker_url:
        print(f"VIN {vin} has no window_sticker_url; "
              "run `enrich-vin` first to discover one", file=sys.stderr)
        return 1
    res = parse_sticker_only(listing)
    _print_result(res, listing)
    return 0 if res.status == "enriched" else 1


def _cmd_status() -> int:
    with db.connect() as conn, conn.cursor() as cur:
        summary = db.status_summary(cur)
        per_make = db.per_make_coverage(cur, limit=25)

    print("Enrichment status (carpapi.public.listings)")
    print("=" * 60)
    for k, v in summary.items():
        print(f"  {k:<18} {v:>10,}")

    print()
    print(f"  {'make':<22} {'total':>7} {'enriched':>9} "
          f"{'sticker':>8} {'unsup':>7}")
    print("  " + "-" * 60)
    for make, total, enriched, sticker, unsup in per_make:
        print(f"  {make:<22} {total:>7,} {enriched:>9,} {sticker:>8,} {unsup:>7,}")
    return 0


def _print_result(res, listing) -> None:
    print(f"VIN          {listing.vin}")
    print(f"make/model   {listing.make} {listing.model} {listing.year or ''} "
          f"({listing.trim or 'no trim'})")
    print(f"status       {res.status}")
    if res.detail:
        print(f"detail       {res.detail}")
    if res.maker_url:
        print(f"maker_url    {res.maker_url}")
    if res.sticker_url:
        print(f"sticker_url  {res.sticker_url}")
    if res.sticker_msrp is not None:
        print(f"sticker_msrp ${res.sticker_msrp:,}")
