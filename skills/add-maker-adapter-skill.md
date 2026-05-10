# Skill: add-maker-adapter

Template + checklist for adding a new manufacturer-site adapter under
`carpapi.makers.<slug>`. Each adapter handles one make — given a VIN,
returns the canonical maker-page URL, the parsed factory specs, and
the window-sticker PDF URL.

## When to use this skill

Trigger when working on any of:
- "add an adapter for <make>", "support Honda / Toyota / Subaru / GM"
- the per-make dispatch logic in `carpapi.makers.__init__.REGISTRY`
- diagnosing `maker_enrich_status='unsupported'` for a make that should be supported
- expanding cold-loop coverage to more brands

## Read first

- [carpapi/makers/base.py](../carpapi/makers/base.py) — the `MakerAdapter` ABC and `MakerLookup` dataclass
- [carpapi/makers/ford.py](../carpapi/makers/ford.py) — canonical reference adapter
- [carpapi/makers/__init__.py](../carpapi/makers/__init__.py) — the adapter registry
- [enrich-from-maker-skill](enrich-from-maker-skill.md) — how the orchestrator consumes adapters

## Adapter contract (1-pass design)

Each adapter exposes a single `lookup(vin)` method. **One method, one
network round-trip if at all possible** — fan-out makes the orchestrator
hard to throttle.

```python
# carpapi/makers/<slug>.py
from .base import MakerAdapter, MakerLookup, MakerUnsupported, MakerLoginRequired

class FooAdapter(MakerAdapter):
    make = "Foo"
    supported = True       # set to False if no public VIN endpoint
    rate_limit_seconds = 1.5

    def lookup(self, vin: str) -> MakerLookup:
        url = self._vehicle_url(vin)
        html = self._fetch(url)              # uses shared HTTP from runner.py
        specs = self._parse_specs(html)
        sticker_url = self._find_sticker(html, vin)
        return MakerLookup(
            maker_url=url,
            specs=specs,
            sticker_url=sticker_url,
            raw_html=html if len(html) < 200_000 else None,
        )
```

## What goes in `specs` (target shape)

A flat-ish dict — keep keys consistent across adapters so the
denormalizer (`carpapi.enrich.merger`) can promote a small set to
columns later.

```python
{
    "trim":           "XLT",
    "drivetrain":     "AWD",
    "transmission":   "10-speed automatic",
    "engine":         "2.7L EcoBoost V6",
    "fuel":           "Gasoline",
    "exterior_color": "Iconic Silver Metallic",
    "interior_color": "Ebony",
    "seating":        5,
    "msrp_listed":    42395,                  # what the maker page shows; sticker may differ
    "package":        "Equipment Group 200A",
    "options":        ["Co-Pilot360 Assist+", "Tow Package"],
    "vin_match":      "exact" | "model_only", # did the page actually echo the VIN?
    "scraped_at":     "2026-05-10T17:42:01+00:00",
}
```

Adapters MAY include extra make-specific fields under a `_raw` key —
those don't break the merger.

## Per-make checklist

When picking up a new make, run through this list:

- [ ] **Find the public VIN endpoint.** Manufacturer "owner" portals
      are the typical home (e.g. `owner.ford.com`, `owners.honda.com`).
      Confirm it works without login by opening it incognito with a
      known VIN. If login-only, set `supported = False` and stop.
- [ ] **Check `robots.txt`.** Reuse `runner._robots_for(host)` —
      respect `Disallow` lines for the path you'd hit.
- [ ] **Identify the data layer.** Most maker sites embed JSON in:
      - a `<script type="application/ld+json">` block (schema.org `Vehicle`/`Product`)
      - a `window.__INITIAL_STATE__` or `window.dataLayer` global
      - a `<script id="__NEXT_DATA__" type="application/json">` (Next.js)
      Prefer those over HTML scraping — they're stable across redesigns.
- [ ] **Locate the sticker link.** Common patterns:
      - `<a>` whose href contains `/window-sticker/` or `monroney`
      - JSON field `windowStickerUrl` / `stickerPdf`
      - Sticky button with `download` attribute pointing at `*.pdf`
- [ ] **Add the adapter file.** `carpapi/makers/<slug>.py` — slug matches
      `slug_for_filename(make)` in `api.make_info`.
- [ ] **Register it.** Append to `carpapi/makers/__init__.py`:
      ```python
      from .toyota import ToyotaAdapter
      REGISTRY["Toyota"] = ToyotaAdapter()
      ```
- [ ] **Add a test fixture.** Save one HTML snapshot at
      `carpapi/makers/fixtures/<slug>/sample_vdp.html` and write a
      pytest that runs `lookup()` against it. Fixtures avoid live HTTP
      in CI.
- [ ] **Verify on 5 real VINs.**
      ```bash
      for vin in $(psql ... -tAc "SELECT vin FROM public.listings WHERE make='Toyota' LIMIT 5"); do
        python -m carpapi.enrich enrich-vin "$vin"
      done
      ```
      Eyeball the resulting `maker_specs` against the actual maker pages.
- [ ] **Document quirks.** Add a `## Notes` section in the adapter file
      for anything weird (lazy-loaded fields, anti-bot measures, region
      gates).

## Status quirks worth noting per make

| make            | endpoint type            | typically supported? |
|-----------------|--------------------------|----------------------|
| Ford            | `www.ford.com` VIN URL   | yes (public) |
| Toyota          | Toyota Owners portal     | yes (public for VIN summary; sticker may need login) |
| Honda           | `owners.honda.com`       | partial — VIN summary public, full specs can be login-gated |
| Hyundai / Kia   | brand owner sites        | yes |
| Subaru          | `subaru.com/owners`      | yes |
| GM (Chevy/GMC/Buick/Cadillac) | gm.com VIN tools | yes (window stickers via GM dealer tool) |
| Stellantis (Chrysler/Dodge/Jeep/Ram/Fiat/Alfa Romeo) | Mopar Owner Connect | login-gated → `MakerLoginRequired` |
| VW / Audi / Porsche | brand owner sites    | login-gated → `MakerLoginRequired` |
| BMW / Mercedes / Lexus | varies by region   | unverified — start with `supported=False` until checked |

When in doubt, ship `supported=False` first. The orchestrator will
mark all matching listings `unsupported` and skip them — better than
a flaky "sometimes works" adapter.

## Throttling

Every adapter inherits the same throttle from `MakerAdapter.__init__`:
- `rate_limit_seconds = 1.5` between requests against the same host
- Single shared `requests.Session` (configure in `base.py`) — keep-alive
  reduces TLS handshake cost across runs

## Verification

```bash
# Adapter unit test (uses the fixture, no network)
pytest carpapi/makers/test_<slug>.py -v

# Live smoke test against 1 VIN
python -m carpapi.enrich enrich-vin <real_vin> --debug

# Status query — confirm new make moves from 'unsupported' to 'enriched'
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d carpapi -c "
  SELECT make, maker_enrich_status, count(*)
  FROM public.listings
  WHERE make = '<MakeName>'
  GROUP BY 1, 2"
```
