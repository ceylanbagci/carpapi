"""Read-only Django ORM models bound to the existing carpapi Postgres tables.

Schema is owned by carpapi/db/schema.sql + carapi_pipeline.models — these
classes set ``managed = False`` so Django never tries to create or migrate
the tables. Field names mirror the live columns.
"""
from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import models


class Listing(models.Model):
    id = models.UUIDField(primary_key=True)
    dedupe_key = models.CharField(max_length=512)

    source_id = models.CharField(max_length=128)
    source_name = models.CharField(max_length=256)
    external_id = models.CharField(max_length=256)
    listing_url = models.TextField()
    title = models.TextField()
    description = models.TextField(null=True, blank=True)

    make = models.CharField(max_length=128, null=True, blank=True)
    model = models.CharField(max_length=128, null=True, blank=True)
    trim = models.CharField(max_length=128, null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    body_style = models.CharField(max_length=64, null=True, blank=True)

    vin = models.CharField(max_length=32, null=True, blank=True)
    mileage = models.FloatField(null=True, blank=True)
    mileage_unit = models.CharField(max_length=8, default="unknown")

    price_amount = models.FloatField(null=True, blank=True)
    currency = models.CharField(max_length=3)

    monthly_payment_estimate = models.FloatField(null=True, blank=True)

    seller_name = models.CharField(max_length=256, null=True, blank=True)
    seller_type = models.CharField(max_length=32, null=True, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    region = models.CharField(max_length=64, null=True, blank=True)
    city = models.CharField(max_length=128, null=True, blank=True)
    postal_code = models.CharField(max_length=32, null=True, blank=True)

    listing_posted_at = models.DateTimeField(null=True, blank=True)
    listing_updated_at = models.DateTimeField(null=True, blank=True)
    scraped_at = models.DateTimeField()

    raw_checksum = models.CharField(max_length=128, null=True, blank=True)
    features = models.JSONField(null=True, blank=True)
    images = models.JSONField(null=True, blank=True)
    raw_document = models.JSONField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "listings"
        ordering = ["-scraped_at"]


class Make(models.Model):
    id = models.UUIDField(primary_key=True)
    slug = models.TextField(unique=True)
    name = models.TextField(unique=True)
    homepage_url = models.TextField(null=True, blank=True)
    logo_url = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "makes"
        ordering = ["name"]


class Dealer(models.Model):
    id = models.UUIDField(primary_key=True)
    slug = models.TextField(unique=True)
    name = models.TextField()
    homepage_url = models.TextField(null=True, blank=True)
    inventory_url = models.TextField(null=True, blank=True)
    cms = models.TextField(null=True, blank=True)
    cms_signals = models.JSONField(null=True, blank=True)
    robots_allows_inventory = models.BooleanField(null=True)
    region = models.TextField(null=True, blank=True)
    city = models.TextField(null=True, blank=True)
    postal_code = models.TextField(null=True, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    makes_carried = ArrayField(models.TextField(), null=True, blank=True)
    status = models.TextField(default="active")
    last_scraped_at = models.DateTimeField(null=True, blank=True)
    enrolled_at = models.DateTimeField()
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "dealers"
        ordering = ["name"]
