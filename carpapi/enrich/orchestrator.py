"""Cold-loop orchestrator.

For one listing (keyed by VIN):

  1. If ``maker_specs`` is already populated, do nothing — idempotency rule.
  2. Look up the maker adapter from :mod:`carpapi.makers`.
     If absent, mark ``unsupported``.
  3. Call ``adapter.lookup(...)``.
     - ``MakerUnsupported`` → mark row ``unsupported`` and return.
     - ``MakerLoginRequired`` → mark ``login_required`` and return.
     - any other exception → mark ``failed`` and record the error.
  4. If a sticker URL came back AND the row's ``window_sticker`` is
     still NULL, download + parse the PDF.
  5. Persist everything in one UPDATE.
"""
from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass

from ..makers import (
    MakerLoginRequired,
    MakerLookup,
    MakerUnsupported,
    get_adapter,
)
from . import db
from .window_sticker import fetch_pdf, parse_pdf_bytes

log = logging.getLogger(__name__)


@dataclass
class EnrichResult:
    vin: str
    status: str  # 'enriched' | 'skipped' | 'unsupported' | 'login_required' | 'failed'
    detail: str = ""
    maker_url: str | None = None
    sticker_url: str | None = None
    sticker_msrp: int | None = None
    has_specs: bool = False


def enrich_one(listing: db.ListingRow, *, force_sticker: bool = False) -> EnrichResult:
    """Run cold loop for one listing. Caller persists; this returns
    the EnrichResult and the side effects via the cursor.

    Persistence is handled inside this function via the connection
    context manager so each VIN is its own transaction.
    """
    vin = listing.vin

    # Idempotency: skip rows already enriched, unless force is in play.
    if listing.maker_specs is not None and not force_sticker:
        return EnrichResult(vin=vin, status="skipped", detail="already enriched")

    adapter = get_adapter(listing.make)
    if adapter is None or not adapter.supported:
        with db.connect() as conn, conn.cursor() as cur:
            db.save_status_only(cur, listing.id, "unsupported",
                                error=f"no adapter for make={listing.make!r}")
            conn.commit()
        return EnrichResult(vin=vin, status="unsupported",
                            detail=f"no adapter for {listing.make}")

    try:
        lookup: MakerLookup = adapter.lookup(
            vin=vin,
            make=listing.make or "",
            model=listing.model,
            year=listing.year,
            trim=listing.trim,
        )
    except MakerUnsupported as e:
        with db.connect() as conn, conn.cursor() as cur:
            db.save_status_only(cur, listing.id, "unsupported", error=str(e))
            conn.commit()
        return EnrichResult(vin=vin, status="unsupported", detail=str(e))
    except MakerLoginRequired as e:
        with db.connect() as conn, conn.cursor() as cur:
            db.save_status_only(cur, listing.id, "login_required", error=str(e))
            conn.commit()
        return EnrichResult(vin=vin, status="login_required", detail=str(e))
    except Exception as e:
        log.warning("enrich %s: adapter failed: %s\n%s", vin, e, traceback.format_exc())
        with db.connect() as conn, conn.cursor() as cur:
            db.save_status_only(cur, listing.id, "failed", error=f"{type(e).__name__}: {e}")
            conn.commit()
        return EnrichResult(vin=vin, status="failed", detail=str(e))

    # Sticker — only if we found a URL and the row doesn't have one yet
    sticker_data = None
    sticker_url = lookup.sticker_url
    if sticker_url and (listing.window_sticker is None or force_sticker):
        try:
            pdf = fetch_pdf(sticker_url)
            sticker_data = parse_pdf_bytes(pdf, source_url=sticker_url)
        except Exception as e:
            log.warning("enrich %s: sticker parse failed: %s", vin, e)
            sticker_data = {
                "source_url": sticker_url,
                "parser_error": str(e),
            }

    with db.connect() as conn, conn.cursor() as cur:
        db.save_enrichment(
            cur,
            listing.id,
            maker_url=lookup.maker_url,
            maker_specs=lookup.specs,
            window_sticker_url=sticker_url,
            window_sticker=sticker_data,
            status="enriched",
            error=None,
        )
        conn.commit()

    return EnrichResult(
        vin=vin,
        status="enriched",
        detail=f"specs={len(lookup.specs)} keys",
        maker_url=lookup.maker_url,
        sticker_url=sticker_url,
        sticker_msrp=(sticker_data or {}).get("msrp") if sticker_data else None,
        has_specs=bool(lookup.specs),
    )


def parse_sticker_only(listing: db.ListingRow) -> EnrichResult:
    """Re-parse the existing window_sticker_url without re-running the
    maker-site lookup. Useful after tightening regexes."""
    vin = listing.vin
    if not listing.window_sticker_url:
        return EnrichResult(vin=vin, status="failed",
                            detail="listing has no window_sticker_url")
    try:
        pdf = fetch_pdf(listing.window_sticker_url)
        sticker = parse_pdf_bytes(pdf, source_url=listing.window_sticker_url)
    except Exception as e:
        return EnrichResult(vin=vin, status="failed", detail=str(e))

    with db.connect() as conn, conn.cursor() as cur:
        db.save_sticker_only(
            cur,
            listing.id,
            window_sticker_url=listing.window_sticker_url,
            window_sticker=sticker,
        )
        conn.commit()
    return EnrichResult(
        vin=vin, status="enriched",
        detail=f"sticker re-parsed (MSRP={sticker.get('msrp')})",
        sticker_url=listing.window_sticker_url,
        sticker_msrp=sticker.get("msrp"),
    )
