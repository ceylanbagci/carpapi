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


def _dedup_key(listing: dict) -> str:
    """Stable key used to detect duplicates across paginated pages.

    Dealer.com numbers its inventory by VIN; in rare cases a non-VIN
    Vehicle node appears (manager's specials, certified-pre-owned
    placeholders) and we fall back to its listing_url. Empty when
    neither field is set — those rows will deduplicate against each
    other but not against canonical rows, which is fine.
    """
    return (
        listing.get("vin")
        or listing.get("listing_url")
        or listing.get("external_id")
        or ""
    )


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
    allow_selenium: bool = True,
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

    # 2. CMS routing.
    # Known-blocked CMSes we never try (per scraper-rules.md):
    #   - dealeron: robots.txt explicitly disallows inventory paths
    #   - dealer_inspire: 403s plain HTTP; project policy disallows
    #     escalating past bot defenses
    if cms in ("dealeron", "dealer_inspire"):
        result.skipped_reason = (
            f"CMS {cms!r} is policy-blocked "
            "(robots.txt disallow / bot defense)"
        )
        return result

    if not inventory_url:
        result.skipped_reason = "dealer has no inventory_url; run discover_cms first"
        return result

    # For 'unknown' CMS we still try the Dealer.com adapter — many
    # 'unknown' dealers turn out to be Dealer.com themes that didn't
    # match the fingerprints. Adapter handles the case gracefully (0
    # listings → marked unhealthy by scrape_monitor, not crash).
    # Other known/different adapters can be wired here.
    adapter_cms = cms if cms == "dealer.com" else "dealer.com (try)"
    log.info("[%s] using dealer.com adapter (cms=%s)", dealer_slug, adapter_cms)

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
        # 6a. Fetch the inventory page (static, cheap). We walk pagination
        #     on Dealer.com via `?numRecsPerPage=100&start=N` — a single
        #     dealer can carry 60-200 new cars and the default page size
        #     of 30 was capping us to that first page. The pagination
        #     helper yields up to `max_pages` URLs; we stop early when a
        #     page returns zero NEW vehicles (dedup by VIN / vehicle_id).
        paginated_urls = dealer_dot_com.paginated_inventory_urls(inventory_url)
        page = dealer_dot_com.fetch(paginated_urls[0])
        pages_fetched += 1
        if page.error or page.status >= 400:
            http_error_count += 1
            log.warning(
                "[%s] static inventory page error: status=%s err=%s",
                dealer_slug, page.status, page.error,
            )
            if page.status in (403, 429):
                # Bot defense — don't escalate to Selenium either; honor it.
                result.skipped_reason = f"inventory returned HTTP {page.status}; stopping"
                page = None
        if page is not None and page.status == 200:
            inline, vdps = dealer_dot_com.parse_listing_page(
                page,
                source_id=source_id,
                source_name=dealer_name,
                region=region,
                city=city,
            )
            log.info(
                "[%s] static listing page 1: %d inline listings, %d VDP candidates",
                dealer_slug, len(inline), len(vdps),
            )
            canonical_listings.extend(inline)

            # Walk additional pages via static fetch when page 1 yielded
            # inline JSON-LD (cheap path). If page 1 yielded nothing, the
            # Selenium fallback below handles pagination itself.
            if inline:
                seen_keys = {_dedup_key(l) for l in inline}
                for next_url in paginated_urls[1:]:
                    time.sleep(rate_limit_seconds)
                    np = dealer_dot_com.fetch(next_url)
                    pages_fetched += 1
                    if np.error or np.status >= 400:
                        http_error_count += 1
                        log.warning(
                            "[%s] paginated page %s -> %s; stopping walk",
                            dealer_slug, next_url, np.status or np.error,
                        )
                        break
                    inline_n, vdps_n = dealer_dot_com.parse_listing_page(
                        np,
                        source_id=source_id,
                        source_name=dealer_name,
                        region=region,
                        city=city,
                    )
                    new_inline = [
                        l for l in inline_n if _dedup_key(l) not in seen_keys
                    ]
                    log.info(
                        "[%s] static listing page %s: %d new inline (of %d), %d VDPs",
                        dealer_slug, next_url, len(new_inline), len(inline_n), len(vdps_n),
                    )
                    if not new_inline and not vdps_n:
                        break  # page exhausted
                    seen_keys.update(_dedup_key(l) for l in new_inline)
                    canonical_listings.extend(new_inline)
                    vdps.extend(vdps_n)

            # 6b. Selenium fallback when the static page yielded nothing.
            #     Re-fetch with a real browser so JS-rendered inventory
            #     hydrates, then re-run the same parser. Walks pagination
            #     URLs in order; stops on the first page with no new VINs.
            if (
                allow_selenium
                and not canonical_listings
                and not vdps
                and not result.skipped_reason
            ):
                log.info(
                    "[%s] no inline listings or VDPs in static HTML; "
                    "falling back to Selenium-rendered fetch (paginated)",
                    dealer_slug,
                )
                try:
                    with dealer_dot_com.selenium_session() as driver:
                        seen_keys: set[str] = set()
                        vdps = []
                        for page_url in paginated_urls:
                            rendered = dealer_dot_com.fetch_rendered(driver, page_url)
                            pages_fetched += 1
                            if rendered.error or rendered.status >= 400:
                                log.warning(
                                    "[%s] selenium fetch error %s: %s",
                                    dealer_slug, page_url, rendered.error or rendered.status,
                                )
                                http_error_count += 1
                                break
                            inline_p, vdps_p = dealer_dot_com.parse_listing_page(
                                rendered,
                                source_id=source_id,
                                source_name=dealer_name,
                                region=region,
                                city=city,
                            )
                            new_inline = [
                                l for l in inline_p if _dedup_key(l) not in seen_keys
                            ]
                            log.info(
                                "[%s] selenium %s: +%d inline (of %d), +%d VDPs",
                                dealer_slug, page_url,
                                len(new_inline), len(inline_p), len(vdps_p),
                            )
                            if not new_inline and not vdps_p:
                                break  # page exhausted → done
                            seen_keys.update(_dedup_key(l) for l in new_inline)
                            canonical_listings.extend(new_inline)
                            vdps.extend(vdps_p)
                            time.sleep(rate_limit_seconds)

                        # Walk VDPs (if any) using Selenium too, since
                        # detail pages also tend to be JS-rendered. This
                        # runs AFTER the pagination loop — `vdps` is the
                        # union of every page's VDP candidates, deduped
                        # below.
                        seen_vdps: set[str] = set()
                        for vdp_url in vdps:
                            if vdp_url in seen_vdps:
                                continue
                            seen_vdps.add(vdp_url)
                            if len(canonical_listings) >= max_listings:
                                break
                            time.sleep(rate_limit_seconds)
                            vdp_page = dealer_dot_com.fetch_rendered(
                                driver, vdp_url, wait_for_jsonld_seconds=4.0
                            )
                            pages_fetched += 1
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
                except RuntimeError as exc:
                    log.warning("[%s] selenium not available: %s", dealer_slug, exc)
            else:
                # 7. Walk VDPs via static fetch (cheaper) when we found them.
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
