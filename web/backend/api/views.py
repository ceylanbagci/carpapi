"""REST API views — read-only list endpoints + a small stats endpoint
for the dashboard. Cars / Makes / Models are derived aggregations over
the ``listings`` table; the underlying schema does not have separate
tables for them.

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

from django.db.models import Count, Max, Min, Q
from rest_framework import viewsets
from rest_framework.decorators import api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import Dealer, Listing
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
    ]
    lookup_field = "slug"

    def get_queryset(self):
        qs = super().get_queryset()
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
    """Distinct makes with dealer + listing counts."""
    listing_qs = Listing.objects.exclude(make__isnull=True)
    listing_qs = _apply_listing_filters(listing_qs, request.query_params)
    listing_counts = dict(listing_qs.values_list("make").annotate(c=Count("id")))

    make_filter = (request.query_params.get("make") or "").strip().lower()

    dealer_make_counts: dict[str, int] = {}
    for d in Dealer.objects.exclude(makes_carried__isnull=True).values_list(
        "makes_carried", flat=True
    ):
        for m in d or []:
            dealer_make_counts[m] = dealer_make_counts.get(m, 0) + 1

    search = (request.query_params.get("search") or "").strip().lower()

    rows = []
    for m in sorted(set(listing_counts) | set(dealer_make_counts)):
        if make_filter and m.lower() != make_filter:
            continue
        if search and search not in m.lower():
            continue
        rows.append(
            {
                "make": m,
                "listing_count": listing_counts.get(m, 0),
                "dealer_count": dealer_make_counts.get(m, 0),
            }
        )

    ordering = (request.query_params.get("ordering") or "").strip()
    if ordering:
        desc = ordering.startswith("-")
        field = ordering.lstrip("-")
        if field in {"make", "listing_count", "dealer_count"}:
            rows.sort(key=lambda r: r[field], reverse=desc)
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
