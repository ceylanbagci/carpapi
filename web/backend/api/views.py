"""REST API views — read-only list endpoints + a small stats endpoint
for the dashboard, plus a RAG-backed ``/api/chat/`` endpoint that
proxies user questions through ``carpapi.rag.answer``.

All list endpoints accept the query params:

  ?search=<text>          substring match across all relevant text fields
  ?ordering=<field>       sort ascending; prefix with '-' for desc
  ?make=<exact>           filter by make (case-insensitive equality)
  ?model=<exact>          filter by model (case-insensitive equality)
  ?price_min=<number>     filter price_amount >= n
  ?price_max=<number>     filter price_amount <= n
  ?year_min=<int>         filter year >= n
  ?year_max=<int>         filter year <= n
  ?status=<active|paused|blocked>   dealers only
"""
from __future__ import annotations

from django.db.models import (
    Count, IntegerField, Max, Min, OuterRef, Q, Subquery, Value,
)
from django.db.models.functions import Coalesce
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import Dealer, Listing, Make
from .serializers import DealerSerializer, ListingSerializer


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


def _coerce(value, cast):
    try:
        return cast(value)
    except (TypeError, ValueError):
        return None


def _apply_listing_filters(qs, params):
    if (m := params.get("make")):
        qs = qs.filter(make__iexact=m)
    if (m := params.get("model")):
        qs = qs.filter(model__iexact=m)
    if (s := params.get("source_id")):
        # Drives the "click the Listings count on /dealers" link.
        # listings.source_id is the dealer slug.
        qs = qs.filter(source_id__iexact=s)
    if (v := _coerce(params.get("price_min"), float)) is not None:
        qs = qs.filter(price_amount__gte=v)
    if (v := _coerce(params.get("price_max"), float)) is not None:
        qs = qs.filter(price_amount__lte=v)
    if (v := _coerce(params.get("year_min"), int)) is not None:
        qs = qs.filter(year__gte=v)
    if (v := _coerce(params.get("year_max"), int)) is not None:
        qs = qs.filter(year__lte=v)
    return qs


def _apply_search(qs, params, fields):
    """Manual substring search across the given text fields (OR)."""
    text = (params.get("search") or "").strip()
    if not text:
        return qs
    q = Q()
    for f in fields:
        q |= Q(**{f"{f}__icontains": text})
    return qs.filter(q)


class DealerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Dealer.objects.all()
    serializer_class = DealerSerializer
    pagination_class = StandardPagination
    search_fields = ["name", "slug", "city", "region", "cms", "postal_code", "notes"]
    ordering_fields = [
        "name",
        "slug",
        "city",
        "region",
        "cms",
        "status",
        "postal_code",
        "enrolled_at",
        "last_scraped_at",
        # Annotation added in get_queryset — Postgres sorts numerically
        # via ORDER BY cars_count DESC. SPA renders this as the
        # "Listings" pill in the /dealers table.
        "cars_count",
    ]
    lookup_field = "slug"

    def get_queryset(self):
        # Listings join to dealers via `Listing.source_id == Dealer.slug`
        # (there's no Django ForeignKey because the listings table is
        # SQLAlchemy-managed). Correlated subquery so the count is a
        # single integer per row — DRF's OrderingFilter then sorts
        # numerically via Postgres ORDER BY, not string-collation. The
        # Coalesce wraps NULL (dealers with zero listings) to 0 so
        # `-cars_count` puts empty dealers last.
        cars_sq = (
            Listing.objects.filter(source_id=OuterRef("slug"))
            .order_by()
            .values("source_id")
            .annotate(c=Count("*"))
            .values("c")
        )
        qs = super().get_queryset().annotate(
            cars_count=Coalesce(
                Subquery(cars_sq, output_field=IntegerField()),
                Value(0),
            )
        )
        params = self.request.query_params
        if (make := params.get("make")):
            qs = qs.filter(makes_carried__contains=[make])
        if (status := params.get("status")):
            qs = qs.filter(status=status)
        return qs


class ListingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Listing.objects.all()
    serializer_class = ListingSerializer
    pagination_class = StandardPagination
    search_fields = [
        "title",
        "description",
        "make",
        "model",
        "trim",
        "vin",
        "city",
        "region",
        "source_id",
        "source_name",
        "external_id",
        "seller_name",
    ]
    ordering_fields = [
        "title",
        "make",
        "model",
        "trim",
        "year",
        "price_amount",
        "mileage",
        "city",
        "region",
        "scraped_at",
        "source_id",
    ]

    def get_queryset(self):
        return _apply_listing_filters(super().get_queryset(), self.request.query_params)


