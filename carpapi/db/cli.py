from __future__ import annotations

"""Adapter CLI:  python -m carpapi.db {init|status|seed-dealers|drop-all}

  init           Apply schema.sql (idempotent — safe to re-run).
  status         Show schemas, tables, row counts.
  seed-dealers   Bulk-load output/dealers_final.json into public.dealers.
                 Optionally enrich from output/dealer_cms_map.json if present.
  drop-all       Dangerous. Drops the carpapi-managed schemas (ingest,
                 monitor, ai) and our public tables. Refuses unless
                 --yes-really-drop is passed.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from carpapi.db.engine import get_engine, session_scope
from carpapi.db.repositories import DealerRepo, SourceRepo

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = REPO_ROOT / "carpapi" / "db" / "schema.sql"
DEALERS_JSON = REPO_ROOT / "output" / "dealers_final.json"
CMS_MAP_JSON = REPO_ROOT / "output" / "dealer_cms_map.json"


def cmd_init(_args: argparse.Namespace) -> int:
    if not SCHEMA_SQL.exists():
        log.error("missing %s", SCHEMA_SQL)
        return 2
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    engine = get_engine()
    with engine.begin() as conn:
        # Need to run as a single script — DO blocks include semicolons.
        # SQLAlchemy's `text()` plus engine.exec_driver_sql is the easiest
        # way to send the whole script verbatim.
        conn.exec_driver_sql(sql)
    log.info("applied %s", SCHEMA_SQL)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    engine = get_engine()
    with engine.connect() as conn:
        schemas = list(
            conn.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name IN ('public', 'ingest', 'monitor', 'ai') "
                    "ORDER BY schema_name"
                )
            )
        )
        print("Schemas:", [r[0] for r in schemas])
        print()
        tables = conn.execute(
            text(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema IN ('public', 'ingest', 'monitor', 'ai')
                  AND table_type = 'BASE TABLE'
                ORDER BY table_schema, table_name
                """
            )
        ).all()
        print(f"{'Schema':<10} {'Table':<30} {'Rows':>10}")
        print("-" * 55)
        for schema, table in tables:
            try:
                count = conn.execute(
                    text(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
                ).scalar_one()
            except Exception as exc:  # noqa: BLE001
                count = f"err: {exc.__class__.__name__}"
            print(f"{schema:<10} {table:<30} {count:>10}")
    return 0


def _seed_dealers_load_records() -> tuple[list[dict], dict[str, dict]]:
    """Load dealers + the optional CMS-map enrichment by name."""
    if not DEALERS_JSON.exists():
        raise FileNotFoundError(f"missing {DEALERS_JSON}")
    dealers = json.loads(DEALERS_JSON.read_text(encoding="utf-8"))
    cms_map: dict[str, dict] = {}
    if CMS_MAP_JSON.exists():
        try:
            recs = json.loads(CMS_MAP_JSON.read_text(encoding="utf-8"))
            cms_map = {r["dealer_name"]: r for r in recs if "dealer_name" in r}
        except json.JSONDecodeError:
            pass
    return dealers, cms_map


def _record_to_fields(rec: dict, cms_rec: Optional[dict]) -> dict:
    name = rec.get("name") or "Unnamed dealer"
    slug = DealerRepo.slugify(name)
    fields: dict = {
        "slug": slug,
        "name": name,
        "homepage_url": rec.get("dealership_website"),
        "region": _state_to_region(rec.get("state")),
        "makes_carried": [rec["make"]] if rec.get("make") else None,
        "status": "active",
    }
    if cms_rec:
        fields["cms"] = cms_rec.get("cms")
        fields["cms_signals"] = (
            {"signals": cms_rec.get("cms_signals") or []} if cms_rec.get("cms_signals") else None
        )
        fields["robots_allows_inventory"] = cms_rec.get("robots_allows_inventory")
        fields["inventory_url"] = cms_rec.get("inventory_url") or None
    return fields


_STATE_MAP = {
    "new-jersey": "NJ", "new-york": "NY", "pennsylvania": "PA", "connecticut": "CT",
}


def _state_to_region(state: Optional[str]) -> Optional[str]:
    if not state:
        return None
    return _STATE_MAP.get(state, state.upper()[:2])


def cmd_seed_dealers(args: argparse.Namespace) -> int:
    dealers, cms_map = _seed_dealers_load_records()
    log.info("loaded %d dealers, %d CMS records", len(dealers), len(cms_map))

    inserted = 0
    updated = 0
    merged_makes_count = 0
    seen_slugs: dict[str, set[str]] = {}

    with session_scope() as session:
        # Pass 1: collect makes per dealer slug so a dealer that sells
        # multiple brands (one row per (dealer, make) in the source) gets
        # an array of makes_carried, not just the last one we processed.
        for rec in dealers:
            name = rec.get("name") or ""
            slug = DealerRepo.slugify(name)
            if rec.get("make"):
                seen_slugs.setdefault(slug, set()).add(rec["make"])

        # Pass 2: upsert. For dealers that appeared multiple times, keep
        # the merged set of makes.
        seen_done: set[str] = set()
        for rec in dealers:
            name = rec.get("name") or ""
            slug = DealerRepo.slugify(name)
            if slug in seen_done:
                continue
            seen_done.add(slug)
            cms_rec = cms_map.get(name)
            fields = _record_to_fields(rec, cms_rec)
            makes = sorted(seen_slugs.get(slug) or set())
            fields["makes_carried"] = makes or None
            if len(makes) > 1:
                merged_makes_count += 1

            existed = DealerRepo.get_by_slug(session, slug) is not None
            DealerRepo.upsert(session, fields)
            if existed:
                updated += 1
            else:
                inserted += 1
            if args.limit and (inserted + updated) >= args.limit:
                break

    log.info(
        "seed complete: %d inserted, %d updated, %d multi-brand dealers",
        inserted, updated, merged_makes_count,
    )
    return 0


def cmd_seed_sources(_args: argparse.Namespace) -> int:
    """Register the well-known sources we already have."""
    rows = [
        {"id": "demo_dealer", "name": "Demo Dealer Feed", "type": "fixture", "priority": 10},
        {"id": "other_feed", "name": "Other Feed (fixture dup test)", "type": "fixture", "priority": 5},
        {"id": "demo_batch", "name": "Demo Batch", "type": "fixture", "priority": 5},
    ]
    with session_scope() as session:
        for row in rows:
            SourceRepo.upsert(session, row)
    log.info("seeded %d sources", len(rows))
    return 0


def cmd_drop_all(args: argparse.Namespace) -> int:
    if not args.yes_really_drop:
        log.error("refusing to drop without --yes-really-drop")
        return 2
    engine = get_engine()
    with engine.begin() as conn:
        # Drop our schemas (cascades all tables in them).
        for schema in ("ingest", "monitor", "ai"):
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        # In public, drop only the tables we own (NOT listings — that's
        # owned by carapi_pipeline.models).
        for table in ("listing_groups", "dealers", "sources"):
            conn.exec_driver_sql(f'DROP TABLE IF EXISTS public."{table}" CASCADE')
        # Strip the listing_group_id column we added (best-effort).
        conn.exec_driver_sql(
            "ALTER TABLE IF EXISTS public.listings DROP COLUMN IF EXISTS listing_group_id"
        )
    log.warning("dropped carpapi-managed schemas and tables")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="carpapi.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Apply schema.sql idempotently").set_defaults(func=cmd_init)
    sub.add_parser("status", help="List schemas + tables + row counts").set_defaults(
        func=cmd_status
    )

    sd = sub.add_parser("seed-dealers", help="Load output/dealers_final.json into public.dealers")
    sd.add_argument("--limit", type=int, default=0, help="Cap number of dealers to seed")
    sd.set_defaults(func=cmd_seed_dealers)

    sub.add_parser("seed-sources", help="Register fixture sources").set_defaults(
        func=cmd_seed_sources
    )

    drop = sub.add_parser("drop-all", help="Drop carpapi-managed schemas + tables. Dangerous.")
    drop.add_argument("--yes-really-drop", action="store_true")
    drop.set_defaults(func=cmd_drop_all)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
