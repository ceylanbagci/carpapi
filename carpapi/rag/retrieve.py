from __future__ import annotations

"""Vector + structured retrieval over public.listings.

Two helpers:

  vector_search(query_text, limit, filters) — embeds the message via
      Titan v2, runs pgvector cosine similarity, returns top-K listings
      enriched with similarity score. Optional structured filters
      (make/model/year/price) get applied as a WHERE clause first so
      we only rank candidates that match the hard constraints.

  structured_search(filters, limit) — pure structured retrieval; same
      shape but no vector ranking, ORDER BY price ASC.

Both return ``list[ListingHit]`` — a typed dict shaped for the synthesis
layer downstream.
"""

import logging
import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

import psycopg

from carpapi.cache.bedrock_client import bedrock_embed

log = logging.getLogger("carpapi.rag.retrieve")

DEFAULT_LIMIT = 10


def _dsn() -> str:
    return (
        f"host={os.environ.get('CARPAPI_DB_HOST', 'localhost')} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5433')} "
        f"dbname={os.environ.get('CARPAPI_DB_NAME', 'carpapi')} "
        f"user={os.environ.get('CARPAPI_DB_USER', 'carpapi')} "
        f"password={os.environ.get('CARPAPI_DB_PASSWORD', 'carpapi')}"
    )


@dataclass
class ListingHit:
    id: str
    vin: Optional[str]
    title: str
    make: Optional[str]
    model: Optional[str]
    year: Optional[int]
    trim: Optional[str]
    body_style: Optional[str]
    mileage: Optional[float]
    price_amount: Optional[float]
    currency: Optional[str]
    region: Optional[str]
    city: Optional[str]
    listing_url: Optional[str]
    car_url: Optional[str]
    dealer_id: Optional[str]
    dealer_name: Optional[str]
    seller_type: Optional[str]
    # Image pipeline (carpapi/images/). Both are optional CDN URLs;
    # the SPA prefers `image_url` (JPEG thumb) and falls back to the
    # `image_svg_url` silhouette, then to a generic icon.
    image_url: Optional[str] = None
    image_svg_url: Optional[str] = None
    similarity: Optional[float] = None   # vector path only
    rank_reason: Optional[str] = None    # filled by the caller

    def to_card(self) -> dict[str, Any]:
        """Compact dict for chat-response payloads."""
        return {
            "id": self.id,
            "vin": self.vin,
            "title": self.title,
            "make": self.make,
            "model": self.model,
            "year": self.year,
            "trim": self.trim,
            "body_style": self.body_style,
            "mileage": int(self.mileage) if self.mileage is not None else None,
            "price": int(self.price_amount) if self.price_amount is not None else None,
            "currency": self.currency or "USD",
            "city": self.city,
            "region": self.region,
            "url": self.car_url or self.listing_url,
            "dealer": self.dealer_name,
            "image_url": self.image_url,
            "image_svg_url": self.image_svg_url,
            "similarity": (
                round(float(self.similarity), 4) if self.similarity is not None else None
            ),
        }


# --------------------------------------------------------------------------- #
# Filters
# --------------------------------------------------------------------------- #


@dataclass
class Filters:
    """Hard-constraint filters. Matches CarQuery schema shape."""

    make: Optional[str] = None
    model: Optional[str] = None
    body_style: Optional[str] = None
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    mileage_max: Optional[float] = None
    region: Optional[str] = None
    require_price: bool = False    # exclude rows with NULL/0 price
    require_url: bool = False      # exclude rows whose url is just the inventory page

    def where_clause(self) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if self.make:
            clauses.append("l.make ILIKE %s")
            params.append(self.make)
        if self.model:
            clauses.append("l.model ILIKE %s")
            params.append(self.model)
        if self.body_style:
            clauses.append("l.body_style ILIKE %s")
            params.append(self.body_style)
        if self.year_min is not None:
            clauses.append("l.year >= %s")
            params.append(int(self.year_min))
        if self.year_max is not None:
            clauses.append("l.year <= %s")
            params.append(int(self.year_max))
        if self.price_min is not None:
            clauses.append("l.price_amount >= %s")
            params.append(float(self.price_min))
        if self.price_max is not None:
            clauses.append("l.price_amount <= %s")
            params.append(float(self.price_max))
        if self.mileage_max is not None:
            clauses.append("l.mileage <= %s")
            params.append(float(self.mileage_max))
        if self.region:
            clauses.append("l.region ILIKE %s")
            params.append(self.region)
        if self.require_price:
            clauses.append("l.price_amount > 0")
        if self.require_url:
            # Real VDP URL — not the dealer's inventory landing page.
            clauses.append("l.car_url ~ '\\.html?(\\?|$)'")
            clauses.append("l.car_url !~ '/(new|used)-(inventory|vehicles)'")
        return (" AND ".join(clauses) or "TRUE", params)