@api_view(["GET"])
def healthz(_request):
    """Liveness probe — returns 200 without touching DB or Bedrock.

    Use this as the App Runner / ECS / k8s health-check path. Use
    ``/api/stats/`` only as a readiness probe, since it requires DB
    connectivity.
    """
    return Response({"ok": True, "service": "carpapi-api"})


@api_view(["GET"])
def stats(_request):
    listings_qs = Listing.objects.all()
    return Response(
        {
            "listings": listings_qs.count(),
            "dealers": Dealer.objects.count(),
            "cars": (
                listings_qs.exclude(make__isnull=True)
                .exclude(model__isnull=True)
                .values("make", "model", "year", "trim")
                .distinct()
                .count()
            ),
            "makes": (
                listings_qs.exclude(make__isnull=True)
                .values("make")
                .distinct()
                .count()
            ),
            "models": (
                listings_qs.exclude(make__isnull=True)
                .exclude(model__isnull=True)
                .values("make", "model")
                .distinct()
                .count()
            ),
            "active_dealers": Dealer.objects.filter(status="active").count(),
        }
    )


CAR_ORDERING = {
    "make", "model", "year", "trim",
    "count", "min_price", "max_price",
}


@api_view(["GET"])
def cars(request):
    """Distinct (year, make, model, trim) groupings with listing counts."""
    qs = Listing.objects.exclude(make__isnull=True).exclude(model__isnull=True)
    qs = _apply_listing_filters(qs, request.query_params)
    qs = _apply_search(qs, request.query_params, ["make", "model", "trim", "title", "vin"])

    qs = (
        qs.values("make", "model", "year", "trim")
        .annotate(
            count=Count("id"),
            min_price=Min("price_amount"),
            max_price=Max("price_amount"),
        )
    )

    ordering = (request.query_params.get("ordering") or "").strip()
    field = ordering.lstrip("-")
    if field in CAR_ORDERING:
        qs = qs.order_by(ordering)
    else:
        qs = qs.order_by("make", "model", "-year")

    paginator = StandardPagination()
    page = paginator.paginate_queryset(list(qs), request)
    return paginator.get_paginated_response(page)


@api_view(["GET"])
def makes(request):
    """Distinct makes with dealer + listing counts.

    Joins the persisted ``public.makes`` table (homepage_url, logo_url)
    with on-the-fly counts derived from listings + dealers.makes_carried.
    """
    listing_qs = Listing.objects.exclude(make__isnull=True)
    listing_qs = _apply_listing_filters(listing_qs, request.query_params)

    make_filter = (request.query_params.get("make") or "").strip().lower()
    search = (request.query_params.get("search") or "").strip().lower()

    # Case-insensitive count maps so "Ford" / "ford" / "FORD" merge.
    listing_counts: dict[str, int] = {}
    for raw, c in listing_qs.values_list("make").annotate(c=Count("id")):
        if not raw:
            continue
        listing_counts[raw.lower()] = listing_counts.get(raw.lower(), 0) + c

    dealer_make_counts: dict[str, int] = {}
    for d in Dealer.objects.exclude(makes_carried__isnull=True).values_list(
        "makes_carried", flat=True
    ):
        for m in d or []:
            if not m:
                continue
            dealer_make_counts[m.lower()] = dealer_make_counts.get(m.lower(), 0) + 1

    persisted = {m.name.lower(): m for m in Make.objects.all()}

    all_keys = set(listing_counts) | set(dealer_make_counts) | set(persisted)

    rows = []
    for key in sorted(all_keys):
        if make_filter and key != make_filter:
            continue
        if search and search not in key:
            continue
        m_row = persisted.get(key)
        display_name = m_row.name if m_row else key.title()
        rows.append(
            {
                "make": display_name,
                "slug": m_row.slug if m_row else None,
                "homepage_url": m_row.homepage_url if m_row else None,
                "logo_url": m_row.logo_url if m_row else None,
                "listing_count": listing_counts.get(key, 0),
                "dealer_count": dealer_make_counts.get(key, 0),
            }
        )

    ordering = (request.query_params.get("ordering") or "").strip()
    if ordering:
        desc = ordering.startswith("-")
        field = ordering.lstrip("-")
        if field in {"make", "listing_count", "dealer_count"}:
            rows.sort(key=lambda r: (r[field] is None, r[field]), reverse=desc)
    else:
        rows.sort(key=lambda r: (-r["listing_count"], -r["dealer_count"], r["make"]))

    paginator = StandardPagination()
    page = paginator.paginate_queryset(rows, request)
    return paginator.get_paginated_response(page)


MODEL_ORDERING = {"make", "model", "count"}


