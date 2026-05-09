from __future__ import annotations

"""Per-dealer-page scraper harness.

Uses the approved zero-AI stack:
    - requests   for static HTTP
    - lxml       for fast HTML parsing
    - bs4        for selector convenience and JSON-LD extraction
    - selenium   for JS-rendered pages (lazy-imported; only when needed)

Per project policy:
    - No LLM calls. None. The extractor is pure selectors + heuristics.
    - Each dealer site is implemented as a separate adapter under
      `_ADAPTERS` keyed by domain. Adding a new site = one new adapter.
    - Always check site ToS / robots.txt before adding a domain.

Status: skeleton. The adapter registry is in place but no live extractors
ship until a per-domain ToS check + sample fixture have been added.
Gating is open question #1 in the project plan (data-source decision).
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    status_code: int
    html: str | None
    error: str | None = None
    fetched_at: float = 0.0
    rendered_with_selenium: bool = False


class Adapter(Protocol):
    """One adapter per dealer-site domain. Each is a no-AI parser."""

    domain: str

    def parse(self, html: str, url: str) -> dict[str, Any]: ...


# Registry — populated when adapters land. Empty by default so the harness
# fails closed.
_ADAPTERS: dict[str, Adapter] = {}


def register_adapter(adapter: Adapter) -> None:
    """Add a domain adapter at runtime. Tests use this; production code
    should add adapters at import time in the adapter module itself."""
    _ADAPTERS[adapter.domain.lower()] = adapter


def fetch(
    url: str,
    *,
    use_selenium: bool = False,
    timeout: float = 30.0,
    user_agent: str = "CarPapiBot/0.1 (+https://github.com/ceylanbagci/carpapi)",
) -> FetchResult:
    """Fetch a single dealer page. Static GET unless `use_selenium=True`."""
    started = time.time()
    if use_selenium:
        return _fetch_selenium(url, timeout=timeout, user_agent=user_agent, started=started)
    return _fetch_static(url, timeout=timeout, user_agent=user_agent, started=started)


def _fetch_static(
    url: str, *, timeout: float, user_agent: str, started: float
) -> FetchResult:
    import requests  # noqa: PLC0415

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        return FetchResult(
            url=url,
            status_code=0,
            html=None,
            error=f"{type(exc).__name__}: {exc}",
            fetched_at=started,
        )
    return FetchResult(
        url=url,
        status_code=resp.status_code,
        html=resp.text if resp.ok else None,
        error=None if resp.ok else f"HTTP {resp.status_code}",
        fetched_at=started,
    )


def _fetch_selenium(
    url: str, *, timeout: float, user_agent: str, started: float
) -> FetchResult:
    """Lazy-imported Selenium fetch for JS-rendered pages."""
    try:
        from selenium import webdriver  # noqa: PLC0415
        from selenium.webdriver.chrome.options import Options  # noqa: PLC0415
    except ImportError as exc:
        return FetchResult(
            url=url,
            status_code=0,
            html=None,
            error=f"selenium not installed: {exc}",
            fetched_at=started,
        )

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument(f"--user-agent={user_agent}")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=opts)
    try:
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        # Naive wait; per-domain adapters can implement smarter readiness checks.
        time.sleep(1.5)
        html = driver.page_source
        return FetchResult(
            url=url,
            status_code=200,
            html=html,
            error=None,
            fetched_at=started,
            rendered_with_selenium=True,
        )
    except Exception as exc:  # noqa: BLE001
        return FetchResult(
            url=url,
            status_code=0,
            html=None,
            error=f"{type(exc).__name__}: {exc}",
            fetched_at=started,
            rendered_with_selenium=True,
        )
    finally:
        driver.quit()


def parse(result: FetchResult) -> dict[str, Any] | None:
    """Run the registered adapter for `result.url`'s domain.

    Returns the adapter's raw dict, or None when no adapter is registered
    or the fetch failed.
    """
    if result.html is None:
        return None
    domain = _domain_of(result.url)
    adapter = _ADAPTERS.get(domain)
    if adapter is None:
        log.warning("no adapter registered for %s — skipping parse", domain)
        return None
    return adapter.parse(result.html, result.url)


def _domain_of(url: str) -> str:
    from urllib.parse import urlparse  # noqa: PLC0415

    return (urlparse(url).hostname or "").lower().lstrip("www.")


def jsonld_blocks(html: str) -> list[dict[str, Any]]:
    """Helper for adapters: pull every <script type=application/ld+json> block.

    Many dealer sites publish Vehicle / AutoDealer schema.org blocks. They
    are far more stable than CSS selectors — adapters should prefer them.
    """
    import json  # noqa: PLC0415
    from bs4 import BeautifulSoup  # noqa: PLC0415

    soup = BeautifulSoup(html, "lxml")
    out: list[dict[str, Any]] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = tag.string or tag.text
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            out.extend(p for p in parsed if isinstance(p, dict))
        elif isinstance(parsed, dict):
            out.append(parsed)
    return out
