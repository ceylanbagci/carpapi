"""REST API views — read-only list endpoints + a small stats endpoint
for the dashboard. Cars / Makes / Models are derived aggregations over
the ``listings`` table; the underlying schema does not have separate
tables for them.
"""
from __future__ import annotations

from django.db.models import Count, F, Max, Min
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


class DealerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Dealer.objects.all()
    serializer_class = DealerSerializer
    pagination_class = StandardPagination
    search_fields = ["name", "slug", "city", "region", "cms"]
    ordering_fields = ["name", "city", "region", "enrolled_at", "last_scraped_at"]
    lookup_field = "slug"


class ListingViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Listing.objects.all()
    serializer_class = ListingSerializer
    pagination_class = StandardPagination
    search_fields = ["title", "make", "model", "trim", "vin", "city", "region"]
    ordering_fields = ["scraped_at", "price_amount", "year", "mileage"]


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


@api_view(["GET"])
def cars(request):
    """Distinct (year, make, model, trim) groupings with listing counts."""
    qs = (
        Listing.objects.exclude(make__isnull=True)
        .exclude(model__isnull=True)
        .values("make", "model", "year", "trim")
        .annotate(
            count=Count("id"),
            min_price=Min("price_amount"),
            max_price=Max("price_amount"),
        )
        .order_by("make", "model", "-year")
    )
    paginator = StandardPagination()
    page = paginator.paginate_queryset(list(qs), request)
    return paginator.get_paginated_response(page)


@api_view(["GET"])
def makes(request):
    """Distinct makes with dealer + listing counts."""
    listing_counts = dict(
        Listing.objects.exclude(make__isnull=True)
        .values_list("make")
        .annotate(c=Count("id"))
    )
    dealer_make_counts: dict[str, int] = {}
    for d in Dealer.objects.exclude(makes_carried__isnull=True).values_list(
        "makes_carried", flat=True
    ):
        for m in d or []:
            dealer_make_counts[m] = dealer_make_counts.get(m, 0) + 1

    rows = []
    for m in sorted(set(listing_counts) | set(dealer_make_counts)):
        rows.append(
            {
                "make": m,
                "listing_count": listing_counts.get(m, 0),
                "dealer_count": dealer_make_counts.get(m, 0),
            }
        )
    rows.sort(key=lambda r: (-r["listing_count"], -r["dealer_count"], r["make"]))
    paginator = StandardPagination()
    page = paginator.paginate_queryset(rows, request)
    return paginator.get_paginated_response(page)


@api_view(["GET"])
def models_list(request):
    """Distinct (make, model) pairs with listing counts."""
    qs = (
        Listing.objects.exclude(make__isnull=True)
        .exclude(model__isnull=True)
        .values("make", "model")
        .annotate(count=Count("id"))
        .order_by("make", "model")
    )
    paginator = StandardPagination()
    page = paginator.paginate_queryset(list(qs), request)
    return paginator.get_paginated_response(page)
