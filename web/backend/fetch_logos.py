"""Fetch real brand logos for each make and cache them under MEDIA_ROOT.

For every row in ``public.makes`` with a homepage_url, try a small
fallback chain of standard well-known endpoints that brand sites
publish exactly so user-agents can identify them:

  1. ``https://<domain>/apple-touch-icon.png``         (180x180, PNG)
  2. ``https://<domain>/apple-touch-icon-precomposed.png``
  3. ``https://www.google.com/s2/favicons?domain=<domain>&sz=128`` (PNG)
  4. ``https://<domain>/favicon.ico``                  (last resort)

Successful fetches are saved as ``media/logos/<slug>.<ext>`` and the
DB row's ``logo_url`` is updated to point at the new file. Failures
leave the row alone (still pointing at the placeholder SVG written
by ``generate_logos.py``).

Usage:
    python fetch_logos.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import requests

BASE = Path(__file__).resolve().parent
MEDIA_LOGOS = BASE / "media" / "logos"

sys.path.insert(0, str(BASE))
from api.make_info import slug_for_filename  # noqa: E402

USER_AGENT = (
    "carpapi-web/0.1 (logo fetcher; "
    "https://github.com/ceylanbagci/carpapi)"
)
TIMEOUT = 8
DELAY_BETWEEN_MAKES = 0.4


def domain_of(url: str) -> str:
    p = urlparse(url)
    host = (p.netloc or p.path).split("/")[0]
    return host[4:] if host.startswith("www.") else host


SESSION = requests.Session()
SESSION.headers["User-Agent"] = USER_AGENT
SESSION.headers["Accept"] = "image/png,image/*,*/*;q=0.8"


def http_get(url: str) -> bytes:
    r = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return r.content


PNG_SIG = b"\x89PNG\r\n\x1a\n"
JPG_SIG = b"\xff\xd8\xff"
ICO_SIG = b"\x00\x00\x01\x00"


def detect_ext(data: bytes) -> str | None:
    if data.startswith(PNG_SIG):
        return "png"
    if data.startswith(JPG_SIG):
        return "jpg"
    if data.startswith(ICO_SIG):
        return "ico"
    head = data.lstrip()[:200].lower()
    if b"<svg" in head:
        return "svg"
    return None


# Hash of Google's "default globe" PNG returned for unknown domains —
# used as a sentinel so we don't store a generic placeholder when
# Google doesn't actually have a favicon for the brand.
GOOGLE_DEFAULTS: set[str] = set()


def remember_google_default(domain: str = "this-domain-definitely-does-not-exist-xyz.invalid") -> None:
    try:
        data = http_get(
            f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
        )
        GOOGLE_DEFAULTS.add(hashlib.sha1(data).hexdigest())
    except Exception:
        pass


def fetch_one(make: str, homepage_url: str, slug: str) -> str | None:
    domain = domain_of(homepage_url)
    if not domain:
        return None

    candidates = [
        f"https://{domain}/apple-touch-icon.png",
        f"https://{domain}/apple-touch-icon-precomposed.png",
        f"https://www.google.com/s2/favicons?domain={domain}&sz=256",
        f"https://www.google.com/s2/favicons?domain={domain}&sz=128",
        f"https://{domain}/favicon.ico",
    ]

    for url in candidates:
        try:
            data = http_get(url)
        except (requests.RequestException, TimeoutError):
            continue

        if not data or len(data) < 200:
            continue
        ext = detect_ext(data)
        if not ext:
            continue
        # Don't accept Google's generic globe fallback.
        if "google.com/s2/favicons" in url:
            if hashlib.sha1(data).hexdigest() in GOOGLE_DEFAULTS:
                continue

        out = MEDIA_LOGOS / f"{slug}.{ext}"
        out.write_bytes(data)
        rel = f"/media/logos/{slug}.{ext}"
        print(f"  ✓ {make:<22} {ext:<3} {len(data):>6}B  ←  {url}")
        return rel

    print(f"  ✗ {make:<22} (no usable logo found)")
    return None


def main() -> int:
    MEDIA_LOGOS.mkdir(parents=True, exist_ok=True)
    remember_google_default()

    dsn = (
        f"host={os.environ.get('CARPAPI_DB_HOST', 'localhost')} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5433')} "
        f"dbname={os.environ.get('CARPAPI_DB_NAME', 'carpapi')} "
        f"user={os.environ.get('CARPAPI_DB_USER', 'carpapi')} "
        f"password={os.environ.get('CARPAPI_DB_PASSWORD', 'carpapi')}"
    )

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT slug, name, homepage_url FROM public.makes "
            "WHERE homepage_url IS NOT NULL ORDER BY name"
        )
        rows = cur.fetchall()
        print(f"Fetching logos for {len(rows)} makes…")

        successes = 0
        for slug, name, homepage_url in rows:
            new_url = fetch_one(name, homepage_url, slug or slug_for_filename(name))
            if new_url:
                cur.execute(
                    "UPDATE public.makes SET logo_url=%s, updated_at=now() "
                    "WHERE slug=%s",
                    (new_url, slug),
                )
                successes += 1
            time.sleep(DELAY_BETWEEN_MAKES)
        conn.commit()

    print(f"\nDone. {successes}/{len(rows)} logos fetched and DB updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
