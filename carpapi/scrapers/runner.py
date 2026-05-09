from __future__ import annotations

"""Per-dealer scrape runner.

Threads a single dealer through:
  1. robots.txt check (refuse if disallowed — never bypass)
  2. CMS routing (only Dealer.com adapter shipped today)
  3. Adapter parse: listing inline → VDPs as needed
  4. scrape_monitor.analyze() statistical gate
  5. carapi_pipeline.run_ingest_batch → normalize → dedupe → upsert
  6. IngestRepo.start_run / finish_run + per-listing raw pointer

Per project policy:
  - Approved stack only (requests + bs4 in adapters; no LLM).
  - Per-host throttling enforced HERE (sleep between requests).
  - On 4xx/429/403: stop the dealer, don't escalate. Move on.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from carapi_pipeline.pipeline import run_ingest_batch
from carapi_pipeline.settings import load_settings
from carpapi.db import (
    DealerRepo,
    IngestRepo,
    MonitorRepo,
    SourceRepo,
    session_scope,
)
from carpapi.monitor.scrape_monitor import ScrapeMonitorThresholds, analyze
from carpapi.scrapers.adapters import dealer_dot_com

log = logging.getLogger(__name__)


@dataclass
class DealerRunResult:
    dealer_slug: str
    cms: str
    inventory_url: str
    listings_extracted: int = 0
    listings_inserted: int = 0
    listings_updated: int = 0
    listings_rejected: int = 0
    pages_fetched: int = 0
    http_errors: int = 0
    monitor_healthy: bool = True
    monitor_flags: list[str] = field(default_factory=list)
    skipped_reason: Optional[str] = None


# --------------------------------------------------------------------- #
# robots.txt
# --------------------------------------------------------------------- #


def _robots_for(url: str) -> Optional[RobotFileParser]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        return None
    rp = RobotFileParser()
    rp.set_url(f"{parsed.scheme}://{parsed.hostname}/robots.txt")
    try:
        rp.read()
    except Exception:  # noqa: BLE001
        return None
    return rp


def _robots_allows(rp: Optional[RobotFileParser], url: str, user_agent: str) -> bool:
    if rp is None:
        # No robots.txt or unreachable — treat as permissive (default
        # internet posture). Belt-and-braces: caller still has the
        # dealer.robots_allows_inventory column from discovery.
        return True
    try:
        return bool(rp.can_fetch(user_agent, url))
    except Exception:  # noqa: BLE001
        return True


# --------------------------------------------------------------------- #
# Per-dealer run
# --------------------------------------------------------------------- #


def run_for_dealer(
    dealer_slug: str,
    *,
    max_listings: int = 25,
    rate_limit_seconds: float = 1.5,
    run_kind: str = "manual",
) -> DealerRunResult:
    """Scrape one dealer and ingest results into Postgres.

    Returns a DealerRunResult with counts + flags. Never raises on policy
    issues (robots, CMS not supported); records the reason in
    skipped_reason and returns instead.
    """
    settings = load_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    # 1. Look up dealer metadata.
    with session_scope(autocommit=False) as session:
        dealer = DealerRepo.get_by_slug(session, dealer_slug)
        if dealer is None:
            return DealerRunResult(
                dealer_slug=dealer_slug,
                cms="?",
                inventory_url="",
                skipped_reason=f"dealer slug {dealer_slug!r} not found in public.dealers",
            )
        cms = dealer.cms or "unknown"
        inventory_url = dealer.inventory_url or ""
        dealer_name = dealer.name
        region = dealer.region
        city = dealer.city
        robots_known = dealer.robots_allows_inventory

    result = DealerRunResult(
        dealer_slug=dealer_slug, cms=cms, inventory_url=inventory_url
    )

    # 2. CMS routing — only Dealer.com is implemented today.
    if cms != "dealer.com":
        result.skipped_reason = (
            f"no adapter for CMS {cms!r} yet (only dealer.com is implemented)"
        )
        return result

    if not inventory_url:
        result.skipped_reason = "dealer has no inventory_url; run discover_cms first"
        return result

    # 3. Robots check — always honor it, even if discovery already said allow.
    rp = _robots_for(inventory_url)
    allowed = _robots_allows(rp, inventory_url, dealer_dot_com.USER_AGENT)
    if not allowed:
        result.skipped_reason = "robots.txt disallows the discovered inventory URL"
        return result
    if robots_known is False:
        # Belt-and-braces: respect what discovery saw too.
        result.skipped_reason = "dealer.robots_allows_inventory is False (discovery)"
        return result

    # 4. Ensure source row exists for this dealer.
    source_id = dealer_slug
    with session_scope() as session:
        SourceRepo.upsert(
            session,
            {
                "id": source_id,
                "name": f"{dealer_name} (Dealer.com)",
                "type": "scrape",
                "priority": 5,
            },
        )

    # 5. Start an ingest run.
    with session_scope() as session:
        run = IngestRepo.start_run(session, source_id=source_id, run_kind=run_kind)
        run_id = run.id

    started = time.time()
    canonical_listings: list[dict] = []
    http_error_count = 0
    pages_fetched = 0

    try:
        # 6. Fetch the inventory page.
        page = dealer_dot_com.fetch(inventory_url)
        pages_fetched += 1
        if page.error or page.status >= 400:
            http_error_count += 1
            log.warning(
                "[%s] inventory page error: status=%s err=%s",
                dealer_slug, page.status, page.error,
            )
            # Stop on initial 403/429 — don't escalate.
            if page.status in (403, 429):
                result.skipped_reason = f"inventory returned HTTP {page.status}; stopping"
        else:
            inline, vdps = dealer_dot_com.parse_listing_page(
                page,
                source_id=source_id,
                source_name=dealer_name,
                region=region,
                city=city,
            )
            log.info(
                "[%s] listing page: %d inline listings, %d VDP candidates",
                dealer_slug, len(inline), len(vdps),
            )
            canonical_listings.extend(inline)

            # 7. Walk VDPs until we hit max_listings.
            for vdp_url in vdps:
                if len(canonical_listings) >= max_listings:
                    break
                time.sleep(rate_limit_seconds)
                vdp_page = dealer_dot_com.fetch(vdp_url)
                pages_fetched += 1
                if vdp_page.status in (403, 429):
                    http_error_count += 1
                    log.warning(
                        "[%s] VDP %s returned HTTP %s — stopping for this dealer",
                        dealer_slug, vdp_url, vdp_page.status,
                    )
                    break
                if vdp_page.error or vdp_page.status >= 400:
                    http_error_count += 1
                    continue
                listing = dealer_dot_com.parse_vdp(
                    vdp_page,
                    source_id=source_id,
                    source_name=dealer_name,
                    region=region,
                    city=city,
                )
                if listing is not None:
                    canonical_listings.append(listing)
    except Exception as exc:  # noqa: BLE001
        log.exception("[%s] adapter raised: %s", dealer_slug, exc)
        with session_scope() as session:
            IngestRepo.finish_run(
                session,
                run_id,
                counts={"pages_fetched": pages_fetched, "http_errors": http_error_count},
                duration_seconds=time.time() - started,
                status="failed",
                error_summary={"message": str(exc), "type": type(exc).__name__},
            )
        raise

    result.listings_extracted = len(canonical_listings)
    result.pages_fetched = pages_fetched
    result.http_errors = http_error_count

    # 8. Statistical gate (zero AI). Per scraper-rules.md.
    if canonical_listings:
        report = analyze(
            canonical_listings,
            source_id=source_id,
            http_errors=http_error_count,
            http_total=pages_fetched,
            thresholds=ScrapeMonitorThresholds(
                # Loosen for live scrapes — a single dealer page often has
                # higher null rates on VIN than fixtures.
                max_null_rate_per_field={
                    "vin": 0.50,
                    "price_amount": 0.20,
                    "make": 0.10,
                    "model": 0.10,
                    "mileage": 0.40,
                    "year": 0.10,
                },
            ),
        )
        result.monitor_healthy = report.healthy
        result.monitor_flags = list(report.flags)
        with session_scope() as session:
            MonitorRepo.insert_scrape_report(
                session,
                ingest_run_id=run_id,
                source_id=source_id,
                record_count=report.record_count,
                null_rates=report.null_rates,
                duplicate_rate=float(report.duplicate_rate),
                http_error_rate=float(report.http_error_rate),
                flags=list(report.flags),
                healthy=report.healthy,
            )

    # 9. Hand off to the canonical ingest pipeline (normalize → dedupe → upsert).
    if canonical_listings:
        with Session(engine) as session:
            counts = run_ingest_batch(
                session,
                settings,
                canonical_listings,
                source_id=source_id,
                batch_id=uuid.uuid4(),
            )
            session.commit()
        result.listings_inserted = counts.get("RecordsInserted", 0)
        result.listings_updated = counts.get("RecordsUpdated", 0)
        result.listings_rejected = counts.get("RecordsRejected", 0)
    else:
        counts = {
            "RecordsFetched": 0, "RecordsNormalized": 0, "RecordsInserted": 0,
            "RecordsUpdated": 0, "RecordsSkipped": 0, "RecordsRejected": 0,
        }

    # 10. Close out the ingest run.
    duration = time.time() - started
    with session_scope() as session:
        status = "success"
        if result.skipped_reason:
            status = "partial"
        if not result.monitor_healthy:
            status = "partial"
        IngestRepo.finish_run(
            session,
            run_id,
            counts={**counts, "pages_fetched": pages_fetched, "http_errors": http_error_count},
            duration_seconds=duration,
            status=status,
        )
        DealerRepo.mark_scraped(session, dealer_slug)

    return result
