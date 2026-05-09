# Skill: query-planner

Use when extending the natural-language → CarQuery translation layer.

## Authoritative
- Schema: [schema/car_query.schema.json](../schema/car_query.schema.json)
- Current planner (regex MVP): [services/api/carapi_api/orchestrator.py](../services/api/carapi_api/orchestrator.py)
- Executor: [services/api/carapi_api/query_exec.py](../services/api/carapi_api/query_exec.py)

## Hard contract
- Output is a dict matching the CarQuery JSON Schema. The schema is the allowlist — fields not in it are silently dropped.
- Output is validated via `validate_car_query()` before SQL is built. Build never sees free-form text.
- The model never returns SQL. Only filter parameters.
- Operators allowlist is implicit in the schema field names: `*_min`, `*_max`, equality on `make/model/region`, range on `radius_miles`. No `LIKE`, no raw substring search, no joins.

## When to extend
| Want | How | Don't |
|---|---|---|
| New filter (e.g., `transmission`) | Add to schema → add to executor → add to planner extraction | Add a free-form `extra_filter` field — defeats the point of the schema |
| Better make/model recognition | Replace hardcoded regex with a normalized make/model dictionary loaded from the listings table | Train a NER model (overkill until 100+ supported makes) |
| LLM-based planning | Replace `plan_car_query()` with a Bedrock/Claude call using **structured tool output** (tool definition = CarQuery schema) | Let the LLM emit a JSON blob and parse it loosely — rely on tool-use validation |

## LLM planner pattern (when shipped)
1. Use the cheap small model (Haiku / Llama-3-8B) for parsing — accuracy > nuance here.
2. System prompt = the CarQuery schema description + 5–10 few-shot `(message, expected_query)` pairs from `eval/fixtures/`.
3. Force tool use: model must return a function call to `search_cars(**params)` whose params match the schema.
4. Cache by hash of the user message (many users ask identical things).
5. On parse failure: fall back to the regex planner (always-available baseline).

## Don't
- Don't add free-form text fields that bypass the schema (e.g., `note: "user wants a fun car"`). Push the LLM to map vibes → concrete filters.
- Don't expand operator vocabulary. The schema's expressive power is intentionally limited.
- Don't let the planner run when validation fails — return an error or fall back to broad search; never run an unvalidated dict.

## Done when
- New filter passes through end-to-end: chat input → planner extracts it → schema validates → executor applies it → result count changes accordingly.
- Eval set in `eval/fixtures/queries.jsonl` covers the new filter (≥ 3 cases including a negative).
