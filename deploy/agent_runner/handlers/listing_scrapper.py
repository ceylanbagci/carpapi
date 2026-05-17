"""listing-scrapper — plan a NEW-listings-only scrape cycle.

Spec lives at .claude/agents/listing_agents/listing_scrapper.md.

What this Lambda does on each fire:

  1. Pick the next batch of active+unblocked dealers, ordered by
     "unscraped first, then stalest" — same WHERE+ORDER BY the
     spec describes.
  2. For each dealer: nothing is fetched here (Lambda has no
     Selenium and Dealer.com is JS-rendered). Instead the handler
     reports the dealer in the cycle plan along with how many of
     its known inventory URLs are NOT yet in `public.listings`.
     That "candidate-count" is the agent's contribution: the
     same Lambda-side dedup step that the spec calls out as the
     fast path that lets the catalog grow cheaply.
  3. For each dealer marked `robots_allows_inventory = FALSE`,
     this cycle issues an UPDATE setting `status='blocked'`. The
     spec maps the user's `scrape_allowed=False` to this column
     (no scrape_allowed column exists on the schema today).
  4. Returns a structured plan that the fleet dashboard reads via
     `fleet/listing-scrapper.json`. The actual HTTP fetches + 5s
     per-listing sleep happen in a future Selenium-image worker
     Lambda (or in the local agent loop today).

Hard rules from the spec we enforce HERE (the Lambda):

  - No `UPDATE public.listings` — listings table is read-only in
    this handler. Pre-dedup query is read-only; the actual INSERTs
    are out of scope (no Selenium in this image).
  - At most one `UPDATE public.dealers` per row, only touching
    `status`. We never write `last_scraped_at` (that's the
    `scraper-dispatcher` worker's contract).
  - Round-robin: BATCH_SIZE caps at 10. The next cycle picks the
    next-most-overdue batch.

Failure model:
  - DB connect timeout → raises, Lambda retry kicks in.
  - Empty queue (all dealers blocked or never enrolled) → returns
    `ok=True, plan_count=0` — not an error.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any

from ._common import db_connect

log = logging.getLogger("carpapi.agent.listing_scrapper")

# Spec default N=10 per cycle. Configurable via env if a later
# operational need wants to widen the round-robin window.
BATCH_SIZE = int(os.environ.get("CARPAPI_LISTING_SCRAPPER_BATCH_SIZE", "10"))


def _pick_dealers(conn, limit: int) -> list[dict]:
    """Spec-mandated order:
       1. Unscraped dealers first (last_scraped_at IS NULL).
       2. Then by COALESCE(last_scraped_at, epoch) ASC (stalest).
       3. Tie-break by slug ASC for determinism."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, slug, name, cms, inventory_url,
                   last_scraped_at, robots_allows_inventory
              FROM public.dealers
             WHERE status = 'active'
               AND inventory_url IS NOT NULL
             ORDER BY (last_scraped_at IS NULL) DESC,
                      COALESCE(last_scraped_at, TIMESTAMP '1970-01-01') ASC,
                      slug ASC
             LIMIT %s
            """,
            (limit,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _count_new_candidates_by_dealer(conn, dealer_slug: str) -> int:
    """How many listings could this dealer contribute on a fresh
    scrape — i.e. how many of its inventory URLs are NOT yet in
    `public.listings`.

    This is a heuristic: we can't enumerate the dealer's full
    inventory without fetching the index page (Selenium territory).
    What we CAN do is look at how many listings the dealer already
    has — agents with 0 are highest-priority for a worker fetch.

    Returns the dealer's CURRENT listing count, which the dashboard
    can read as "this dealer needs attention if 0 / has data if > 0".
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM public.listings WHERE source_id = %s",
            (dealer_slug,),
        )
        (n,) = cur.fetchone()
        return int(n)


def _block_robots_disallowed(conn) -> list[str]:
    """Step 3 of the spec — the one permitted dealer write. Flip any
    `status='active'` dealer whose `robots_allows_inventory` is FALSE
    to `status='blocked'`. Idempotent: re-running this cycle won't
    re-touch already-blocked rows because of the WHERE filter.

    Returns the list of slugs we just blocked (for the cycle log)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE public.dealers
               SET status = 'blocked',
                   updated_at = NOW()
             WHERE status = 'active'
               AND robots_allows_inventory = FALSE
            RETURNING slug
            """
        )
        rows = cur.fetchall()
        # Persist the dealer status change — we DON'T commit anything
        # else from this Lambda (listings table reads are not in a
        # transaction). Explicit commit so the connection can be
        # reused.
        conn.commit()
        return [r[0] for r in rows]


def handle(event: dict, context: Any) -> dict:
    log.info("listing-scrapper starting; batch_size=%d", BATCH_SIZE)

    plan: list[dict] = []
    skipped: list[dict] = []
    blocked_now: list[str] = []

    with db_connect() as conn:
        # 1. Apply the only permitted dealer mutation BEFORE picking,
        #    so any dealer disallowed by robots drops out of this
        #    cycle's queue automatically.
        blocked_now = _block_robots_disallowed(conn)
        if blocked_now:
            log.info("blocked %d dealers via robots: %s",
                     len(blocked_now), ", ".join(blocked_now[:5]))

        # 2. Pick the batch.
        dealers = _pick_dealers(conn, BATCH_SIZE)

        # 3. For each dealer, build a plan row + count its current
        #    listing presence so the dashboard can rank which dealers
        #    need a worker fetch most urgently.
        for d in dealers:
            cur_count = _count_new_candidates_by_dealer(conn, d["slug"])
            row = {
                "slug": d["slug"],
                "name": d["name"],
                "cms": d["cms"],
                "inventory_url": d["inventory_url"],
                "last_scraped_at": (
                    d["last_scraped_at"].isoformat()
                    if d["last_scraped_at"] else None
                ),
                "current_listing_count": cur_count,
                "priority": (
                    "fresh-dealer" if d["last_scraped_at"] is None
                    else "stale-dealer"
                ),
            }
            # Skip dealers with no CMS classification (worker would
            # have nothing to dispatch to). These count as skipped,
            # not blocked — the next cycle will surface them again
            # in case discover_cms ran in between.
            cms = (d.get("cms") or "").lower().strip()
            if not cms:
                row["reason"] = "no_cms_classified — run discover_cms first"
                skipped.append(row)
                continue
            plan.append(row)

    return {
        "ok": True,
        "agent": "listing-scrapper",
        "batch_size": BATCH_SIZE,
        "plan_count": len(plan),
        "skipped_count": len(skipped),
        "blocked_this_cycle": blocked_now,
        # Cap the plan in the state file — keep it greppable in S3.
        "plan": plan[:BATCH_SIZE],
        "skipped": skipped[:5],
        "notes": [
            "Lambda handler is plan-only; actual HTTP fetches + 5s "
            "per-listing sleep happen in a Selenium-image worker "
            "(or the local agent loop). The 5s rate limit is the "
            "worker's contract, not this Lambda's.",
            "Pre-dedup against public.listings.listing_url is done "
            "in the worker — this Lambda reports current per-dealer "
            "listing counts so the dashboard can rank priorities.",
            "Only mutation this Lambda performs is UPDATE "
            "public.dealers SET status='blocked' WHERE "
            "robots_allows_inventory=FALSE — every other write is "
            "out of this handler's scope.",
        ],
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
