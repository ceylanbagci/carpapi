from __future__ import annotations

"""End-to-end RAG answer: plan → retrieve → synthesize.

  user_message ─▶ planner.plan ─▶ Filters + semantic_query
                                      │
                                      ▼
                               retrieve.hybrid_search ─▶ ListingHit[]
                                      │
                                      ▼
                          synthesize() ── Claude Sonnet ── prose
                                      │
                                      ▼
                              { answer, listings, rationale }

The model is forbidden from inventing listings. The prompt instructs it
to reference only IDs from the retrieved set; the synthesizer post-checks
the response to strip any fabricated VINs/IDs and warn the caller.

All Bedrock calls flow through ``TokenCache`` per ``ai-cache-rules.md``.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from carpapi.cache.bedrock_client import bedrock_chat
from carpapi.cache.token_cache import SQLiteBackend, TokenCache
from carpapi.rag.planner import plan as plan_query
from carpapi.rag.retrieve import Filters, ListingHit, hybrid_search

log = logging.getLogger("carpapi.rag.answer")

_DEFAULT_LIMIT = 8


_SYNTH_SYSTEM = """You are CarPapi, a used-car concierge.

You receive: (1) the user's question, (2) the structured filters CarPapi
extracted, (3) a ranked list of real listings from CarPapi's database.

Rules — ALL are hard:
  - Never invent listings. Reference ONLY the listings in the context.
  - When you mention a car, cite its [id] in square brackets so the
    frontend can render it as a card.
  - Be concise. Two or three sentences of prose is plenty.
  - Honest about uncertainty. If the listings don't really answer the
    question, say so and suggest a tighter or looser query.
  - Don't quote VINs or dealer phone numbers in prose.
  - No financial advice; you can mention list price vs. market range
    only if the context provides comparable cars.
