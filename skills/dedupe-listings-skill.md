# Skill: dedupe-listings

Use when investigating duplicate listings, debugging missed dedups, or extending the dedup engine.

## Preflight — point at the real DB

```bash
# Dedup investigation reads + writes the canonical listings; query
# RDS, not the local :5433 snapshot. See skills/rds-first-skill.md.
source data/secrets/rds.env
```

## Read first
- [context/deduplication-rules.md](../context/deduplication-rules.md)
- [pipeline/carapi_pipeline/dedupe.py](../pipeline/carapi_pipeline/dedupe.py)
- [runbooks/dedupe-policy.md](../runbooks/dedupe-policy.md)
- [skills/rds-first-skill.md](rds-first-skill.md) — RDS-first policy

## Diagnostic workflow
When two rows that should be the same physical car ended up as separate listings:

1. **Pull both rows.** `SELECT id, source_id, external_id, vin, dedupe_key, make, model, year, price_amount, mileage, latitude, longitude FROM listings WHERE id IN (...);`
2. **Compare `vin`.** If both have a VIN and they don't match → they really are different cars. Stop.
3. **If only one has a VIN** → expected miss. The fingerprint key won't match a VIN key. Decide: should the no-VIN row backfill from the VIN row when the user submits the same listing later? (Currently no.)
4. **If neither has a VIN** → run `build_dedupe_key()` on both and inspect divergence. Common causes:
   - Price differs across the bucket boundary (e.g., $24,499 → bucket 48 vs $24,500 → bucket 49). Tighten or widen `price_bucket` divisor.
   - Mileage differs across bucket boundary. Same fix.
   - Geo: one row has lat/lng, other has region/city only. Geo key diverges. Decide: should geo fallback be more lenient?
   - Title/description differs enough that simhash hamming distance > 0 in the high bits used in the key. (Current key uses the full hash; consider top-N bits if false-misses are common.)

## Workflow for changing the dedup algorithm
1. Update `dedupe.py`.
2. Backfill: re-run `normalize.normalize_record()` + `build_dedupe_key()` for every listing, write new keys to a staging column, swap. Don't run partial — collisions become unpredictable.
3. Update [runbooks/dedupe-policy.md](../runbooks/dedupe-policy.md) summary table.
4. Update fixtures + tests in `pipeline/`.
5. Update [context/deduplication-rules.md](../context/deduplication-rules.md) if the rule changes user-facing behavior.

## Don't
- Don't loosen dedup matching to "fix" missed dedups — false-merges are worse than false-splits (we'd silently overwrite a different car's data).
- Don't manually `UPDATE listings SET dedupe_key = ...` in production — bypasses pipeline invariants.

## Done when
- Backfill complete (no rows with old-format keys).
- Test fixtures cover the new edge case.
- Manual: pick 5 random clusters, verify they're correctly grouped.
