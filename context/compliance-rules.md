# Compliance Rules

## Data-source legality
See [scraper-rules.md](scraper-rules.md). One-line summary: licensed feeds and ToS-permitted public sources only. CFAA + state computer-trespass exposure is real — do not scrape ToS-prohibited sites, even if "everyone does it."

## PII handling
Listings may carry seller PII (`seller_name`, occasionally embedded phone/email in `description`). Policy:
- **Dealer listings:** seller name is business info; safe to store and display.
- **Private-party listings:** treat seller name as PII. Store, but redact phone/email patterns from `description` before persistence (regex strip in `normalize.py` via [carpapi_pipeline/pii.py](../pipeline/carapi_pipeline/pii.py)). Do not display seller PII in chat responses.
- **Never** persist plaintext credit-card or financing data (we don't collect it; if a source ever sends it, drop the field at normalization).

## Raw data must NEVER reach an LLM
Restated as a hard rule (with implementation backing): the only path from CarPapi data to Claude/Bedrock/any LLM is through [carpapi/cache/token_cache.py](../carpapi/cache/token_cache.py), and the cache's PII guard ([carpapi/cache/pii_guard.py](../carpapi/cache/pii_guard.py)) rejects prompts containing:
- 17-character VINs
- US phone numbers
- Email addresses
- Street addresses (US format)
- SSN-shaped strings (defensive)

The rejection raises `PIIInPromptError` *before* the prompt hashes or hits the wire. Anonymized metadata only — make/model/year/trim, body style, region, price band. See [ai-cache-rules.md](ai-cache-rules.md) for the full architecture.

## Data-subject rights
- **CCPA / state-equivalent deletion requests:** route to a manual playbook (TBD). Until built, log requests in a tracker; do not auto-delete.
- **Retention:** raw scrape artifacts in S3 → 90 days then archive/delete. Normalized listings → keep until source marks sold + 30 days.

## US-only MVP
Listings outside US, Canada, Mexico are filtered at ingest. Cross-border privacy regimes (GDPR, etc.) are out of scope until international expansion is on the roadmap.

## ToS for the CarPapi product itself
- Public terms must disclose that listing data is sourced from third parties and may be stale or contain errors.
- Public terms must disclose that the assistant is AI-generated.
- "Best value" / "below market" framings are opinions, not appraisals — disclose accordingly.

## Logging policy
- User chat messages → log retention 30 days, then aggregate/anonymize.
- Don't log PII the user volunteers (e.g., they paste their own VIN). Strip 17-char VIN patterns from chat logs before persistence.

## When this list grows
Each new compliance domain (e.g., adding financing data, dealer leads, international data) gets its own subsection here. Update [project-overview.md](project-overview.md) hard-rules section if a new constraint is project-wide.
