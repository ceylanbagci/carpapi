from __future__ import annotations

"""LLM-driven query planner.

Pipeline:
  user message
    → Claude Haiku via TokenCache (tool use)
    → JSON CarQuery (validated by carpapi_api.query_exec.car_query_schema)
    → Filters dataclass for carpapi.rag.retrieve.*

Fallback: if the LLM call fails or returns an invalid plan, we use the
existing regex planner (carapi_api.orchestrator.plan_car_query) so the
pipeline always has *some* plan to work with.

Per architecture.md and skills/query-planner-skill.md:
  - The model never returns SQL; only filter parameters.
  - Schema is the allowlist — unknown fields are dropped.
  - Cache by the message hash; many users ask the same things.
"""

import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import jsonschema

from carpapi.cache.token_cache import TokenCache, PIIInPromptError
from carpapi.rag.retrieve import Filters

log = logging.getLogger("carpapi.rag.planner")

# Re-use the existing JSON Schema as the contract.
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / "car_query.schema.json"
with _SCHEMA_PATH.open(encoding="utf-8") as fh:
    _CAR_QUERY_SCHEMA = json.load(fh)

_SYSTEM_PROMPT = """You are CarPapi's query planner.

Translate the user's natural-language car search into a JSON object that
matches this exact schema (CarQuery):

  make: string|null            (e.g., "Toyota", "Honda")
  model: string|null           (e.g., "Camry", "CR-V")
  body_style: string|null      (e.g., "SUV", "Sedan", "Truck", "Coupe")
  year_min: integer|null       (lower bound, inclusive)
  year_max: integer|null       (upper bound, inclusive)
  price_min: number|null
  price_max: number|null       (upper bound; e.g., "$25k" → 25000)
  mileage_max: number|null     (in miles)
  region: string|null          (US state code, e.g. "NJ")
  zip_code: string|null        (5-digit ZIP for radius search)
  radius_miles: number|null    (1-500, used with zip_code)
  limit: integer (1-50, default 10)
  semantic_query: string|null  (verbatim user message for vector search)

Rules:
  - Output ONLY the JSON object. No prose, no markdown fences.
  - Use null for fields you cannot determine.
  - "under $25k" → price_max: 25000. "30k miles" → mileage_max: 30000.
  - Two-letter state codes (NJ, NY, CA, etc.) in region.
  - Always set semantic_query to the user's verbatim message — the
    backend will use it for vector ranking when filters are sparse.
  - Never invent prices, VINs, or facts about cars; only translate
    what the user wrote.
"""


@dataclass
class PlanResult:
    car_query: dict[str, Any]
    filters: Filters
    rationale: str
    source: str            # "llm" | "regex-fallback"


def _parse_llm_output(text: str) -> Optional[dict[str, Any]]:
    """Pull a JSON object out of the model's response.

    Strips markdown fences when the model ignores instructions and adds
    them anyway. Returns None on parse failure.
    """
    s = (text or "").strip()
    if s.startswith("```"):
        # ```json ... ``` or ``` ... ```
        s = s.split("```", 2)
        if len(s) >= 2:
            s = s[1]
        else:
            s = ""
        # the language tag (if any) is the first line
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0] if "```" in s else s
    s = s.strip()
    if not s:
        return None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        log.debug("planner: model output didn't parse: %r", text[:200])
        return None
    return obj if isinstance(obj, dict) else None


def _normalize(obj: dict[str, Any]) -> dict[str, Any]:
    """Coerce common slips before schema validation.

    The model occasionally emits price as a string with "$" or year as a
    string. Schema validation is strict; normalize first.
    """
    out = dict(obj)
    for k in ("year_min", "year_max"):
        v = out.get(k)
        if isinstance(v, str) and v.isdigit():
            out[k] = int(v)
    for k in ("price_min", "price_max", "mileage_max", "radius_miles"):
        v = out.get(k)
        if isinstance(v, str):
            stripped = v.replace("$", "").replace(",", "").strip()
            try:
                out[k] = float(stripped)
            except ValueError:
                out[k] = None
    if "zip_code" in out and isinstance(out["zip_code"], int):
        out["zip_code"] = f"{out['zip_code']:05d}"
    # Schema allows unknown keys to be silently dropped — strip them.
    allowed = set(_CAR_QUERY_SCHEMA.get("properties", {}).keys())
    return {k: v for k, v in out.items() if k in allowed}


