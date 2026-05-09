# Ranking Rules

## Current (MVP)
**Sort by `price_amount` ASC, NULLS LAST**, capped at `limit` (1–50).

Implementation: `services/api/carapi_api/query_exec.py::build_select` — single `order_by` clause.

This is the placeholder. It is not the product.

## Target (Phase B)
**Value-score ranking** based on cohort-relative price.

### Algorithm (sketch)
For each `(make, model, trim, year)` cohort with ≥ 50 listings:
1. Fit `price ~ mileage` regression (start with linear; revisit later).
2. Predicted price for a listing: `pred(listing) = β₀ + β₁ * mileage`.
3. `value_score = (pred - listed) / pred` — positive ⇒ underpriced vs. cohort.

For sparse cohorts (< 50): fall back to `(make, model, year)`, then `(make, model)`, then `(make)`. Below `(make)`: skip value-score, rank by price only.

### UX surface
Show the residual on the result card: "$2,400 below market" or "comparable pricing." Do not show negative scores as "$X above market" (creates a worse impression than competitor sites; keep it neutral).

### Sort options exposed
`sort_by` in `CarQuery` (TBD): `price_asc` (default), `price_desc`, `mileage_asc`, `value_score`, `newest`.

## Hard constraints on ranking
- Never rank by anything not in the canonical schema.
- Never let the LLM influence ranking score directly (only filter parameters).
- Ranking score must be deterministic for the same `(query, listing_set)`.
- Tie-breaker: lower `mileage`, then more recent `listing_updated_at`.

## Open questions
- Source-quality weighting: should listings from higher-priority sources rank higher? Probably no — leads to gaming. Keep ranking source-blind.
- Promoted/sponsored listings: out of scope for consumer MVP. Revisit for dealer-widget product.
