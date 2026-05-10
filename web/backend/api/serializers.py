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
        ]