def _car_query_to_filters(cq: dict[str, Any]) -> Filters:
    return Filters(
        make=cq.get("make") or None,
        model=cq.get("model") or None,
        body_style=cq.get("body_style") or None,
        year_min=cq.get("year_min"),
        year_max=cq.get("year_max"),
        price_min=cq.get("price_min"),
        price_max=cq.get("price_max"),
        mileage_max=cq.get("mileage_max"),
        region=cq.get("region") or None,
        require_price=True,
    )


def _regex_fallback(message: str) -> PlanResult:
    """Use the existing regex planner so we always have *some* plan."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))
    from carapi_api.orchestrator import plan_car_query  # noqa: PLC0415

    cq, rationale = plan_car_query(message)
    # Ensure semantic_query is present
    cq = dict(cq)
    cq.setdefault("semantic_query", message)
    return PlanResult(
        car_query=cq,
        filters=_car_query_to_filters(cq),
        rationale=rationale,
        source="regex-fallback",
    )


def plan(
    message: str,
    *,
    cache: TokenCache,
    model: str = "haiku",
    ttl_seconds: int = 24 * 3600,
) -> PlanResult:
    """Plan a user message into validated CarQuery filters."""
    if not message or not message.strip():
        return PlanResult(
            car_query={"limit": 10, "semantic_query": ""},
            filters=Filters(require_price=True),
            rationale="empty message",
            source="regex-fallback",
        )

    prompt = (
        _SYSTEM_PROMPT
        + "\n\nUser message:\n" + message.strip()
        + "\n\nReturn only the JSON object."
    )
    try:
        raw = cache.query(
            prompt,
            skill="query-planner",
            model=model,
            max_tokens=400,
            ttl=ttl_seconds,
        )
    except PIIInPromptError as exc:
        log.warning("planner blocked by PII guard: %s", exc)
        return _regex_fallback(message)
    except Exception as exc:  # noqa: BLE001
        log.warning("planner LLM call failed: %s", exc)
        return _regex_fallback(message)

    parsed = _parse_llm_output(raw)
    if parsed is None:
        return _regex_fallback(message)

    normalized = _normalize(parsed)
    normalized.setdefault("semantic_query", message)

    try:
        jsonschema.validate(normalized, _CAR_QUERY_SCHEMA)
    except jsonschema.ValidationError as exc:
        log.warning("planner output failed schema: %s", exc.message)
        return _regex_fallback(message)

    rationale_parts: list[str] = []
    if normalized.get("make") or normalized.get("model"):
        rationale_parts.append(
            f"Filtering by {normalized.get('make') or ''} {normalized.get('model') or ''}".strip()
        )
    if normalized.get("body_style"):
        rationale_parts.append(f"body {normalized['body_style']}")
    if normalized.get("price_max"):
        rationale_parts.append(f"price ≤ ${normalized['price_max']:,.0f}")
    if normalized.get("mileage_max"):
        rationale_parts.append(f"mileage ≤ {normalized['mileage_max']:,.0f} mi")
    if normalized.get("region"):
        rationale_parts.append(f"region {normalized['region']}")
    if normalized.get("zip_code") and normalized.get("radius_miles"):
        rationale_parts.append(
            f"within {normalized['radius_miles']:.0f} mi of {normalized['zip_code']}"
        )
    rationale = "; ".join(rationale_parts) or "Broad search"

    return PlanResult(
        car_query=normalized,
        filters=_car_query_to_filters(normalized),
        rationale=rationale,
        source="llm",
    )
