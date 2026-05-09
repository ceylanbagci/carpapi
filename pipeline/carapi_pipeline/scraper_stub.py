"""Placeholder scraper that replays bundled fixtures until real site adapters exist."""

from __future__ import annotations

from typing import Any

from carapi_pipeline.normalize import load_fixture


def fetch_demo_listings() -> list[dict[str, Any]]:
    return load_fixture("sample_listings.json")
