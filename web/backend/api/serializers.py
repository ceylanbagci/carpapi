from rest_framework import serializers

from .models import Dealer, Listing


class ListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = [
            "id",
            "title",
            "year",
            "make",
            "model",
            "trim",
            "body_style",
            "mileage",
            "mileage_unit",
            "price_amount",
            "currency",
            "vin",
            "city",
            "region",
            "source_id",
            "source_name",
            "listing_url",
            "scraped_at",
            "price_refreshed_at",
            "maker_url",
            "maker_specs",
            "window_sticker_url",
            "window_sticker",
            "maker_enriched_at",
            "maker_enrich_status",
        ]


class DealerSerializer(serializers.ModelSerializer):
    # Annotated by DealerViewSet.get_queryset (Subquery on Listing.source_id).
    # Coalesce to 0 here so the wire shape is always an int, never null.
    cars_count = serializers.SerializerMethodField()

    class Meta:
        model = Dealer
        fields = [
            "id",
            "slug",
            "name",
            "homepage_url",
            "inventory_url",
            "cms",
            "city",
            "region",
            "postal_code",
            "makes_carried",
            "status",
            "last_scraped_at",
            "enrolled_at",
            "cars_count",
        ]

    def get_cars_count(self, obj):
        return getattr(obj, "cars_count", 0) or 0
