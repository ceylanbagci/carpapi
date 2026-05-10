"""Window sticker (Monroney label) parser.

Pipeline: download a sticker PDF → run markitdown to convert it to
Markdown → regex-extract MSRP, options, fuel economy, standard
features, and any dealer addendum. Result is stored at
``public.listings.window_sticker`` as JSONB.

The CLI never invokes this with a hot URL it hasn't already verified
on the maker page — sticker URLs flow through the orchestrator only.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import logging
import re
from typing import Any

import requests
from markitdown import MarkItDown

log = logging.getLogger(__name__)

USER_AGENT = "CarPapiBot/0.1 (+https://github.com/ceylanbagci/carpapi)"
MAX_BYTES = 25 * 1024 * 1024  # 25MB cap for sticker PDFs


def fetch_pdf(url: str, timeout: int = 20) -> bytes:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/pdf,*/*;q=0.8",
    }
    with requests.get(url, headers=headers, timeout=timeout, stream=True) as resp:
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "")
        # Some servers serve PDFs with octet-stream — accept both
        if "pdf" not in ctype.lower() and "octet-stream" not in ctype.lower():
            log.warning("sticker fetch: unexpected content-type %s for %s", ctype, url)
        body = b""
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            body += chunk
            if len(body) > MAX_BYTES:
                raise ValueError(f"sticker PDF too large (>{MAX_BYTES}B): {url}")
        if not body.startswith(b"%PDF-"):
            raise ValueError(f"sticker fetch: response is not a PDF (first bytes={body[:4]!r}) at {url}")
        return body


def parse_pdf_bytes(pdf_bytes: bytes, *, source_url: str | None = None) -> dict[str, Any]:
    """PDF → markdown via markitdown → structured fields."""
    try:
        result = MarkItDown().convert_stream(
            io.BytesIO(pdf_bytes),
            file_extension=".pdf",
        )
    except Exception as e:
        return {
            "parser_error": f"markitdown failed: {e}",
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            "source_url": source_url,
            "parsed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }

    text = result.text_content or ""
    # PII scrub — drop phone numbers and emails out of an abundance of caution.
    text = _scrub_pii(text)

    out: dict[str, Any] = {
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "source_url": source_url,
        "parsed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "msrp": _extract_msrp(text),
        "base_price": _extract_dollar(text, r"Base\s+Price[^\n]{0,40}"),
        "destination_charge": _extract_dollar(text, r"Destination[^\n]{0,40}"),
        "fuel_city_mpg": _extract_int(text, r"(\d{1,2})\s*city"),
        "fuel_hwy_mpg": _extract_int(text, r"(\d{1,2})\s*(?:highway|hwy)"),
        "options": _extract_options(text),
        "standard_features": _extract_section(text, "Standard Equipment", "Standard Features"),
        "addendum": _extract_section(text, "Dealer Addendum", "Addendum"),
        "raw_markdown": text[:30_000],  # cap for storage
    }
    return out


# --------------------------------------------------------------------- #
# Regex extractors
# --------------------------------------------------------------------- #


def _extract_msrp(text: str) -> int | None:
    for pat in (
        r"Total\s+MSRP[^\$\n]{0,40}\$([\d,]+)",
        r"MSRP[^\$\n]{0,40}\$([\d,]+)",
        r"Total\s+Price[^\$\n]{0,40}\$([\d,]+)",
        r"Suggested\s+Retail\s+Price[^\$\n]{0,40}\$([\d,]+)",
    ):
        m = re.search(pat, text, flags=re.I)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _extract_dollar(text: str, prefix_pattern: str) -> int | None:
    m = re.search(prefix_pattern + r"\$([\d,]+)", text, flags=re.I | re.S)
    if m:
        try:
            return int(m.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _extract_int(text: str, pattern: str) -> int | None:
    m = re.search(pattern, text, flags=re.I)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _extract_options(text: str) -> list[dict[str, Any]]:
    """Lines that look like ``<label> $<price>`` — typical Monroney
    option-line shape across most US sticker layouts."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) > 200:
            continue
        m = re.match(r"^([A-Z][A-Za-z0-9&,\-/\s\.\']{4,80})\s+\$([\d,]+)\s*$", line)
        if not m:
            continue
        label = re.sub(r"\s+", " ", m.group(1)).strip(" ,")
        price_raw = m.group(2).replace(",", "")
        try:
            price = int(price_raw)
        except ValueError:
            continue
        # Drop obvious totals so they don't show up as options
        if label.lower() in {"total msrp", "msrp", "total price", "total"}:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label, "price": price})
        if len(out) >= 60:
            break
    return out


def _extract_section(text: str, *header_aliases: str) -> list[str]:
    """Return non-empty lines between a header alias and the next ALL-CAPS heading."""
    pattern = r"^\s*(?:" + "|".join(re.escape(h) for h in header_aliases) + r")\s*$"
    lines = text.splitlines()
    found = -1
    for i, line in enumerate(lines):
        if re.match(pattern, line, flags=re.I):
            found = i
            break
    if found < 0:
        return []
    out: list[str] = []
    for line in lines[found + 1 : found + 200]:  # cap to ~200 lines
        s = line.strip()
        if not s:
            continue
        # next heading? stop.
        if re.match(r"^[A-Z][A-Z\s/&\-]{3,40}$", s) and len(s) < 50:
            break
        if len(s) >= 3:
            out.append(s)
        if len(out) >= 80:
            break
    return out


_PHONE_RE = re.compile(r"\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}")
_EMAIL_RE = re.compile(r"[\w.\-]+@[\w\-]+(?:\.[\w\-]+)+", flags=re.I)


def _scrub_pii(text: str) -> str:
    text = _PHONE_RE.sub("[redacted-phone]", text)
    text = _EMAIL_RE.sub("[redacted-email]", text)
    return text
