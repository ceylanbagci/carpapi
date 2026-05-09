# AI Cache Rules (mandatory)

> Policy file. Loaded into every AI tool's context. Update only when the rule itself changes — the implementation reference is in code.

## The hard rule

**No component in CarPapi calls Claude (or any LLM) directly.** Every prompt must pass through `carpapi.cache.token_cache.TokenCache`. There are no exceptions: not for one-off scripts, not for prototype code, not for "just testing." If you find yourself reaching for `anthropic.Anthropic()`, `boto3.client('bedrock-runtime')`, or any other LLM client outside `TokenCache`, stop — wire it through the cache instead.

## Architecture

```
Component → TokenCache → Claude / Bedrock
                ↑
         (hit: return cached response)
         (miss: PII-check, compress, call, store)
```

Authoritative implementation: [carpapi/cache/token_cache.py](../carpapi/cache/token_cache.py).

## What the cache does on every call

1. **PII guard** — refuses prompts containing VINs, US phones, emails, street addresses, SSN-shaped strings. See [carpapi/cache/pii_guard.py](../carpapi/cache/pii_guard.py). Raises `PIIInPromptError` before the prompt hashes or hits the wire.
2. **Optional compression** — when `llmlingua` is installed, runs LLMLingua + HTML strip to cut tokens 2–5×. See [carpapi/cache/llmlingua_compressor.py](../carpapi/cache/llmlingua_compressor.py).
3. **Hash → cache key** — `sha256(json({"p": compressed_prompt, "m": model, "t": max_tokens}))`. The hash is over the compressed form, not the raw prompt.
4. **Backend lookup** — SQLite for development (default at `./data/token_cache.sqlite`), Redis for production via `RedisBackend(url)`.
5. **Hit** → return cached response. No LLM call. No cost.
6. **Miss** → invoke the injected `llm_call`, store result with TTL, return.

## What MUST NOT enter a prompt

Even processed/anonymized metadata is preferable to raw fields. Specifically:

- **VINs** — anonymize to make/model/year/trim before sending.
- **Customer phone numbers, emails, mailing addresses** — never. Drop these fields server-side before constructing any prompt.
- **Internal database IDs that map to external accounts** — replace with hashed surrogates if the LLM needs continuity.
- **Raw scraped HTML containing tracking pixels / dealer credentials** — strip via `strip_html_and_boilerplate()` first.

The PII guard enforces a subset of this automatically; the rest is on the caller.

## TTLs

- Default: 24 hours (`DEFAULT_TTL_SECONDS`).
- Override per call via `TokenCache.query(prompt, ttl=...)`.
- Sane buckets:
  - Classification of stable inputs (dealer type, body style): **7 days**.
  - User-query parsing (regex/structured extraction): **24 hours**.
  - Free-form synthesis on changing inventory: **1 hour** at most.

## max_tokens defaults (guideline 3)

| Skill type | max_tokens |
|---|---|
| Classification | 256 |
| Extraction | 512 |
| Synthesis | 1024 |

Pass via `TokenCache.query(..., max_tokens=256)`. Don't let max_tokens float on its own — every skill should declare an explicit ceiling.

## Pre-prompt prep (always, even when cache misses)

Before constructing the prompt:
- Strip HTML tags and boilerplate (`strip_html_and_boilerplate()` is always available).
- Use structured templates with explicit field boundaries; avoid free-form prose where a list will do.
- Pass JSON Schemas as the contract for tool use, not English descriptions of "what you should return."
- Quote literal user input; don't interpolate untrusted strings into instructions.

## How to wire the LLM client

`TokenCache` doesn't ship with a Bedrock or Anthropic client — it accepts one via dependency injection. The pattern:

```python
from carpapi.cache.token_cache import TokenCache, SQLiteBackend
from carpapi.cache.llmlingua_compressor import make_compressor

def call_bedrock(prompt: str, max_tokens: int | None, model: str | None) -> str:
    # Whatever boto3 / anthropic invocation you need.
    ...

cache = TokenCache(
    backend=SQLiteBackend(),
    compressor=make_compressor(rate=0.5),
    llm_call=call_bedrock,
)
response = cache.query(
    "Classify dealer type from this metadata: ...",
    skill="classify-dealer",
    max_tokens=256,
    ttl=7 * 24 * 3600,
)
```

The `call_bedrock` closure is the *only* place in the codebase where a real LLM client lives.

## What to do if the rule blocks you

If you genuinely need direct LLM access for something the cache can't model, **don't bypass — extend**. File an issue, propose the new TokenCache method, get review. Bypasses normalize and the rule erodes.

## Verification

- Cache eval: `python eval/run_token_cache_eval.py` — checks hit/miss/PII rejection.
- Production: `cache.stats` exposes hit count, miss count, PII rejections, and per-skill breakdowns. Log this nightly.
