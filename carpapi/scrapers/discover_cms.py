from __future__ import annotations

"""Phase-1 CMS discovery tool.

For each dealer in `output/dealers_final.json`:
  1. Fetch the homepage politely (one GET, identifiable User-Agent).
  2. Identify the CMS platform from page signals (script src hosts,
     <meta name="generator">, body classes, well-known assets).
  3. Try common inventory URL patterns; pick the first that returns 200
     and contains a schema.org/Vehicle JSON-LD block.
  4. Check robots.txt for both the homepage and the discovered inventory
     path against an identifiable User-Agent string.

Output: a JSON map at `output/dealer_cms_map.json` with one record per
dealer. Resumable: re-running skips dealers already classified.

Per project policy:
  - Zero AI used in this layer (guideline 4 / scraper-rules.md).
  - Approved stack only: requests + BeautifulSoup4.
  - Sequential by default; --concurrency raises with a per-host limit.

CLI usage:
  python -m carpapi.scrapers.discover_cms \\
    --dealers output/dealers_final.json \\
    --out     output/dealer_cms_map.json \\
    --limit   10           # try just N dealers
    --skip-robots          # don't fetch robots.txt (default: do)
"""

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import asdict, dataclass, field  # noqa: I001
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

log = logging.getLogger(__name__)

USER_AGENT = (
    "CarPapiBot/0.1 (+https://github.com/ceylanbagci/carpapi; "
    "research crawler - daily cadence)"
)

# Common inventory paths in approximate order of prevalence.
INVENTORY_PATHS = (
    "/used-vehicles",
    "/used-inventory",
    "/inventory/used",
    "/preowned-vehicles",
    "/pre-owned-vehicles",
    "/pre-owned",
    "/preowned",
    "/used-cars",
    "/used",
    "/inventory",
    "/vehicles/used",
    "/cars/used",
    "/v/usedcars/",
)

# CMS fingerprints. Each entry: (cms_id, signals).
# A "signal" hits when its substring appears in the page.
# `weight` lets stronger signals win on ties.
#
# For Dealer.com specifically we also use a regex check below to catch any
# `*.dealer.com` asset host (images, cdn, static, prsnbaa etc.); the
# substring entries here are kept for backwards-compat and to score
# multiple-signal pages higher.
CMS_FINGERPRINTS: tuple[tuple[str, tuple[tuple[str, int], ...]], ...] = (
    (
        "dealer.com",
        (
            ("cdn.dealer.com", 5),
            ("images.dealer.com", 5),
            ("static.cdn.dealer.com", 5),
            ('content="Dealer.com"', 4),
            ("brand: 'Dealer.com'", 4),  # appears in window.ddc bootstrap blocks
            ("ddc-schemaorg", 4),
            ("/dealer-com/", 3),
            ("dealercom_session", 3),
            ("dealercom-shoppertools", 4),
        ),
    ),
    (
        "dealeron",
        (
            ("dealeron.com", 5),
            ('content="DealerOn"', 4),
            ("/v/usedcars/", 3),  # url path, not in homepage typically; weak
        ),
    ),
    (
        "dealer_inspire",
        (
            ("dealerinspire.com", 5),
            ('content="Dealer Inspire"', 5),
            ("powered-by-dealer-inspire", 4),
            ('class="di-', 2),
        ),
    ),
    (
        "dealersocket",
        (
            ("dealersocket.com", 5),
            ("dealerfire.com", 5),
            ('content="DealerSocket"', 4),
        ),
    ),
    (
        "fox_dealer",
        (
            ("foxdealer.com", 5),
            ('content="Fox Dealer"', 4),
        ),
    ),
    (
        "naked_lime",
        (
            ("nakedlime.com", 5),
            ('content="Naked Lime"', 4),
        ),
    ),
    (
        "vinsolutions",
        (
            ("vinsolutions.com", 5),
            ("vinconnect", 3),
        ),
    ),
    (
        "pixall",
        (
            ("pixall.com", 4),  # tag-mgr; appears on many Cox sites
        ),
    ),
)

# Regex for Dealer.com asset hosts (catches images.dealer.com,
# prsnbaa.dealer.com, etc. — Cox uses many subdomains).
_DEALER_DOT_COM_HOST_RE = re.compile(
    r"\b[a-z0-9][a-z0-9-]*\.dealer\.com\b", re.IGNORECASE
)

