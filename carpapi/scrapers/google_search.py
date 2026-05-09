from __future__ import annotations

"""Google Custom Search API client.

NOT a scrape. Uses Google's official paid API (Custom Search JSON API).
That makes it ToS-compliant and rate-limited by Google rather than by
target sites' anti-bot defenses.

Use cases:
- Discover dealer listing pages by query ("Toyota Camry for sale 07470")
- Find detail-page URLs that other scrapers (dealership_page,
  dealerrater) then visit.

Required env vars:
    GOOGLE_CSE_API_KEY  — Google Cloud API key with Custom Search API enabled
    GOOGLE_CSE_ID       — the Custom Search Engine identifier

Both are configured in your Google Cloud console:
    https://developers.google.com/custom-search/v1/overview

Per project policy this module:
- Has zero LLM/AI calls.
- Returns raw dicts; downstream code may inspect them with statistical
  monitors (carpapi.monitor.scrape_monitor) but never an LLM.
"""

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Iterator

log = logging.getLogger(__name__)

_API_BASE = "https://www.googleapis.com/customsearch/v1"
_PAGE_SIZE = 10  # Google's max per request
_MAX_RESULTS = 100  # Google's hard cap across pagination


@dataclass(frozen=True)
class GoogleSearchResult:
    title: str
    link: str
    snippet: str
    display_link: str
    raw: dict[str, Any]


class GoogleSearchError(RuntimeError):
    """Raised on auth, quota, or unexpected API responses."""


def search(
    query: str,
    *,
    api_key: str | None = None,
    cse_id: str | None = None,
    max_results: int = 30,
    site_filter: str | None = None,
    safe: str = "active",
    sleep_between_pages: float = 0.2,
) -> Iterator[GoogleSearchResult]:
    """Yield up to `max_results` search results for `query`.

    Args:
      query: free-form search string. Quote phrases as needed.
      api_key: defaults to env GOOGLE_CSE_API_KEY.
      cse_id: defaults to env GOOGLE_CSE_ID.
      max_results: hard cap; Google itself caps at 100.
      site_filter: e.g. 'dealerrater.com' to restrict to one domain.
      safe: 'active' or 'off'.
      sleep_between_pages: small delay between pagination calls to be polite.

    Raises:
      GoogleSearchError on auth failure, quota exhaustion, or unexpected
      response shape.
    """
    import requests  # noqa: PLC0415 — keep import lazy so test envs work

    api_key = api_key or os.environ.get("GOOGLE_CSE_API_KEY")
    cse_id = cse_id or os.environ.get("GOOGLE_CSE_ID")
    if not api_key or not cse_id:
        raise GoogleSearchError(
            "GOOGLE_CSE_API_KEY and GOOGLE_CSE_ID must be set "
            "(env or function args)."
        )

    capped = min(max_results, _MAX_RESULTS)
    yielded = 0
    start = 1  # Google uses 1-based indexing for `start`

    while yielded < capped:
        params: dict[str, Any] = {
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "num": min(_PAGE_SIZE, capped - yielded),
            "start": start,
            "safe": safe,
        }
        if site_filter:
            params["siteSearch"] = site_filter
            params["siteSearchFilter"] = "i"  # include only

        resp = requests.get(_API_BASE, params=params, timeout=30)
        if resp.status_code == 403:
            raise GoogleSearchError(
                f"Google CSE 403: {resp.text[:200]} (check API key quotas)"
            )
        if resp.status_code == 429:
            raise GoogleSearchError("Google CSE 429: rate-limited")
        if resp.status_code >= 400:
            raise GoogleSearchError(
                f"Google CSE {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        items = data.get("items", [])
        if not items:
            return

        for item in items:
            yield GoogleSearchResult(
                title=item.get("title", ""),
                link=item.get("link", ""),
                snippet=item.get("snippet", ""),
                display_link=item.get("displayLink", ""),
                raw=item,
            )
            yielded += 1
            if yielded >= capped:
                return

        # Pagination: respect total-results count if Google reports we're
        # past the end.
        next_page = data.get("queries", {}).get("nextPage")
        if not next_page:
            return
        start = int(next_page[0]["startIndex"])
        if sleep_between_pages > 0:
            time.sleep(sleep_between_pages)


def collect(query: str, **kwargs: Any) -> list[GoogleSearchResult]:
    """Convenience: drain `search()` into a list."""
    return list(search(query, **kwargs))