@api_view(["GET"])
def models_list(request):
    """Distinct (make, model) pairs with listing counts."""
    qs = Listing.objects.exclude(make__isnull=True).exclude(model__isnull=True)
    qs = _apply_listing_filters(qs, request.query_params)
    qs = _apply_search(qs, request.query_params, ["make", "model", "trim"])

    qs = qs.values("make", "model").annotate(count=Count("id"))

    ordering = (request.query_params.get("ordering") or "").strip()
    field = ordering.lstrip("-")
    if field in MODEL_ORDERING:
        qs = qs.order_by(ordering)
    else:
        qs = qs.order_by("make", "model")

    paginator = StandardPagination()
    page = paginator.paginate_queryset(list(qs), request)
    return paginator.get_paginated_response(page)


# --------------------------------------------------------------------------- #
# Chat / RAG endpoint
# --------------------------------------------------------------------------- #
#
# POST /api/chat/
#   body: { "message": "Find me a Toyota Camry under $25k" }
#   response: {
#     "answer":  "...prose with [listing-id] citations...",
#     "listings": [{ id, title, make, model, year, price, url, ... }, ...],
#     "rationale": "Filtering by Toyota Camry; price ≤ $25,000",
#     "car_query": { make: "Toyota", model: "Camry", price_max: 25000, ... },
#     "plan_source": "llm" | "regex-fallback",
#     "retrieval_path": "structured" | "vector",
#     "cited_listing_ids": [...],
#     "diagnostics": { hits, cache, hallucinated_ids_dropped }
#   }
#
# Wired to ``carpapi.rag.answer.answer``. That module owns the TokenCache
# and the Bedrock calls; this view is a thin HTTP shim.

import logging

_chat_log = logging.getLogger("api.chat")
_RAG_CACHE = None  # populated lazily so import-time doesn't open Bedrock


def _rag_cache():
    """Process-local TokenCache so repeated questions hit the cache."""
    global _RAG_CACHE
    if _RAG_CACHE is None:
        from carpapi.cache.bedrock_client import bedrock_chat
        from carpapi.cache.token_cache import SQLiteBackend, TokenCache
        _RAG_CACHE = TokenCache(
            backend=SQLiteBackend("./data/token_cache.sqlite"),
            llm_call=bedrock_chat(default_model="haiku", default_max_tokens=512),
        )
    return _RAG_CACHE


@api_view(["POST"])
def chat(request):
    """RAG-backed chat: plan -> retrieve -> synthesize.

    Auth: JWT Bearer. Real user accounts via accounts.User; the SPA
    sends `Authorization: Bearer <access-token>` on every request.
    Unauthenticated requests get DRF's 401 automatically.

    Legacy passphrase path: if `CARPAPI_API_KEY` is set in settings,
    we also accept `X-CarPapi-Auth: <key>` from clients that haven't
    migrated to JWT yet. Empty key disables the legacy path entirely.
    """
    from django.conf import settings
    from rest_framework import status

    # Legacy passphrase fallback (only when no JWT was provided AND
    # the env-var path is enabled). Lets old SPA bundles still work
    # during the rollout window.
    if not request.user.is_authenticated:
        required_key = getattr(settings, "CARPAPI_API_KEY", "") or ""
        if required_key:
            sent = (request.headers.get("X-CarPapi-Auth") or "").strip()
            if sent != required_key:
                return Response(
                    {"error": "unauthorized"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
        # else: no JWT and no legacy key configured → fall through. Local
        # dev mode (DJANGO_DEBUG=true) skips the gate.
        elif not getattr(settings, "DEBUG", False):
            return Response(
                {"error": "unauthorized", "detail": "sign in to use the chat"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

    message = (request.data.get("message") or "").strip()
    if not message:
        return Response(
            {"error": "missing required field 'message'"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(message) > 2000:
        return Response(
            {"error": "message too long (max 2000 chars)"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    from carpapi.cache.pii_guard import PIIInPromptError
    from carpapi.rag.answer import answer as rag_answer

    try:
        result = rag_answer(message, cache=_rag_cache(), limit=8)
    except PIIInPromptError as exc:
        return Response(
            {"error": "pii_in_prompt", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as exc:  # noqa: BLE001
        _chat_log.exception("chat failed: %s", exc)
        return Response(
            {"error": "chat_pipeline_failure", "detail": type(exc).__name__},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        "answer": result.answer,
        "listings": result.listings,
        "rationale": result.rationale,
        "car_query": result.car_query,
        "plan_source": result.plan_source,
        "retrieval_path": result.retrieval_path,
        "cited_listing_ids": result.cited_listing_ids,
        "diagnostics": result.diagnostics,
    })
