"""Listing enrichment pipeline.

Two loops:
  * ``refresh-prices``  — hot loop, frequent, price column only.
  * ``enrich-vin``      — cold loop, one-shot per VIN, fills
                          ``maker_url`` / ``maker_specs`` / ``window_sticker``.

CLI entrypoint: ``python -m carpapi.enrich``.
"""
