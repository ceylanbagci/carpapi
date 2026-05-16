"""dealer-prospector — interactive agent placeholder.

This agent's real work (running `discover_cms` against a region,
filtering by the allowlist, opening a PR) is human-supervised. The
scheduled fire just refreshes the dashboard state with the current
roster of active dealers.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from ._common import db_connect


def handle(event: dict, context: Any) -> dict:
    with db_connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM public.dealers WHERE status='active'")
        active = int(cur.fetchone()[0])
        cur.execute(
            "SELECT COUNT(*) FROM public.dealers WHERE status='active' AND cms IS NULL"
        )
        unclassified = int(cur.fetchone()[0])

    return {
        "ok": True,
        "agent": "dealer-prospector",
        "mode": "interactive_placeholder",
        "active_dealers": active,
        "unclassified": unclassified,
        "note": (
            "Real prospecting runs from Claude Code: "
            "`python tools/discover_cms.py --region NJ` → PR review → activate."
        ),
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
