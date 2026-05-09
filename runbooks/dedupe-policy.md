# Dedupe policy

Canonical keys and merge behavior are defined in code (`carapi_pipeline.dedupe`) and [schema/README.md](../schema/README.md).

## Summary

| Condition | Primary key | Survivorship |
|-----------|-------------|----------------|
| VIN present | Normalized VIN (17 chars) | Newest `listing_updated_at` wins |
| No VIN | Fingerprint: make, model, year, price_bucket, mileage_bucket, geo hash, simhash(title+desc) | Higher **source_priority**; tie-break by freshness |

## Manual overrides

- Duplicate clusters surfaced by QA: store **merge_decision** auditable row (future admin API).
