from __future__ import annotations

"""Smoke test for carpapi.scrapers.discover_cms.

Pure offline test: synthetic HTML samples for each CMS fingerprint and
each Vehicle JSON-LD pattern. No network, no real dealer URLs.

Run from repo root:
    python eval/run_cms_discovery_eval.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from carpapi.scrapers.discover_cms import (  # noqa: E402
    detect_cms,
    discover_inventory_url,
    looks_like_vehicle_jsonld,
)


# --- detect_cms --------------------------------------------------------- #

DETECT_CASES = [
    (
        "dealer.com homepage with CDN host",
        '<html><head><script src="https://cdn.dealer.com/inde.js"></script>'
        '<meta name="generator" content="Dealer.com"></head><body></body></html>',
        "dealer.com",
    ),
    (
        "dealeron with explicit generator",
        '<html><head><script src="https://www.dealeron.com/x.js"></script>'
        '<meta name="generator" content="DealerOn"></head><body></body></html>',
        "dealeron",
    ),
    (
        "dealer inspire with powered-by class",
        '<html><body class="powered-by-dealer-inspire">'
        '<script src="https://cdn.dealerinspire.com/x.js"></script></body></html>',
        "dealer_inspire",
    ),
    (
        "dealersocket script",
        '<html><body><script src="https://x.dealersocket.com/y.js">'
        '</script></body></html>',
        "dealersocket",
    ),
    (
        "fox dealer generator",
        '<html><head><meta name="generator" content="Fox Dealer">'
        '</head><body></body></html>',
        "fox_dealer",
    ),
    (
        "naked lime",
        '<html><body><script src="//cdn.nakedlime.com/x.js"></script></body></html>',
        "naked_lime",
    ),
    (
        "vinsolutions",
        '<html><body><script src="//app.vinsolutions.com/x.js"></script>'
        '</body></html>',
        "vinsolutions",
    ),
    (
        "completely unknown CMS",
        "<html><body><h1>Joe's Used Cars</h1></body></html>",
        "unknown",
    ),
    (
        "dealer.com with multiple signals beats single-signal others",
        '<html><head><script src="https://cdn.dealer.com/a.js"></script>'
        '<meta name="generator" content="Dealer.com">'
        '<script src="//app.vinsolutions.com/v.js"></script></head><body>'
        '</body></html>',
        "dealer.com",
    ),
    (
        "dealer.com via images.dealer.com asset host (caught by regex)",
        '<html><head>'
        '<link rel="dns-prefetch" href="https://images.dealer.com/">'
        '</head><body></body></html>',
        "dealer.com",
    ),
    (
        "dealer.com via prsnbaa.dealer.com personalization (caught by regex)",
        '<html><body>'
        '<script src="https://prsnbaa.dealer.com/personalization.js"></script>'
        '</body></html>',
        "dealer.com",
    ),
]


def case_detect_cms() -> list[str]:
    fails: list[str] = []
    for label, html, expected in DETECT_CASES:
        actual, _signals = detect_cms(html)
        if actual != expected:
            fails.append(f"{label}: expected {expected!r}, got {actual!r}")
    return fails


# --- looks_like_vehicle_jsonld ---------------------------------------- #

JSONLD_CASES = [
    (
        "explicit Vehicle @type",
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Vehicle","name":"2022 Camry"}'
        "</script>",
        True,
    ),
    (
        "explicit Car @type",
        '<script type="application/ld+json">{"@type":"Car","name":"x"}</script>',
        True,
    ),
    (
        "Organization JSON-LD only — no Vehicle",
        '<script type="application/ld+json">{"@type":"AutoDealer","name":"x"}</script>',
        False,
    ),
    (
        "no JSON-LD at all",
        "<html><body>Welcome</body></html>",
        False,
    ),
    (
        "empty",
        "",
        False,
    ),
    (
        "JSON-LD with whitespace after colon — must still match",
        '<script type="application/ld+json">{"@context": "https://schema.org",'
        '  "@type": "Vehicle", "name": "2022 Camry"}</script>',
        True,
    ),
    (
        "Vehicle nested inside @graph",
        '<script type="application/ld+json">{"@graph":['
        '{"@type":"AutoDealer","name":"x"},{"@type":"Vehicle","name":"y"}]}'
        "</script>",
        True,
    ),
    (
        "Vehicle inside ItemList children",
        '<script type="application/ld+json">'
        '{"@type":"ItemList","itemListElement":['
        '{"@type":"ListItem","position":1,"item":'
        '{"@type":"Vehicle","name":"2021 CR-V"}}]}</script>',
        True,
    ),
    (
        "type as a list including Vehicle",
        '<script type="application/ld+json">'
        '{"@type":["Product","Vehicle"],"name":"truck"}</script>',
        True,
    ),
    (
        "single-quoted script type attribute",
        "<script type='application/ld+json'>{\"@type\":\"Vehicle\"}</script>",
        True,
    ),
]


def case_looks_like_vehicle_jsonld() -> list[str]:
    fails: list[str] = []
    for label, html, expected in JSONLD_CASES:
        actual = looks_like_vehicle_jsonld(html)
        if actual != expected:
            fails.append(f"{label}: expected {expected}, got {actual}")
    return fails


# --- discover_inventory_url (URL pattern logic only — no network) ----- #
# We can't fully test discover_inventory_url without HTTP; skip it here
# and let the Phase-1 smoke run against real URLs validate the network
# path. The classifier and JSON-LD checker are the high-value pure-logic
# pieces to lock down with unit tests.


def main() -> int:
    cases = [
        ("detect_cms classifies known platforms", case_detect_cms),
        ("looks_like_vehicle_jsonld matches Vehicle/Car", case_looks_like_vehicle_jsonld),
    ]
    total = 0
    failed = 0
    for label, runner in cases:
        total += 1
        fails = runner()
        if fails:
            failed += 1
            print(f"  FAIL  {label}")
            for f in fails:
                print(f"    - {f}")
        else:
            print(f"  ok    {label}")
    print(f"\nCMS discovery eval: {total - failed}/{total} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
