# CarPapi — Project Overview

Loaded into AI tool context. Update when scope or hard rules change.

## What it is
ChatGPT-like used-car search. Users ask in natural language; the system returns ranked listings with citations (stable IDs + source URLs) plus a short prose explanation. Inventory truth lives in Postgres, not in model weights.

## Architecture in one line
Sources → ingest → canonical Postgres + pgvector → JSON-filter query planner → validated SQL → ranked results → chat synthesis → web/mobile UI.

Authoritative system design: [architecture.md](../architecture.md). Stack rationale: [STACK_DECISION.md](../STACK_DECISION.md).

## Two products, one backend
1. **Consumer chat** — natural-language car search. Builds first to validate the engine.
2. **Dealer widget** — same backend embedded on dealer inventory sites for monthly subscription. Builds after consumer is proven.

## In scope (MVP)
- Used-car listings from licensed feeds or sanctioned public sources
- US-only (specific geographic scope is open — see plan)
- Ranking by listed price (MVP) → value-score regression (Phase B)
- Natural-language query → structured filters → ranked results

## Out of scope (MVP)
- New-car configurator / OEM ordering
- Financing applications, credit checks, dealer F&I
- Trade-in valuations
- Vehicle history report integrations (consider post-MVP)
- Fine-tuning a chat model
- International markets

## Hard rules — never break these
- The LLM never controls the database directly. JSON filter → JSON-Schema validation → query builder → parameterized SQL.
- No scraping of sources whose ToS prohibit automated access.
- No fine-tuning before there is real user data.
- Daily monitoring report is a first-class deliverable, not an ops afterthought.
- Inventory truth is the database, not the model. Listings shown to users must come from `listings` rows with stable `id` and `listing_url`.

## Open decisions (gating real progress)
1. Data source: licensed feed (Marketcheck/AutoDev/VinAudit) vs. sanctioned-only scraping. **Single biggest unresolved decision.**
2. Geographic scope: US-wide vs. one metro for MVP.
3. Private-party vs. dealer-only.
4. Monetization shape (affects chat UX and dealer-widget priority).

Reference: design critique at `~/.claude/plans/analyze-this-and-update-peppy-ullman.md`.
