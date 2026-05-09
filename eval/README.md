# Eval — pure-function regression suites

Three independent evals that gate changes to the pure-Python core. None require a DB or external services.

| Suite | Runner | Covers |
|---|---|---|
| Query planner | `run_planner_eval.py` | NL message → CarQuery filters (orchestrator regex MVP; same fixtures will gate the LLM planner) |
| Zero-result relaxation | `run_relaxation_eval.py` | `relax_query()` priority order: radius → price → mileage → year |
| PII redaction (pipeline) | `run_pii_redaction_eval.py` | Phone + email patterns stripped from free-text fields before persistence |
| Token cache | `run_token_cache_eval.py` | `TokenCache` hit/miss, PII guard rejection, missing-`llm_call` failure mode, key varies by model/max_tokens |
| Scrape monitor | `run_scrape_monitor_eval.py` | Statistical thresholds: zero records, null-rate ceilings, within-batch dup rate, HTTP error rate |

## Running

From the repo root:

```bash
for f in eval/run_*_eval.py; do python "$f" || break; done
```

Or individually:

```bash
python eval/run_planner_eval.py
python eval/run_relaxation_eval.py
python eval/run_pii_redaction_eval.py
python eval/run_token_cache_eval.py
python eval/run_scrape_monitor_eval.py
```

Each exits 0 on full pass, 1 on any failure (mismatched fields printed).

## Fixture format

`fixtures/queries.jsonl` — one JSON object per line:

```json
{"message": "Camry under $25k near 07302", "expected": {"make": "Toyota", "model": "Camry", "price_max": 25000, "zip_code": "07302"}}
```

The runner asserts every key in `expected` is present in the planner output with the same value. Extra fields in the actual output are ignored — partial assertions only.

## Adding cases

When extending the planner, add ≥ 3 cases for the new behavior including a negative case (input that should NOT trigger it). Keep wording natural — the eval should reflect how real users phrase things, not the regex authors' idioms.

## What this is not

- Not a unit test for `query_exec.py` — that needs a DB.
- Not an end-to-end test — the API/streaming layer is not exercised here.
- Not a quality measure — passing the eval is necessary, not sufficient. Real-traffic logging is the eventual ground truth.