# Schema.org Vehicle / Car detection. We pull every JSON-LD block and
# parse it (JSON is cheap). Substring matching is unreliable due to
# whitespace, key ordering, @graph nesting, etc.
_JSONLD_BLOCK_RE = re.compile(
    r'<script\s+[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_VEHICLE_TYPES = {"Vehicle", "Car", "Motorcycle", "MotorVehicle"}


@dataclass
class DealerCMSRecord:
    dealer_name: str
    make: str
    homepage: str
    homepage_status: int = 0
    homepage_final_url: str = ""
    cms: str = "unknown"
    cms_signals: list[str] = field(default_factory=list)
    inventory_url: str = ""
    inventory_status: int = 0
    has_jsonld_vehicle: bool = False
    robots_allows_homepage: Optional[bool] = None
    robots_allows_inventory: Optional[bool] = None
    errors: list[str] = field(default_factory=list)
    checked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------- #
# Fetching helpers
# --------------------------------------------------------------------------- #


def _http_get(url: str, *, timeout: float = 15.0, max_bytes: int = 600_000):
    """Single GET. Returns (status, final_url, body_text, error)."""
    import requests  # noqa: PLC0415 — keep test envs without requests viable

    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
            allow_redirects=True,
            stream=True,
        )
    except requests.RequestException as exc:
        return 0, url, "", f"{type(exc).__name__}: {exc}"

    # Drain body up to max_bytes so we don't pull huge home-pages.
    body = b""
    try:
        for chunk in resp.iter_content(chunk_size=16_384, decode_unicode=False):
            body += chunk
            if len(body) >= max_bytes:
                break
    except Exception as exc:  # noqa: BLE001
        return resp.status_code, str(resp.url), "", f"read error: {exc}"
    finally:
        resp.close()

    encoding = resp.encoding or "utf-8"
    try:
        text = body.decode(encoding, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")

    return resp.status_code, str(resp.url), text, None


def _http_head(url: str, *, timeout: float = 10.0):
    """HEAD probe. Returns (status, final_url, error)."""
    import requests  # noqa: PLC0415

    try:
        resp = requests.head(
            url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        return 0, url, f"{type(exc).__name__}: {exc}"
    return resp.status_code, str(resp.url), None


# --------------------------------------------------------------------------- #
# Robots.txt
# --------------------------------------------------------------------------- #


def _robots_for(homepage_url: str) -> Optional[RobotFileParser]:
    parsed = urlparse(homepage_url)
    if not parsed.scheme or not parsed.hostname:
        return None
    robots_url = f"{parsed.scheme}://{parsed.hostname}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        # urllib's RobotFileParser uses urlopen which does NOT honor our
        # User-Agent. That's fine — robots.txt is public and we identify
        # our crawler via the rp.can_fetch() user-agent argument anyway.
        rp.read()
    except Exception:  # noqa: BLE001
        return None
    return rp


def _robots_allows(rp: Optional[RobotFileParser], url: str) -> Optional[bool]:
    if rp is None:
        return None
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


def detect_cms(html: str) -> tuple[str, list[str]]:
    """Score CMS fingerprints against `html`. Return (winner, signals)."""
    if not html:
        return "unknown", []
    scores: dict[str, int] = {}
    matched_signals: dict[str, list[str]] = {}
    for cms_id, signals in CMS_FINGERPRINTS:
        for needle, weight in signals:
            if needle in html:
                scores[cms_id] = scores.get(cms_id, 0) + weight
                matched_signals.setdefault(cms_id, []).append(needle)

    # Catch-all for *.dealer.com asset hosts that the literal-string
    # signals miss (Cox uses many subdomains).
    dotcom_hosts = set(_DEALER_DOT_COM_HOST_RE.findall(html))
    if dotcom_hosts:
        scores["dealer.com"] = scores.get("dealer.com", 0) + 4
        matched_signals.setdefault("dealer.com", []).append(
            f"hostnames:{','.join(sorted(dotcom_hosts)[:3])}"
        )

    if not scores:
        return "unknown", []
    winner = max(scores.items(), key=lambda kv: kv[1])[0]
    return winner, sorted(set(matched_signals[winner]))


def _extract_jsonld_objects(html: str) -> list:
    """Pull every <script type=application/ld+json> block and JSON-parse it.

    Skips blocks that don't parse (some sites embed templated/escaped JS in
    a JSON-LD-typed script). Returns a flat list of dict/list nodes.
    """
    out: list = []
    for raw in _JSONLD_BLOCK_RE.findall(html):
        text = raw.strip()
        # Some Cox/Dealer.com pages emit double-escaped JSON; try a couple of
        # common cleanups.
        for candidate in (text, text.replace("&quot;", '"')):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            out.append(obj)
            break
    return out


def _walk_for_vehicle_type(node) -> bool:
    """True iff any descendant has @type matching a Vehicle/Car schema."""
    if isinstance(node, dict):
        t = node.get("@type")
        if isinstance(t, str) and t in _VEHICLE_TYPES:
            return True
        if isinstance(t, list) and any(s in _VEHICLE_TYPES for s in t if isinstance(s, str)):
            return True
        for v in node.values():
            if _walk_for_vehicle_type(v):
                return True
    elif isinstance(node, list):
        for v in node:
            if _walk_for_vehicle_type(v):
                return True
    return False


def looks_like_vehicle_jsonld(html: str) -> bool:
    """True iff the page has at least one JSON-LD block with @type Vehicle/Car
    (anywhere in the tree, including @graph arrays and ItemList children)."""
    if not html:
        return False
    for obj in _extract_jsonld_objects(html):
        if _walk_for_vehicle_type(obj):
            return True
    return False


def discover_inventory_url(homepage_url: str, homepage_html: str) -> Optional[str]:
    """Find a plausible inventory URL.

    Strategy:
      1. Parse anchors in the homepage HTML; prefer ones whose text or path
         contains 'used', 'pre-owned', 'inventory'.
      2. Probe the well-known INVENTORY_PATHS in order.
      3. Return the first probe that returns 200 AND has a Vehicle JSON-LD,
         else the first that returns 200 (still useful — adapters may need
         AJAX to extract listings), else None.
    """
    base = homepage_url

    # Pass 1: parse <a> hrefs.
    candidates: list[str] = []
    if homepage_html:
        # Cheap regex over hrefs is fine; full parse adds little here.
        for m in re.finditer(
            r'<a\s+[^>]*href="([^"]+)"[^>]*>([^<]{0,80})</a>',
            homepage_html,
            re.IGNORECASE,
        ):
            href, text = m.group(1), m.group(2).strip().lower()
            joined = urljoin(base, href)
            if not joined.startswith(("http://", "https://")):
                continue
            if urlparse(joined).hostname != urlparse(base).hostname:
                continue
            haystack = (joined + " " + text).lower()
            if any(
                kw in haystack
                for kw in ("used-vehicle", "used-cars", "used cars", "pre-owned",
                          "preowned", "/used", "inventory")
            ):
                candidates.append(joined)
    # De-dupe while preserving order.
    seen: set[str] = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    # Pass 2: well-known paths.
    for path in INVENTORY_PATHS:
        url = urljoin(base, path)
        if url not in candidates:
            candidates.append(url)

    # Probe each candidate. Return on first vehicle-JSON-LD hit; remember
    # the first 200 as a fallback.
    fallback_200: Optional[str] = None
    for url in candidates:
        status, final_url, body, err = _http_get(url, timeout=15.0, max_bytes=300_000)
        if err is not None or status != 200:
            continue
        if looks_like_vehicle_jsonld(body):
            return final_url
        if fallback_200 is None:
            fallback_200 = final_url
        # Don't probe forever; cap per-dealer probes.
        # 8 candidates is plenty.
        if candidates.index(url) >= 7:
            break
    return fallback_200


# --------------------------------------------------------------------------- #
# Per-dealer discovery
# --------------------------------------------------------------------------- #


def discover_dealer(
    name: str,
    make: str,
    homepage: str,
    *,
    skip_robots: bool = False,
) -> DealerCMSRecord:
    rec = DealerCMSRecord(
        dealer_name=name,
        make=make,
        homepage=homepage,
        checked_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    # Reject obviously non-URL placeholders early.
    if not homepage.startswith(("http://", "https://")):
        rec.errors.append(f"homepage is not a valid URL: {homepage!r}")
        return rec

    # 1. Homepage GET.
    status, final_url, html, err = _http_get(homepage)
    rec.homepage_status = status
    rec.homepage_final_url = final_url
    if err:
        rec.errors.append(f"homepage fetch: {err}")
        return rec
    if status != 200:
        rec.errors.append(f"homepage returned HTTP {status}")
        # Continue — some sites return 200 only on www. variants and we
        # already followed redirects.

    # 2. Robots.
    rp = None if skip_robots else _robots_for(final_url)
    rec.robots_allows_homepage = _robots_allows(rp, final_url) if rp else None

    # 3. CMS detection.
    rec.cms, rec.cms_signals = detect_cms(html)

    # 4. Inventory URL.
    inv = discover_inventory_url(final_url, html)
    if inv:
        rec.inventory_url = inv
        # Probe it once more for JSON-LD presence (we may have followed
        # the fallback path that didn't have it).
        st, _final, body, e = _http_get(inv, timeout=15.0, max_bytes=300_000)
        rec.inventory_status = st
        if e is None:
            rec.has_jsonld_vehicle = looks_like_vehicle_jsonld(body)
        else:
            rec.errors.append(f"inventory fetch: {e}")
        rec.robots_allows_inventory = _robots_allows(rp, inv) if rp else None

    return rec


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="carpapi.scrapers.discover_cms",
        description="Phase-1 CMS classifier for the dealer roster.",
    )
    p.add_argument(
        "--dealers",
        default="output/dealers_final.json",
        help="Path to the dealers JSON array.",
    )
    p.add_argument(
        "--out",
        default="output/dealer_cms_map.json",
        help="Where to write the enriched per-dealer records.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process only the first N dealers (0 = all).",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to sleep between dealers (politeness).",
    )
    p.add_argument(
        "--skip-robots",
        action="store_true",
        help="Don't fetch robots.txt (default: do).",
    )
    p.add_argument(
        "--makes",
        default="",
        help="Comma-separated makes filter (e.g. 'Toyota,Honda'). Empty = all.",
    )
    return p.parse_args(argv)


def _load_dealers(path: str) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_existing(path: Path) -> dict[str, dict]:
    """Index existing records by dealer_name for resumability."""
    if not path.exists():
        return {}
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {r["dealer_name"]: r for r in records if "dealer_name" in r}


def _save(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(records, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    dealers = _load_dealers(args.dealers)
    out_path = Path(args.out)
    existing = _load_existing(out_path)
    if args.makes:
        wanted = {m.strip() for m in args.makes.split(",") if m.strip()}
        dealers = [d for d in dealers if d.get("make") in wanted]
    if args.limit > 0:
        dealers = dealers[: args.limit]

    log.info(
        "discovering %d dealers (existing classified: %d)",
        len(dealers),
        len(existing),
    )

    records: list[dict] = list(existing.values())
    seen_names = set(existing.keys())
    new_count = 0
    fail_count = 0

    for i, dealer in enumerate(dealers, 1):
        name = dealer.get("name") or f"<unnamed-{i}>"
        if name in seen_names:
            log.info("[%d/%d] skip (already classified): %s", i, len(dealers), name)
            continue
        homepage = dealer.get("dealership_website", "")
        make = dealer.get("make", "")

        log.info("[%d/%d] %s — %s", i, len(dealers), name, homepage)
        rec = discover_dealer(name, make, homepage, skip_robots=args.skip_robots)
        records.append(rec.to_dict())
        seen_names.add(name)
        new_count += 1
        if rec.errors:
            fail_count += 1

        # Save incrementally so a kill mid-run doesn't lose progress.
        _save(records, out_path)

        if args.delay > 0:
            time.sleep(args.delay)

    log.info(
        "done: %d new, %d errored. wrote %s (total %d records).",
        new_count,
        fail_count,
        out_path,
        len(records),
    )

    # Summary by CMS for the new run.
    by_cms: dict[str, int] = {}
    for r in records:
        by_cms[r.get("cms", "unknown")] = by_cms.get(r.get("cms", "unknown"), 0) + 1
    log.info("CMS breakdown:")
    for cms, count in sorted(by_cms.items(), key=lambda kv: -kv[1]):
        log.info("  %-20s %4d", cms, count)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
