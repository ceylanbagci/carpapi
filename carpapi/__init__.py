"""CarPapi top-level package: AI-cache, scrapers, and post-run monitoring.

This is intentionally separate from the existing `carapi_pipeline` package
(under pipeline/carapi_pipeline/) which holds the ingest/normalize/dedupe
pipeline. The split is policy-driven:

- `carapi_pipeline.*` — runs DURING ingest. Pure data-engineering code,
  no LLM calls. Owned by the data team.
- `carpapi.*` — runs AROUND ingest. The AI-cache layer (single entry
  point for all Claude calls), scrapers (zero-AI per project policy),
  and post-run statistical monitors. Owned by the platform team.

If you add new code that calls Claude/Bedrock/any LLM, route it through
`carpapi.cache.token_cache.TokenCache` — see context/ai-cache-rules.md.
"""

__version__ = "0.1.0"
