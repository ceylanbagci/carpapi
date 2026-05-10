"""Create and seed ``public.makes`` on the carpapi Postgres.

Schema (idempotent — safe to re-run):

    CREATE TABLE IF NOT EXISTS public.makes (
        id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        slug         TEXT NOT NULL UNIQUE,
        name         TEXT NOT NULL UNIQUE,
        homepage_url TEXT,
        logo_url     TEXT,
        created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );

Sources for the row set, in order:
  1. distinct ``listings.make`` already in the DB
  2. distinct entries from ``dealers.makes_carried[]``
  3. every key in api.make_info.HOMEPAGES (so even makes with zero
     listings get a row when their homepage is known)

Each row is upserted: existing makes get their homepage_url / logo_url
updated, brand-new makes are inserted. Nothing is deleted.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from api.make_info import HOMEPAGES, homepage_for, logo_url_for, slug_for_filename  # noqa: E402


DDL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.makes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug         TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL UNIQUE,
    homepage_url TEXT,
    logo_url     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_makes_name ON public.makes (name);
"""

UPSERT = """
INSERT INTO public.makes (slug, name, homepage_url, logo_url)
VALUES (%(slug)s, %(name)s, %(homepage_url)s, %(logo_url)s)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    homepage_url = EXCLUDED.homepage_url,
    logo_url = EXCLUDED.logo_url,
    updated_at = now();
"""


def discover_make_names(cur) -> set[str]:
    found: set[str] = set()

    cur.execute(
        "SELECT DISTINCT make FROM public.listings "
        "WHERE make IS NOT NULL AND length(trim(make)) > 0"
    )
    for (m,) in cur.fetchall():
        found.add(m.strip())

    cur.execute(
        "SELECT DISTINCT unnest(makes_carried) FROM public.dealers "
        "WHERE makes_carried IS NOT NULL"
    )
    for (m,) in cur.fetchall():
        if m and m.strip():
            found.add(m.strip())

    # Fold in known homepages so well-known makes get a row even if
    # they have zero listings/dealers.
    title_cased = {k.title() for k in HOMEPAGES.keys()}
    for tc in title_cased:
        if not any(tc.lower() == n.lower() for n in found):
            found.add(tc)
    return found


def main() -> int:
    dsn = (
        f"host={os.environ.get('CARPAPI_DB_HOST', 'localhost')} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5433')} "
        f"dbname={os.environ.get('CARPAPI_DB_NAME', 'carpapi')} "
        f"user={os.environ.get('CARPAPI_DB_USER', 'carpapi')} "
        f"password={os.environ.get('CARPAPI_DB_PASSWORD', 'carpapi')}"
    )

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        conn.commit()

        names = discover_make_names(cur)
        # canonicalize: collapse case-only duplicates by preferring the
        # variant that already exists in the DB / the title-cased form.
        unique_by_lower: dict[str, str] = {}
        for n in sorted(names):
            unique_by_lower.setdefault(n.lower(), n)
        rows = [
            {
                "slug": slug_for_filename(name),
                "name": name,
                "homepage_url": homepage_for(name),
                "logo_url": logo_url_for(name),
            }
            for name in unique_by_lower.values()
        ]

        cur.executemany(UPSERT, rows)
        conn.commit()

        cur.execute("SELECT COUNT(*) FROM public.makes")
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM public.makes "
            "WHERE homepage_url IS NOT NULL"
        )
        with_home = cur.fetchone()[0]

    print(f"Seeded {len(rows)} makes; table now has {total} rows "
          f"({with_home} with homepage_url).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
