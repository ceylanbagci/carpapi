"""Generate placeholder SVG logos for every make in the DB.

Each SVG is a rounded square in the make's accent color with the make's
initials in white — distinct, deterministic, and free of trademarked
imagery. Output goes to ``MEDIA_ROOT/logos/<slug>.svg``.

Usage:
    python generate_logos.py            # uses live DB to discover makes
    python generate_logos.py --offline  # uses MAKE_INFO map only
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
MEDIA_LOGOS = BASE / "media" / "logos"

sys.path.insert(0, str(BASE))
from api.make_info import (  # noqa: E402
    COLORS,
    HOMEPAGES,
    color_for,
    initials_for,
    slug_for_filename,
)

SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100" role="img" aria-label="{name} logo">
  <rect x="2" y="2" width="96" height="96" rx="18" ry="18" fill="{color}"/>
  <text x="50" y="50" text-anchor="middle" dominant-baseline="central"
        font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif"
        font-size="{font_size}" font-weight="700" letter-spacing="0.02em" fill="#ffffff">{initials}</text>
</svg>
"""


def font_size_for(initials: str) -> int:
    return {1: 56, 2: 36, 3: 26, 4: 22}.get(len(initials), 22)


def render_svg(make: str) -> str:
    initials = initials_for(make)
    return SVG_TEMPLATE.format(
        name=make,
        color=color_for(make),
        initials=initials,
        font_size=font_size_for(initials),
    )


def discover_makes_from_db() -> list[str]:
    import psycopg

    dsn = (
        f"host={os.environ.get('CARPAPI_DB_HOST', 'localhost')} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5433')} "
        f"dbname={os.environ.get('CARPAPI_DB_NAME', 'carpapi')} "
        f"user={os.environ.get('CARPAPI_DB_USER', 'carpapi')} "
        f"password={os.environ.get('CARPAPI_DB_PASSWORD', 'carpapi')}"
    )
    found: set[str] = set()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT DISTINCT make FROM public.listings WHERE make IS NOT NULL")
        for (m,) in cur.fetchall():
            found.add(m)
        cur.execute(
            "SELECT DISTINCT unnest(makes_carried) FROM public.dealers "
            "WHERE makes_carried IS NOT NULL"
        )
        for (m,) in cur.fetchall():
            if m:
                found.add(m)
    return sorted(found)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--offline",
        action="store_true",
        help="don't query the DB; render logos for every make in MAKE_INFO",
    )
    args = p.parse_args()

    MEDIA_LOGOS.mkdir(parents=True, exist_ok=True)

    if args.offline:
        makes = sorted({*HOMEPAGES.keys(), *COLORS.keys()})
        # offline keys are lowercased; use the canonical-cased version in the SVG
        makes = [m.title() if m != "bmw" and m != "gmc" else m.upper() for m in makes]
    else:
        try:
            makes = discover_makes_from_db()
        except Exception as exc:
            print(f"DB discovery failed ({exc}); falling back to offline list.")
            makes = sorted({*HOMEPAGES.keys(), *COLORS.keys()})
            makes = [m.title() for m in makes]

    written = 0
    for m in makes:
        path = MEDIA_LOGOS / f"{slug_for_filename(m)}.svg"
        path.write_text(render_svg(m))
        written += 1

    print(f"Wrote {written} logos to {MEDIA_LOGOS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
