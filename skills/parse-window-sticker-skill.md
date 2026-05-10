# Skill: parse-window-sticker

Convert a Monroney window-sticker PDF (downloaded from the
manufacturer's website during cold-loop enrichment) into a structured
JSONB document, using [microsoft/markitdown](https://github.com/microsoft/markitdown)
as the PDF→Markdown bridge and a small set of regex extractors over the
Markdown.

## When to use this skill

Trigger when working on any of:
- the window-sticker JSON shape, the `listings.window_sticker` field
- markitdown integration / PDF parsing in carpapi
- adding/tuning the regex extractors (`_extract_msrp`, `_extract_options`, etc.)
- a sticker that parsed wrong (an option line is missing, MSRP was off)

## Read first

- [carpapi/enrich/window_sticker.py](../carpapi/enrich/window_sticker.py) — the parser module
- [pipeline/carapi_pipeline/pii.py](../pipeline/carapi_pipeline/pii.py) — PII scrubber to apply to the markdown before storing
- [carpapi/db/schema.sql](../carpapi/db/schema.sql) — `listings.window_sticker` (JSONB) column
- markitdown docs: https://github.com/microsoft/markitdown — only PDF + (optional) image OCR fallback are relevant here

## Setup

```bash
cd web/backend
.venv/bin/pip install 'markitdown[all]'>=0.0.1a3
```

(The `[all]` extra pulls PDF and OCR dependencies. Use `markitdown[pdf]`
if disk pressure matters; OCR is only needed for sticker scans.)

## Parse pipeline

```python
import io, hashlib
from markitdown import MarkItDown

def parse_pdf(pdf_bytes: bytes) -> dict:
    md = MarkItDown().convert_stream(
        io.BytesIO(pdf_bytes),
        file_extension=".pdf",
    )
    text = scrub_pii(md.text_content)   # carpapi_pipeline.pii.scrub
    return {
        "pdf_sha256":         hashlib.sha256(pdf_bytes).hexdigest(),
        "msrp":               _extract_msrp(text),
        "base_price":         _extract_field(text, r"Base\s+Price[^\n]*\$([\d,]+)"),
        "destination_charge": _extract_field(text, r"Destination[^\n]*\$([\d,]+)"),
        "fuel_city_mpg":      _extract_int(text, r"(\d{1,2})\s*(?:city|City)"),
        "fuel_hwy_mpg":       _extract_int(text, r"(\d{1,2})\s*(?:highway|hwy|Highway|Hwy)"),
        "options":            _extract_options(text),
        "standard_features":  _extract_section(text, "Standard Equipment"),
        "addendum":           _extract_section(text, "Addendum"),
        "raw_markdown":       text,
        "parsed_at":          datetime.now(timezone.utc).isoformat(),
    }
```

## Output JSON shape

The shape stored at `public.listings.window_sticker`:

```json
{
  "pdf_sha256": "1a2b3c…",
  "msrp": 42395,
  "base_price": 38995,
  "destination_charge": 1395,
  "fuel_city_mpg": 24,
  "fuel_hwy_mpg": 33,
  "options": [
    {"label": "Equipment Group 200A", "price": 1500},
    {"label": "Co-Pilot360 Assist+",  "price":  995}
  ],
  "standard_features": [
    "10.1\" SYNC 4 touchscreen",
    "AdvanceTrac with RSC",
    "..."
  ],
  "addendum": [
    {"label": "Door edge guards", "price": 195}
  ],
  "raw_markdown": "Total MSRP $42,395\\nBase Price $38,995\\n…",
  "parsed_at": "2026-05-10T17:42:01+00:00"
}
```

Always store `raw_markdown` (after PII scrub) — it's small and lets us
re-parse offline when an extractor regex is improved.

## Extractor patterns

| field              | primary regex (case-insensitive) |
|--------------------|----------------------------------|
| MSRP               | `Total\s+MSRP[^\n]{0,40}\$([\d,]+)` then fallback `MSRP[^\n]{0,40}\$([\d,]+)` |
| Base price         | `Base\s+Price[^\n]*\$([\d,]+)` |
| Destination        | `Destination[^\n]*\$([\d,]+)` |
| Fuel city/highway  | `(\d{1,2})\s*city\s*/\s*(\d{1,2})\s*(?:highway|hwy)` (combined first), then individual |
| Options            | line-anchored `^\s*([A-Z][^$\n]{4,80})\s+\$([\d,]+)\s*$` |
| Sections           | between header line `^Standard\s+Equipment\s*$` and next ALL-CAPS header |

Numeric values: strip commas, parse as int (or float if a decimal point
is present). `_extract_field()` returns `None` if no match.

## Failure modes

| symptom                                  | cause / fix |
|------------------------------------------|-------------|
| `markitdown` returns empty `text_content`| Encrypted/scanned PDF — escalate to OCR (markitdown does this if `[all]` is installed) or skip and set `parser_error` |
| MSRP is `None` for a known-good sticker   | Add a maker-specific regex to `MSRP_PATTERNS_BY_MAKE` |
| Option list comes back garbled           | The maker uses a multi-column layout; markitdown emits it linearly. Add per-maker post-processing (e.g. Ford uses tabs as column separators). |
| PII detected in raw markdown             | The PII scrubber should redact phone/email — confirm `scrub_pii()` ran before storing |

## Verification

```bash
# One-off parse for a VIN with a known sticker URL
python -m carpapi.enrich parse-sticker 1FA6P8AM6N5100001

# Confirm JSON populated
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d carpapi -c "
  SELECT vin,
         window_sticker -> 'msrp' AS msrp,
         jsonb_array_length(coalesce(window_sticker -> 'options', '[]'::jsonb)) AS option_count,
         window_sticker -> 'fuel_city_mpg' AS city_mpg,
         window_sticker -> 'fuel_hwy_mpg' AS hwy_mpg
  FROM public.listings
  WHERE vin = '1FA6P8AM6N5100001'"
```

Manually open the original PDF; assert all four numbers match.

## Idempotency

This skill cooperates with the orchestrator: `parse-sticker <vin>`
re-runs unconditionally (you're explicitly asking to re-parse).
The orchestrator's auto-call only runs when `window_sticker IS NULL`.
