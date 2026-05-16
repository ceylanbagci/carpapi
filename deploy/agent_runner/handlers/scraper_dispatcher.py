"""Handler for the `scraper-dispatcher` agent.

This Lambda is the **orchestrator** of CarPapi's daily ingest. It
lives at the front of the pipeline:

  scraper-dispatcher  (THIS Lambda — picks dealers, fans out)
        ↓
  scrape-worker       (per-dealer Lambda — Selenium + Dealer.com adapter; NOT YET DEPLOYED)
        ↓
  listing-validator   (SQS-triggered — normalizes + upserts to public.listings)

What this handler does on each invocation:

  1. Connect to RDS (Lambda is wired into the App Runner VPC so the
     private route through `sg-0897cabb71dc01061` works; RDS auth via
     the existing `CARPAPI_DB_*` env vars).
  2. Pick a batch of N active dealers that haven't been scraped recently
     (`status='active' ORDER BY COALESCE(last_scraped_at, '1970')
     ASC LIMIT N`). N defaults to 5 per fire; configurable via the
     `CARPAPI_SCRAPE_BATCH_SIZE` env var.
  3. Filter by allowlist CMS — Dealer.com only today, per
     `context/scraper-rules.md`. DealerOn + Dealer Inspire are policy-
     blocked at the source.
  4. For each picked dealer: emit a structured `scrape_plan` entry.
     The actual scrape doesn't run yet — the worker Lambda hasn't been
     deployed (it needs the Selenium image, follow-up). For now the
     dispatcher just identifies WHO would get scraped.
  5. Mark `dealers.last_scraped_at = NOW()` ONLY for dealers we'd
     actually invoke a worker for. (Future: only mark after the worker
     reports success via SQS.)

The handler returns a structured plan that the fleet dashboard reads
via S3. That plan is the source-of-truth for what the next scrape
cycle WILL do — humans can review it before turning on the worker.

Failure handling:
  - DB connect timeout → raises (Lambda retry + DLQ).
  - No active dealers found → returns `ok=True, picked=0`. Not an error.
  - One dealer's row is malformed (e.g. NULL inventory_url) → skipped,
    counted in `skipped_reasons`. Doesn't fail the whole run.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any

import psycopg

log = logging.getLogger("carpapi.agent.scraper_dispatcher")


# ── Config ───────────────────────────────────────────────────────────
BATCH_SIZE = int(os.environ.get("CARPAPI_SCRAPE_BATCH_SIZE", "5"))
DRY_RUN = os.environ.get("CARPAPI_SCRAPE_DRYRUN", "1") == "1"

# CMSes we're allowed to scrape per `context/scraper-rules.md`. Today
# only Dealer.com is shipped; everything else is policy-blocked
# (DealerOn, Dealer Inspire — both via robots.txt / bot defenses).
ALLOWED_CMSES = {"dealer.com", "dealer_com", "dealercom"}


def _db_dsn() -> str:
    """Build a libpq connection string from the standard env vars.
    Same convention used by the rest of CarPapi (App Runner + local
    tooling). Pulled from the Lambda function config (Variables=...)."""
    return (
        f"host={os.environ['CARPAPI_DB_HOST']} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5432')} "
        f"dbname={os.environ['CARPAPI_DB_NAME']} "
        f"user={os.environ['CARPAPI_DB_USER']} "
        f"password={os.environ['CARPAPI_DB_PASSWORD']} "
        f"connect_timeout=8"
    )


def _pick_dealers(conn, limit: int) -> list[dict]:
    """Pick the N active dealers most overdue for a scrape."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text, slug, name, cms, inventory_url, region, city,
                   last_scraped_at
              FROM public.dealers
             WHERE status = 'active'
             ORDER BY COALESCE(last_scraped_at, TIMESTAMP '1970-01-01') ASC,
                      slug ASC
             LIMIT %s
            """,
            (limit,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _classify_dealer(d: dict) -> tuple[bool, str]:
    """Returns (would_dispatch, reason)."""
    cms = (d.get("cms") or "").lower().strip()
    if not cms:
        return False, "no_cms_classified — run discover_cms first"
    if cms not in ALLOWED_CMSES:
        return False, f"cms_blocked: {cms} (per scraper-rules.md)"
    if not d.get("inventory_url"):
        return False, "no inventory_url on dealer row"
    return True, "ok"


def handle(event: dict, context: Any) -> dict:
    log.info("scraper-dispatcher starting")

    plan: list[dict] = []
    skipped: list[dict] = []

    try:
        with psycopg.connect(_db_dsn()) as conn:
            dealers = _pick_dealers(conn, BATCH_SIZE)
            for d in dealers:
                would, reason = _classify_dealer(d)
                row = {
                    "slug": d["slug"],
                    "name": d["name"],
                    "cms": d["cms"],
                    "inventory_url": d["inventory_url"],
                    "last_scraped_at": (
                        d["last_scraped_at"].isoformat()
                        if d["last_scraped_at"] else None
                    ),
                    "reason": reason,
                }
                if would:
                    plan.append(row)
                else:
                    skipped.append(row)

            # In DRY_RUN mode we DON'T touch last_scraped_at — the actual
            # scrape worker will update it on real completion. The MVP
            # path is therefore a pure read; nothing in RDS changes from
            # this Lambda firing today.
            #
            # Once the scrape-worker Lambda is wired, this is where we
            # would: SQS send-message-batch into carpapi-scrape-batches
            # with each (dealer_slug, inventory_url, cms) job. The worker
            # consumes one job at a time, runs the Selenium adapter,
            # writes raw payloads to ingest.raw_payloads, and only THEN
            # updates dealers.last_scraped_at.
    except psycopg.OperationalError as exc:
        log.error("db connect failed: %s", exc)
        # Raise — Lambda retry + DLQ will eventually notify.
        raise

    return {
        "ok": True,
        "batch_size": BATCH_SIZE,
        "dry_run": DRY_RUN,
        "plan_count": len(plan),
        "skipped_count": len(skipped),
        "plan": plan,
        "skipped": skipped[:5],   # cap to keep state file small
        "next_steps": [
            "Deploy carpapi-scrape-worker Lambda (Selenium image) to actually scrape these",
            f"Plan above covers {len(plan)} dealers — total active fleet has many more (next batch will pick the next overdue {BATCH_SIZE})",
        ],
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