_BASE_SELECT = """
    SELECT l.id::text, l.vin, l.title, l.make, l.model, l.year, l.trim,
           l.body_style, l.mileage, l.price_amount, l.currency,
           l.region, l.city,
           l.listing_url, l.car_url,
           l.dealer_id::text, d.name AS dealer_name, l.seller_type,
           l.image_url, l.image_svg_url
"""


def _row_to_hit(row: tuple, with_similarity: bool = False) -> ListingHit:
    # SELECT order must match _BASE_SELECT (+ optional similarity column)
    base = list(row)
    sim = base.pop() if with_similarity else None
    (
        rid, vin, title, make, model, year, trim, body_style, mileage,
        price_amount, currency, region, city, listing_url, car_url,
        dealer_id, dealer_name, seller_type, image_url, image_svg_url,
    ) = base
    return ListingHit(
        id=rid, vin=vin, title=title or "",
        make=make, model=model, year=year, trim=trim,
        body_style=body_style,
        mileage=float(mileage) if mileage is not None else None,
        price_amount=float(price_amount) if price_amount is not None else None,
        currency=currency, region=region, city=city,
        listing_url=listing_url, car_url=car_url,
        dealer_id=dealer_id, dealer_name=dealer_name,
        seller_type=seller_type,
        image_url=image_url, image_svg_url=image_svg_url,
        similarity=float(sim) if sim is not None else None,
    )


# --------------------------------------------------------------------------- #
# Searches
# --------------------------------------------------------------------------- #


def _to_vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


def vector_search(
    query_text: str,
    *,
    limit: int = DEFAULT_LIMIT,
    filters: Optional[Filters] = None,
) -> list[ListingHit]:
    """Embed query, run cosine similarity, optionally apply hard filters first."""
    if not query_text or not query_text.strip():
        return []
    flt = filters or Filters(require_price=True)
    qvec = bedrock_embed(query_text)

    where, params = flt.where_clause()
    sql = f"""
        {_BASE_SELECT},
               (1 - (l.embedding <=> %s::vector)) AS similarity
        FROM public.listings l
        LEFT JOIN public.dealers d ON l.dealer_id = d.id
        WHERE l.embedding IS NOT NULL AND {where}
        ORDER BY l.embedding <=> %s::vector
        LIMIT %s
    """
    qlit = _to_vector_literal(qvec)
    full_params = [qlit, *params, qlit, int(limit)]

    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, full_params)
            rows = cur.fetchall()
    return [_row_to_hit(r, with_similarity=True) for r in rows]


def structured_search(
    *,
    filters: Filters,
    limit: int = DEFAULT_LIMIT,
    sort_by: str = "price_asc",
) -> list[ListingHit]:
    """Pure SQL retrieval with the same shape, no embedding."""
    order = {
        "price_asc":  "l.price_amount ASC NULLS LAST, l.scraped_at DESC",
        "price_desc": "l.price_amount DESC NULLS LAST, l.scraped_at DESC",
        "mileage_asc": "l.mileage ASC NULLS LAST",
        "newest":     "l.year DESC NULLS LAST, l.scraped_at DESC",
    }.get(sort_by, "l.price_amount ASC NULLS LAST")

    where, params = filters.where_clause()
    sql = f"""
        {_BASE_SELECT}
        FROM public.listings l
        LEFT JOIN public.dealers d ON l.dealer_id = d.id
        WHERE {where}
        ORDER BY {order}
        LIMIT %s
    """
    params.append(int(limit))
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [_row_to_hit(r, with_similarity=False) for r in rows]


def hybrid_search(
    query_text: str,
    *,
    filters: Optional[Filters] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[ListingHit]:
    """Combine structured filters with vector ranking.

    If hard filters narrow the candidate set down to ``limit`` or fewer
    rows, we skip the vector pass entirely (no Bedrock call). Otherwise
    we vector-search within the filtered set.
    """
    flt = filters or Filters(require_price=True)
    structured = structured_search(filters=flt, limit=limit, sort_by="price_asc")
    if len(structured) <= limit and (
        flt.make or flt.model or flt.body_style
        or flt.year_min or flt.year_max
        or flt.price_min or flt.price_max
    ):
        for h in structured:
            h.rank_reason = "structured"
        return structured
    hits = vector_search(query_text, limit=limit, filters=flt)
    for h in hits:
        h.rank_reason = "vector"
    return hits