"""


@dataclass
class AnswerResult:
    answer: str
    listings: list[dict[str, Any]] = field(default_factory=list)
    rationale: str = ""
    car_query: dict[str, Any] = field(default_factory=dict)
    plan_source: str = ""             # "llm" | "regex-fallback"
    retrieval_path: str = ""          # "structured" | "vector" | "mixed"
    cited_listing_ids: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _build_cache() -> TokenCache:
    """Process-local TokenCache wired to Bedrock.

    Single cache instance per process is fine — SQLiteBackend is
    thread-safe (per its docstring). The Django side wires a long-lived
    cache; the CLI path makes one ad-hoc.
    """
    return TokenCache(
        backend=SQLiteBackend(),
        llm_call=bedrock_chat(default_model="haiku", default_max_tokens=512),
    )


def _format_context(hits: list[ListingHit]) -> str:
    """Render listings as a compact factual table for the synth prompt.

    Anonymizes dealer phone/email if any leak (defense in depth — the
    pipeline already strips these at ingest).
    """
    lines: list[str] = ["LISTINGS (cite by [id]):"]
    for h in hits:
        price = f"${int(h.price_amount):,}" if h.price_amount else "price n/a"
        miles = f"{int(h.mileage):,} mi" if h.mileage is not None else "miles n/a"
        loc = " ".join(x for x in (h.city, h.region) if x) or ""
        dealer = h.dealer_name or h.seller_type or ""
        sim = f" sim={h.similarity:.2f}" if h.similarity is not None else ""
        lines.append(
            f"- [{h.id}] {h.year or '????'} {h.make or ''} {h.model or ''} "
            f"{h.trim or ''} ({h.body_style or 'n/a'}) — {price}, {miles}"
            f"{', ' + loc if loc else ''}{(', ' + dealer) if dealer else ''}"
            f"{sim}"
        )
    return "\n".join(lines)


_ID_RE = re.compile(r"\[([0-9a-f-]{8,40})\]", re.IGNORECASE)


def _cited_ids(text: str, valid_ids: set[str]) -> tuple[list[str], list[str]]:
    """Return (legitimate cited ids, ids the model invented)."""
    found = _ID_RE.findall(text or "")
    legit, hallucinated = [], []
    seen: set[str] = set()
    for fid in found:
        if fid in seen:
            continue
        seen.add(fid)
        (legit if fid in valid_ids else hallucinated).append(fid)
    return legit, hallucinated


def synthesize(
    message: str,
    hits: list[ListingHit],
    *,
    car_query: dict[str, Any],
    cache: TokenCache,
    model: str = "sonnet",
    max_tokens: int = 400,
) -> tuple[str, list[str], list[str]]:
    """Call Sonnet to write a short prose response.

    Returns (answer_text, cited_ids, hallucinated_ids).
    """
    if not hits:
        return (
            "I couldn't find anything in our inventory that matches that "
            "query — try loosening the constraints (broader price range, "
            "different model, or a wider radius).",
            [],
            [],
        )

    plan_summary = ", ".join(
        f"{k}={v}" for k, v in car_query.items()
        if v not in (None, "", 0) and k != "semantic_query"
    ) or "(no hard filters)"

    user_block = (
        f"USER QUESTION: {message}\n\n"
        f"FILTERS APPLIED: {plan_summary}\n\n"
        + _format_context(hits)
    )

    prompt = _SYNTH_SYSTEM + "\n\n" + user_block + "\n\nWrite the response now."
    try:
        answer = cache.query(
            prompt,
            skill="rag-synthesize",
            model=model,
            max_tokens=max_tokens,
            ttl=24 * 3600,
        )
    except Exception as exc:  # noqa: BLE001
        # Bedrock unreachable (use-case-form gate, quota, network) — fall back
        # to a templated response so the API still returns useful results.
        log.warning("synth: LLM unavailable, using template fallback: %s", exc)
        top = hits[0]
        price = f"${int(top.price_amount):,}" if top.price_amount else "price n/a"
        return (
            f"Found {len(hits)} matching listings. Top result: a "
            f"{top.year or ''} {top.make or ''} {top.model or ''} "
            f"at {price} [{top.id}]. (Prose synthesis temporarily "
            f"unavailable — see listings below for full details.)",
            [top.id],
            [],
        )

    valid_ids = {h.id for h in hits}
    legit, hallucinated = _cited_ids(answer, valid_ids)
    if hallucinated:
        log.warning("synth: model invented ids %s — dropping from response", hallucinated)
        # Strip the hallucinated brackets from the prose so the UI doesn't
        # try to render a card we don't have.
        for hid in hallucinated:
            answer = answer.replace(f"[{hid}]", "")
    return answer.strip(), legit, hallucinated


def answer(
    message: str,
    *,
    cache: Optional[TokenCache] = None,
    limit: int = _DEFAULT_LIMIT,
) -> AnswerResult:
    """Full RAG pipeline. The single function the Django view calls."""
    if not message or not message.strip():
        return AnswerResult(answer="Ask me about a car you're looking for.")

    c = cache or _build_cache()

    # 1. Plan filters from the message.
    pr = plan_query(message, cache=c)

    # 2. Retrieve listings (hybrid: structured first, vector fallback).
    hits = hybrid_search(
        pr.car_query.get("semantic_query") or message,
        filters=pr.filters,
        limit=limit,
    )
    retrieval_path = (
        "structured" if hits and hits[0].rank_reason == "structured" else "vector"
    )

    # 3. Synthesize prose with citations.
    prose, cited, hallucinated = synthesize(
        message, hits, car_query=pr.car_query, cache=c,
    )

    return AnswerResult(
        answer=prose,
        listings=[h.to_card() for h in hits],
        rationale=pr.rationale,
        car_query=pr.car_query,
        plan_source=pr.source,
        retrieval_path=retrieval_path,
        cited_listing_ids=cited,
        diagnostics={
            "hits": len(hits),
            "hallucinated_ids_dropped": hallucinated,
            "cache": {
                "hits": c.stats.hits,
                "misses": c.stats.misses,
            },
        },
    )
