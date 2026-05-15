"""Image pipeline: URL → 240×160 JPEG thumbnail → S3 → public CloudFront URL.

Pipeline:
  1. Download the source image (URL extracted from the dealer page).
  2. Use Pillow to:
     - Decode (RGB).
     - Cover-fit to 240×160 (crop the longer dimension; we want a card
       thumbnail, not a letterboxed frame).
     - Encode as progressive JPEG, quality=78, optimize=True.
  3. Upload the JPEG to S3 under
     `s3://carpapi-frontend-183617081338/listings/<vin-or-id>.jpg`.
  4. Optionally generate a minimal SVG silhouette via `potracer` and
     upload to `…/listings/<vin-or-id>.svg`. Silently skipped when the
     `potracer` package is not installed.
  5. Return both public URLs.

CloudFront sits in front of that bucket, so the public-facing URLs are
`https://d372ww3313y553.cloudfront.net/listings/<vin>.jpg(.svg)`.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from typing import Optional

import boto3
import requests
from PIL import Image

log = logging.getLogger("carpapi.images.processor")


# ─────────────────────────────────────────────────────────────────────
# Config — env-driven so the CLI can swap buckets / distribution.
# ─────────────────────────────────────────────────────────────────────

import os

S3_BUCKET = os.environ.get(
    "CARPAPI_IMAGES_S3_BUCKET", "carpapi-frontend-183617081338",
)
S3_PREFIX = os.environ.get("CARPAPI_IMAGES_S3_PREFIX", "listings").strip("/")
CDN_BASE = os.environ.get(
    "CARPAPI_IMAGES_CDN_BASE", "https://d372ww3313y553.cloudfront.net",
).rstrip("/")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

THUMB_SIZE = (240, 160)
JPEG_QUALITY = 78


# ─────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────

@dataclass
class ProcessResult:
    image_url: Optional[str] = None
    image_svg_url: Optional[str] = None
    source_url: Optional[str] = None
    bytes_in: int = 0
    bytes_jpg: int = 0
    bytes_svg: int = 0
    error: Optional[str] = None
    # When the source image traces to a near-empty SVG (< ~300B of
    # path data) we treat the photo as a dealer logo / placeholder and
    # signal up so the CLI can skip the DB write. The S3 JPEG is
    # left in place — a later good scrape (keyed by the same VIN)
    # will overwrite it.
    likely_placeholder: bool = False

    @property
    def ok(self) -> bool:
        return bool(self.image_url) and not self.likely_placeholder


# ─────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────

def process_for_listing(
    *,
    listing_key: str,
    source_url: str,
    generate_svg: bool = True,
) -> ProcessResult:
    """Download → resize → upload. `listing_key` becomes the S3 object
    name (e.g. the VIN or the listing UUID). Returns a `ProcessResult`
    with the public CDN URLs and byte counts.
    """
    result = ProcessResult(source_url=source_url)

    raw = _download(source_url)
    if not raw:
        result.error = "download_failed"
        return result
    result.bytes_in = len(raw)

    try:
        thumb_bytes = _to_thumbnail_jpeg(raw)
    except Exception as exc:  # noqa: BLE001
        log.warning("thumbnail failed for %s: %s", listing_key, exc)
        result.error = "decode_failed"
        return result
    result.bytes_jpg = len(thumb_bytes)

    s3 = boto3.client("s3", region_name=AWS_REGION)
    jpg_key = f"{S3_PREFIX}/{listing_key}.jpg"
    try:
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=jpg_key,
            Body=thumb_bytes,
            ContentType="image/jpeg",
            CacheControl="public, max-age=2592000, immutable",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("S3 PutObject failed for %s: %s", jpg_key, exc)
        result.error = "s3_put_failed"
        return result
    result.image_url = f"{CDN_BASE}/{jpg_key}"

    if generate_svg:
        svg_bytes = _to_silhouette_svg(thumb_bytes)
        if svg_bytes:
            # Below ~300 bytes the SVG is essentially `<svg><path d=""/>`
            # — potrace traced no significant contour, which means the
            # source was a near-uniform image: dealer logo on a solid
            # background, a "photo coming soon" placeholder, etc.
            # Flag the result so the caller can skip the DB write.
            if len(svg_bytes) < 300:
                log.info(
                    "likely placeholder for %s (svg=%db, jpg=%db)",
                    listing_key, len(svg_bytes), result.bytes_jpg,
                )
                result.likely_placeholder = True
                result.error = "likely_placeholder"
                result.bytes_svg = len(svg_bytes)
                return result
            svg_key = f"{S3_PREFIX}/{listing_key}.svg"
            try:
                s3.put_object(
                    Bucket=S3_BUCKET,
                    Key=svg_key,
                    Body=svg_bytes,
                    ContentType="image/svg+xml",
                    CacheControl="public, max-age=2592000, immutable",
                )
                result.image_svg_url = f"{CDN_BASE}/{svg_key}"
                result.bytes_svg = len(svg_bytes)
            except Exception as exc:  # noqa: BLE001
                log.warning("S3 PutObject (svg) failed for %s: %s", svg_key, exc)

    return result


# ─────────────────────────────────────────────────────────────────────
# Steps
# ─────────────────────────────────────────────────────────────────────

def _download(url: str) -> bytes:
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "CarPapiImageBot/1.0",
                "Accept": "image/avif,image/webp,image/jpeg,image/png,*/*",
            },
            timeout=15,
            allow_redirects=True,
            stream=True,
        )
        if r.status_code >= 400:
            log.info("image fetch %s → HTTP %s", url, r.status_code)
            return b""
        # Cap at 4 MB to defend against runaway dealer pages serving
        # uncompressed 20 MB images.
        chunks = []
        total = 0
        for chunk in r.iter_content(64 * 1024):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total > 4 * 1024 * 1024:
                log.info("image fetch %s exceeded 4MB cap, truncating", url)
                break
        return b"".join(chunks)
    except requests.RequestException as exc:
        log.info("image fetch %s → %s", url, exc)
        return b""


def _to_thumbnail_jpeg(raw: bytes) -> bytes:
    """Cover-fit to THUMB_SIZE, encode as progressive JPEG."""
    src = Image.open(io.BytesIO(raw))
    src = src.convert("RGB")
    # Cover-fit: scale so the shorter side matches, then center-crop.
    sw, sh = src.size
    tw, th = THUMB_SIZE
    scale = max(tw / sw, th / sh)
    new = (round(sw * scale), round(sh * scale))
    src = src.resize(new, Image.LANCZOS)
    left = (new[0] - tw) // 2
    top = (new[1] - th) // 2
    src = src.crop((left, top, left + tw, top + th))

    buf = io.BytesIO()
    src.save(
        buf,
        format="JPEG",
        quality=JPEG_QUALITY,
        optimize=True,
        progressive=True,
    )
    return buf.getvalue()


def _to_silhouette_svg(jpg_bytes: bytes) -> Optional[bytes]:
    """Trace the thumbnail into a single-color SVG silhouette using
    `potracer`. Returns None when the dependency isn't installed.
    The output is ~3-8 KB and works well as a dark-mode placeholder."""
    try:
        # The `potracer` package installs as the `potrace` module.
        import potrace  # type: ignore
        import numpy as np  # potrace.Bitmap expects a 2-D bool array
    except ImportError:
        return None

    try:
        img = Image.open(io.BytesIO(jpg_bytes)).convert("L")
        # Higher contrast → cleaner silhouette.
        threshold = 128
        arr = np.array(img) < threshold
        bitmap = potrace.Bitmap(arr)
        path = bitmap.trace(turdsize=4, opttolerance=0.5)

        # Build a clean minimal SVG (single path, viewBox-only, no
        # XML preamble bloat — Inkscape headers cost 800B otherwise).
        h, w = arr.shape
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'preserveAspectRatio="xMidYMid meet">',
            '  <path fill="#3699FF" d="',
        ]
        for curve in path:
            parts.append(f"M{curve.start_point.x:.1f},{curve.start_point.y:.1f} ")
            for seg in curve.segments:
                if seg.is_corner:
                    parts.append(
                        f"L{seg.c.x:.1f},{seg.c.y:.1f} L{seg.end_point.x:.1f},{seg.end_point.y:.1f} "
                    )
                else:
                    parts.append(
                        f"C{seg.c1.x:.1f},{seg.c1.y:.1f} "
                        f"{seg.c2.x:.1f},{seg.c2.y:.1f} "
                        f"{seg.end_point.x:.1f},{seg.end_point.y:.1f} "
                    )
            parts.append("Z ")
        parts.append('"/></svg>')
        return "".join(parts).encode("utf-8")
    except Exception as exc:  # noqa: BLE001
        log.info("potrace failed: %s", exc)
        return None
