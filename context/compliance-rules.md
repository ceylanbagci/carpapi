# Compliance Rules

## Data-source legality
See [scraper-rules.md](scraper-rules.md). One-line summary: licensed feeds and ToS-permitted public sources only. CFAA + state computer-trespass exposure is real — do not scrape ToS-prohibited sites, even if "everyone does it."

## PII handling
Listings may carry seller PII (`seller_name`, occasionally embedded phone/email in `description`). Policy:
- **Dealer listings:** seller name is business info; safe to store and display.
- **Private-party listings:** treat seller name as PII. Store, but redact phone/email patterns from `description` before persistence (regex strip in `normalize.py`). Do not display seller PII in chat responses.
- **Never** persist plaintext credit-card or financing data (we don't collect it; if a source ever sends it, drop the field at normalization).

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
