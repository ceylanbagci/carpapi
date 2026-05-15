"""Add image_url + image_svg_url columns to public.listings.

The Listing table is owned by the SQLAlchemy pipeline
(`pipeline/carapi_pipeline/models.py`), not by Django, so its schema
isn't auto-managed by makemigrations. We use a RunSQL migration here
because it's the cleanest hook into the existing migrate-on-boot
step in the Dockerfile CMD — every App Runner deploy applies all
pending migrations before gunicorn starts.

`image_url` stores the public URL of a small (240×160) JPEG
thumbnail uploaded to S3 (and served via CloudFront). Populated
by the carpapi/images/ pipeline. Null when the image hasn't been
processed yet (or the dealer page had no image we could extract).

`image_svg_url` is the optional minimal-SVG silhouette companion
(generated via potrace). May be null. The frontend prefers
`image_url` and falls back to the SVG only when the JPEG is missing.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_adminotpchallenge"),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "ALTER TABLE public.listings ADD COLUMN IF NOT EXISTS image_url TEXT",
                "ALTER TABLE public.listings ADD COLUMN IF NOT EXISTS image_svg_url TEXT",
            ],
            reverse_sql=[
                "ALTER TABLE public.listings DROP COLUMN IF EXISTS image_svg_url",
                "ALTER TABLE public.listings DROP COLUMN IF EXISTS image_url",
            ],
        ),
    ]
