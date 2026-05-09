# Skill: generate-scraper

Use when bootstrapping a new extractor module from a sample HTML page or API payload.

## Pre-conditions
- Source is on the allow-list per [context/scraper-rules.md](../context/scraper-rules.md).
- One sample raw payload (HTML or JSON) representative of the source's listing detail page.
- For HTML sources: also have a search-results page sample so pagination can be modeled.

## Inputs to gather before generating
- `source_id`, `source_name`
- Sample input file path
- Auth requirements (API key? cookies? unauthenticated?)
- Pagination model (offset, cursor, page-number)
- Rate limit (req/sec, daily cap if any)

## Generation pattern
For an HTML source:
1. Identify the JSON-LD or structured-data block in the sample (cars listing sites often have `<script type="application/ld+json">` with Vehicle schema). Prefer this over CSS selectors when present — it's more stable.
2. Fall back to CSS selectors only when structured data is missing. Document each selector with the field it maps to.
3. Generate the extractor as `pipeline/carapi_pipeline/extractors/<source_id>.py` exposing `fetch_batch(settings) -> Iterator[dict]` that yields raw documents matching the source's native shape (NOT yet canonical).
4. Generate a per-source mapper: `pipeline/carapi_pipeline/normalize/<source_id>.py` (or method on a registry) that converts raw → canonical.
5. Generate fixture-based tests covering: happy path, missing-field handling, schema-drift detection (a fixture with one renamed field should fail loudly).

For an API source:
1. Wrap the API client thinly. Don't add features the source doesn't natively expose.
2. Respect documented rate limits + add 2× safety margin.
3. Use cursor/page tokens; never assume "list all."

## Anti-bot policy (HTML sources only)
- Acceptable: identifying user-agent, session cookies, normal request rate, respecting robots.txt.
- **Not acceptable:** CAPTCHA solvers, residential-proxy rotation specifically to evade blocks, JavaScript fingerprint randomization, browser-version spoofing.
- If a source actively blocks our identifiable scraper → stop. Don't escalate the cat-and-mouse.

## Don't
- Don't generate code from a single sample without representative variants. The first listing you pick is usually the simplest one.
- Don't bundle scraper credentials in the repo. Use settings env vars.
- Don't write parsing logic in the extractor — keep extraction (raw out) separate from normalization (canonical out).

## Done when
- `python -c "from carapi_pipeline.extractors.<source_id> import fetch_batch; ..."` returns the expected count from the fixture.
- Normalizer produces JSON-Schema-valid CarListing documents from each fixture variant.
- Scraping rules registry row added to [context/scraper-rules.md](../context/scraper-rules.md).
