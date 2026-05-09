# Scraper Rules

## Hard rule: zero AI in the scraping layer

**No LLM calls during data extraction.** Not for parsing, not for field disambiguation, not for "just this one tricky field." Scrapers are pure-Python statistical/structured tools. AI gets involved only in downstream query planning (and even then only via [ai-cache-rules.md](ai-cache-rules.md)).

### Approved stack
| Tool | Role |
|---|---|
| `requests` | Static HTTP |
| `BeautifulSoup4` | HTML parsing, JSON-LD extraction |
| `lxml` | Fast XML/HTML parsing where speed matters |
| `Selenium` | JS-rendered pages, pagination, dynamic content |

### Prohibited in this layer
- Any Claude / OpenAI / Bedrock / Gemini / generic LLM API call.
- Paid AI enrichment services.
- AI-driven browser automation (`browser-use`, Stagehand, etc.).
- Heuristic "AI" wrappers that internally call an LLM.

### Why
Scrape failures should be diagnosed by reading code and metrics, not by asking an LLM what went wrong. AI in this layer adds cost, hides bugs, and makes the pipeline non-deterministic.

## Code locations
- Approved scrapers: [carpapi/scrapers/](../carpapi/scrapers/) — `google_search.py` (Google Custom Search API client), `dealership_page.py` (BS4 + Selenium harness), `dealerrater.py` (stub — ToS-gated).
- Post-run statistical monitor: [carpapi/monitor/scrape_monitor.py](../carpapi/monitor/scrape_monitor.py) — pure threshold checks; no AI.
- Ingest stub for fixtures: [pipeline/carapi_pipeline/scraper_stub.py](../pipeline/carapi_pipeline/scraper_stub.py).

## Status
Live scrapers are NOT shipped. `pipeline/carapi_pipeline/scraper_stub.py` returns the bundled `fixtures/sample_listings.json`. Do not write production scrapers until the data-source decision lands (see [project-overview.md](project-overview.md) → Open decisions #1).

## Data-source policy
Allowed inputs to `pipeline.run_ingest_batch()`:
- **Licensed APIs** (Marketcheck, AutoDev, VinAudit, eBay Motors API) — preferred.
- **Sanctioned partner feeds** (dealer XML/CSV with written agreement).
- **Public sources whose ToS permit automated access** — verify per-source, document in this file when added.

Disallowed:
- Sources whose ToS prohibit automated access (AutoTrader, Cars.com, CarGurus, Edmunds, TrueCar, Carvana, Vroom default to this).
- Bypassing anti-bot defenses (CAPTCHA solvers, fingerprint randomization beyond stock browser, residential proxy block-evasion).
- Aggregating from data brokers without explicit license.

## When live scrapers ship
- Per-source rate limits documented in this file plus enforced in code.
- `robots.txt` checked at runtime; respect `Disallow` even when ToS allows.
- Backoff on HTTP 429 / 403 / 503 — exponential, max ~30 min.
- Concurrency cap per source (start at 1; increase only after observation).
- Persist raw artifact to S3 via `raw_store.write_raw()` BEFORE normalization. Lineage required.
- One extractor module per source, regression-fixture-tested.

## Failure handling
See runbook: [runbooks/scrape-failures.md](../runbooks/scrape-failures.md).

## Daily schedule
See runbook: [runbooks/daily-schedule.md](../runbooks/daily-schedule.md). EventBridge per source, staggered, emits EMF metrics.

## Per-source registry (populate when sources are added)
| source_id | source_name | type | rate_limit | status | notes |
|---|---|---|---|---|---|
| `demo_dealer` | Demo Dealer Feed | fixture | n/a | active | bundled sample_listings.json |
