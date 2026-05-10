"""Seed public.dealers from output/dealers_final.json (491 NJ rows).

Idempotent on slug — re-running updates existing rows. Designed for the
local-dev bootstrap; production seeding lives in carpapi.db.cli.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "output" / "dealers_final.json"


def slugify(name: str, make: str) -> str:
    raw = f"{name}-{make}".lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw[:120] or "unknown"


def normalize_url(u: str | None) -> str | None:
    if not u:
        return None
    if u.startswith("VERIFY:"):
        return None
    return u.strip()


def main() -> None:
    data = json.loads(SOURCE.read_text())
    print(f"Loaded {len(data)} dealers from {SOURCE}")

    by_slug: dict[str, dict] = {}
    for d in data:
        slug = slugify(d["name"], d["make"])
        if slug in by_slug:
            row = by_slug[slug]
            existing = set(row.get("makes_carried") or [])
            existing.add(d["make"])
            row["makes_carried"] = sorted(existing)
            continue
        by_slug[slug] = {
            "slug": slug,
            "name": d["name"],
            "homepage_url": normalize_url(d.get("dealership_website")),
            "region": d.get("state"),
            "makes_carried": [d["make"]],
            "status": "active",
        }
    rows = list(by_slug.values())
    print(f"Deduped to {len(rows)} unique slugs.")

    dsn = (
        f"host={os.environ.get('CARPAPI_DB_HOST', 'localhost')} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5433')} "
        f"dbname={os.environ.get('CARPAPI_DB_NAME', 'carpapi')} "
        f"user={os.environ.get('CARPAPI_DB_USER', 'carpapi')} "
        f"password={os.environ.get('CARPAPI_DB_PASSWORD', 'carpapi')}"
    )

    sql = """
        INSERT INTO public.dealers
            (slug, name, homepage_url, region, makes_carried, status)
        VALUES
            (%(slug)s, %(name)s, %(homepage_url)s, %(region)s,
             %(makes_carried)s, %(status)s)
        ON CONFLICT (slug) DO UPDATE SET
            name = EXCLUDED.name,
            homepage_url = EXCLUDED.homepage_url,
            region = EXCLUDED.region,
            makes_carried = EXCLUDED.makes_carried,
            updated_at = now()
    """

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.executemany(sql, rows)
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM public.dealers")
        total = cur.fetchone()[0]
    print(f"Done. dealers row count = {total}")


if __name__ == "__main__":
    sys.exit(main())
