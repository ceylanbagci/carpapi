# Skill: enrich-from-maker

The cold loop of the two-track enrichment pipeline. For each listing
where `maker_specs IS NULL` (or other specific empty fields), look the
VIN up on the manufacturer's USA website, parse the canonical spec
data, locate the window-sticker PDF, parse it, and persist everything
in a single atomic update. **One-time per VIN — never re-run on rows
that already have data.**

## When to use this skill

Trigger when working on any of:
- "enrich the listing", "fill in missing trim/drivetrain/MSRP"
- the maker-site adapter pattern (`carpapi.makers.*`)
- the orchestrator that ties adapter → window-sticker parser → DB
- backfilling spec data, the cold loop, the one-time enrichment pass
- diagnosing why a listing has `maker_enrich_status='failed'` or `'unsupported'`

Do **not** use this skill for the hot loop / price refresh — see
[refresh-prices-skill](refresh-prices-skill.md).

## Read first

- [carpapi/makers/base.py](../carpapi/makers/base.py) — `MakerAdapter` ABC and the `MakerLookup` dataclass
- [carpapi/makers/__init__.py](../carpapi/makers/__init__.py) — the `REGISTRY: dict[str, MakerAdapter]` mapping make → adapter
- [carpapi/makers/ford.py](../carpapi/makers/ford.py) — the canonical reference adapter
- [carpapi/enrich/orchestrator.py](../carpapi/enrich/orchestrator.py) — pulls it all together
- [carpapi/enrich/window_sticker.py](../carpapi/enrich/window_sticker.py) — markitdown PDF → JSON
- [pipeline/carapi_pipeline/pii.py](../pipeline/carapi_pipeline/pii.py) — PII scrubber to apply to the markdown before persisting

## Idempotency rule (instruction #5)

Every step in the cold loop guards on emptiness:

```python
# Skip the maker-site lookup if specs already exist
if listing.maker_specs is not None:
    return

# Skip the sticker fetch if we already have parsed JSON
if listing.window_sticker is not None:
    return  # only the maker-spec scrape will run, sticker is left alone
```

After a successful run, set:
- `maker_url` (the page we scraped)
- `maker_specs` (JSONB)
- `window_sticker_url` (the PDF location, even if parse fails)
- `window_sticker` (parsed JSONB) — NULL if PDF unavailable
- `maker_enriched_at = now()`
- `maker_enrich_status = 'enriched'` (or one of the failure states)

A second invocation of `enrich-vin <same-vin>` is a no-op.

## Status values

| status            | meaning |
|-------------------|---------|
| `pending` (NULL)  | never tried |
| `enriched`        | maker_specs populated successfully |
| `unsupported`     | adapter returned `MakerUnsupported` (no public VIN endpoint) |
| `login_required`  | endpoint exists but requires auth — we don't bypass |
| `failed`          | network/parse error, retry-eligible (manual flag for now) |

`unsupported` and `login_required` are sticky — the orchestrator filters
them out of `enrich-stale` runs. `failed` rows can be re-attempted by
explicitly running `enrich-vin <vin>`.

## Orchestrator flow

```python
def enrich_one(listing: Listing) -> EnrichResult:
    if listing.maker_specs is not None:
        return EnrichResult.skip("already enriched")

    adapter = REGISTRY.get(listing.make)
    if adapter is None or not adapter.supported:
        update_listing(listing.id, maker_enrich_status='unsupported')
        return EnrichResult.skip("no adapter")

    try:
        lookup = adapter.lookup(listing.vin)
    except MakerLoginRequired:
        update_listing(listing.id, maker_enrich_status='login_required')
        return EnrichResult.skip("login required")
    except Exception as e:
        update_listing(listing.id, maker_enrich_status='failed', maker_enrich_error=str(e))
        return EnrichResult.fail(str(e))

    sticker = None
    if lookup.sticker_url and listing.window_sticker is None:
        try:
            sticker = parse_window_sticker(lookup.sticker_url)
        except Exception as e:
            log.warning("sticker parse failed for %s: %s", listing.vin, e)

    save_enrichment(
        listing_id=listing.id,
        maker_url=lookup.maker_url,
        maker_specs=lookup.specs,
        window_sticker_url=lookup.sticker_url,
        window_sticker=sticker,
        status='enriched',
    )
    return EnrichResult.ok()
```

## Throttling

- Reuse the rate-limit helper from [carpapi/scrapers/runner.py](../carpapi/scrapers/runner.py): `>= 1.5s` between requests against the same maker host.
- Robot check: `_robots_allows(maker_host, vin_lookup_path)` before every fetch.
- User-Agent: `CarPapiBot/0.1 (+contact email)` per existing convention.

## Common queries

```sql
-- Counts by enrichment status
SELECT make, maker_enrich_status, count(*)
FROM public.listings
GROUP BY 1, 2
ORDER BY 1, 2;

-- Pending listings ready for enrich-stale
SELECT count(*) FROM public.listings
WHERE maker_specs IS NULL
  AND maker_enrich_status IS DISTINCT FROM 'unsupported'
  AND maker_enrich_status IS DISTINCT FROM 'login_required';

-- Make coverage (which makes have at least one enriched row)
SELECT make, count(*) FILTER (WHERE maker_specs IS NOT NULL) AS enriched,
       count(*) AS total
FROM public.listings
GROUP BY 1
ORDER BY total DESC;
```

## Verification

See [the plan](../../../.claude/plans/so-there-are-mostly-cuddly-kahan.md#verification-plan)
sections 3–5 (Ford adapter, idempotency, unsupported make).
