# Skill: refresh-prices

Refresh `public.listings.price_amount` (and only that) by re-visiting each
dealer's inventory. The hot loop of the two-track enrichment pipeline —
runs frequently, touches no spec data.

## Preflight — point at the real DB

```bash
# Price-refresh writes public.listing_price_history rows on RDS.
# See skills/rds-first-skill.md for the policy.
source data/secrets/rds.env
```

## When to use this skill

Trigger when working on any of:
- "the price scraper", "the dealer scraper", "the hot loop"
- updating `price_refreshed_at`
- diagnosing stale prices in the listings table
- adding a new dealer site to the price-refresh rotation

Do **not** use this skill for spec/feature data — that's the cold loop
([enrich-from-maker-skill](enrich-from-maker-skill.md)).

## Read first

- [carpapi/scrapers/adapters/dealer_dot_com.py](../carpapi/scrapers/adapters/dealer_dot_com.py) — the existing Dealer.com adapter; price-only mode trims `parse_vdp()` to extract just `vin + listing_url + price_amount + currency`
- [carpapi/scrapers/runner.py](../carpapi/scrapers/runner.py) — `_robots_for()`, `_robots_allows()`, the `rate_limit_seconds` throttle. Reuse, do not reinvent.
- [pipeline/carapi_pipeline/pipeline.py](../pipeline/carapi_pipeline/pipeline.py) — `IngestRepo.start_run()` / `.finish_run()` for run tracking
- [carpapi/db/schema.sql](../carpapi/db/schema.sql) — `listings.price_amount`, `price_refreshed_at` (added by the enrichment plan)

## Inputs

- `--dealer SLUG` (optional) — restrict to one dealer. Default: every row in `public.dealers WHERE status='active'`.
- `--max-rps` (default `1.5`) — enforced per-host as in `runner.py`.
- `--dry-run` — log what would change but skip the UPDATE.

## What this scraper does NOT do

The hot loop is intentionally minimal. It must NOT touch:

- `description`, `title`, `features`, `images`, `body_style`, `trim`, `mileage`
- `maker_url`, `maker_specs`, `window_sticker`, `window_sticker_url`
- `maker_enriched_at`, `maker_enrich_status`

Why: those fields are the cold loop's responsibility and change rarely.
Updating them on every price refresh would either thrash the DB or risk
overwriting good cold-loop data with shallow VDP parses.

## Output structure

Per run, write one row to `ingest.ingest_runs` with:
- `source_id = 'price-refresh'`
- `run_kind = 'scheduled'` (or `'manual'` for one-off)
- `counts = {visited: N, updated: M, unchanged: K, errors: E}`
- `status = 'success' | 'partial' | 'failed'`

Per listing:
- `UPDATE public.listings SET price_amount = $1, price_refreshed_at = now() WHERE vin = $2 AND price_amount IS DISTINCT FROM $1`
- Skip rows where the price is unchanged (use `IS DISTINCT FROM` so NULLs work).

## Throttling

- One inventory page request per dealer at a time (existing `runner.py` semantics).
- Sleep `rate_limit_seconds` between VDP fetches against the same host.
- Honor `Retry-After` on 429 responses.
- Stop early on a 403 from a given host and log to `ingest.rejection_log`.

## Verification

```bash
# Pick one dealer, dry run
python -m carpapi.enrich refresh-prices --dealer ford-of-springfield --dry-run

# Actual run
python -m carpapi.enrich refresh-prices --dealer ford-of-springfield

# Confirm only price + price_refreshed_at changed
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d carpapi -c "
  SELECT vin, price_amount, price_refreshed_at, maker_enriched_at
  FROM public.listings
  WHERE source_id = 'ford-of-springfield'
  ORDER BY price_refreshed_at DESC LIMIT 5"
```

`maker_enriched_at` should be unchanged for any row that was already enriched.
