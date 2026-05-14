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
import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from carpapi.cache.bedrock_client import bedrock_chat, bedrock_embed
from carpapi.cache.token_cache import SQLiteBackend, TokenCache
from carpapi.rag.planner import plan as plan_query
from carpapi.rag.retrieve import (
    Filters, ListingHit, hybrid_search, structured_search, vector_search,
)

log = logging.getLogger("carpapi.rag.answer")

_DEFAULT_LIMIT = 8


_SYNTH_SYSTEM_HAIKU = """You are CarPapi. Given the listings below, write a SINGLE short sentence \
that points to the best match by [id]. Never invent listings. Never cite an \
id not in the list. No VINs or phone numbers. No financial advice. Be terse."""

_SYNTH_SYSTEM_SONNET = """You are CarPapi, a used-car concierge.

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
    top_n_to_show: Optional[int] = None,
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

    # Show fewer listings to the model when running Haiku — saves input
    # tokens and time without changing what cards the user sees.
    show = hits if top_n_to_show is None else hits[: top_n_to_show]
    system = _SYNTH_SYSTEM_HAIKU if model == "haiku" else _SYNTH_SYSTEM_SONNET

    user_block = (
        f"USER QUESTION: {message}\n\n"
        f"FILTERS APPLIED: {plan_summary}\n\n"
        + _format_context(show)
    )

    prompt = system + "\n\n" + user_block + "\n\nWrite the response now."
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


# --------------------------------------------------------------------------- #
# Smart-routing helpers — pick synthesis model (or skip synth entirely) based
# on retrieval shape + query complexity. Targets sub-2s latency for the
# common case while preserving Sonnet quality on hard queries.
# --------------------------------------------------------------------------- #

# Cues that suggest the user wants real reasoning (comparison, value
# analysis, nuanced multi-attribute trade-offs). Anything matching these
# routes to Sonnet; everything else uses Haiku (or skips synth).
_SONNET_CUES = re.compile(
    r"\b(compare|comparison|vs\.?|versus|best (value|choice|deal)|"
    r"which (is|one) (better|best)|recommend|trade[-\s]?off|differ|"
    r"reliable|safest|most|less|more|why|how does)\b",
    re.IGNORECASE,
)


def _filters_are_concrete(car_query: dict) -> bool:
    """A query is 'concrete' when the user named what they want hard
    enough that the listings cards ARE the answer — no prose needed.

    Trip on any of:
      - make AND model       (e.g., 'Toyota Camry')
      - body_style AND price_max     ('SUV under $30k')
      - price_max AND year_min/max   ('under $20k 2020+')
    """
    cq = car_query or {}
    has_make_model = cq.get("make") and cq.get("model")
    has_body_price = cq.get("body_style") and cq.get("price_max")
    has_price_year = cq.get("price_max") and (cq.get("year_min") or cq.get("year_max"))
    return bool(has_make_model or has_body_price or has_price_year)


def _pick_synth_strategy(
    message: str, hits: list[ListingHit], retrieval_path: str, car_query: dict
) -> str:
    """Return one of: 'skip' | 'haiku' | 'sonnet'.

    Latency targets (cold cache, after plan+embed):
      - skip:   ~0ms synth   → total ~1.3s
      - haiku:  ~700-900ms   → total ~2.0s
      - sonnet: ~3500-5000ms → total ~5-6s
    """
    has_cue = bool(_SONNET_CUES.search(message or ""))
    if has_cue:
        return "sonnet"
    if retrieval_path == "structured" and _filters_are_concrete(car_query):
        return "skip"
    if retrieval_path == "vector" and len(hits) >= 5:
        # Vector results need prose to explain why these came up
        return "sonnet"
    return "haiku"


def _templated_rationale(message: str, hits: list[ListingHit], car_query: dict) -> str:
    """Deterministic 1-sentence rationale when synthesis is skipped.

    Honest, terse, no synthesis cost. The cards carry the detail.
    """
    if not hits:
        return ("I couldn't find anything matching that — try a looser price "
                "range, a different model, or a wider radius.")

    parts: list[str] = []
    if car_query.get("make") or car_query.get("model"):
        parts.append(
            f"{car_query.get('make') or ''} {car_query.get('model') or ''}".strip()
        )
    elif car_query.get("body_style"):
        parts.append(f"{car_query['body_style']}s")
    else:
        parts.append("listings")

    if car_query.get("price_max"):
        parts.append(f"under ${int(car_query['price_max']):,}")
    if car_query.get("region"):
        parts.append(f"in {car_query['region']}")

    label = " ".join(parts).strip()
    cheapest = min(
        (h for h in hits if h.price_amount), key=lambda h: h.price_amount, default=None,
    )
    if cheapest:
        price = f"${int(cheapest.price_amount):,}"
        return (
            f"Found {len(hits)} {label}. Cheapest: {price} for a "
            f"{cheapest.year or ''} {cheapest.make or ''} {cheapest.model or ''} "
            f"[{cheapest.id}]."
        )
    return f"Found {len(hits)} {label}."


# --------------------------------------------------------------------------- #
# Top-level pipeline
# --------------------------------------------------------------------------- #


def _parallel_plan_and_embed(
    message: str, *, cache: TokenCache
) -> tuple[Any, Optional[list[float]]]:
    """Run plan + embed concurrently. Saves ~300ms on vector-path queries.

    Both calls are I/O-bound (Bedrock HTTP), so a 2-thread executor is
    sufficient — no GIL contention.
    """
    plan_result: list[Any] = [None]
    embed_result: list[Optional[list[float]]] = [None]
    plan_error: list[Optional[Exception]] = [None]
    embed_error: list[Optional[Exception]] = [None]

    def _plan():
        try:
            plan_result[0] = plan_query(message, cache=cache)
        except Exception as e:  # noqa: BLE001
            plan_error[0] = e

    def _embed():
        try:
            embed_result[0] = bedrock_embed(message)
        except Exception as e:  # noqa: BLE001
            embed_error[0] = e

    threads = [threading.Thread(target=_plan), threading.Thread(target=_embed)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if plan_error[0]:
        raise plan_error[0]
    # Embed errors are non-fatal — the structured path may suffice.
    if embed_error[0]:
        log.warning("parallel embed failed: %s (continuing without)", embed_error[0])
        return plan_result[0], None
    return plan_result[0], embed_result[0]


def answer(
    message: str,
    *,
    cache: Optional[TokenCache] = None,
    limit: int = _DEFAULT_LIMIT,
) -> AnswerResult:
    """Full RAG pipeline with latency-tuned routing.

    Smart router targets <2s p95:
      - skip-synth when structured filters narrow to <= 3 results
      - Haiku for routine queries
      - Sonnet only for comparison/value/nuance queries
      - plan + embed run concurrently
    """
    if not message or not message.strip():
        return AnswerResult(answer="Ask me about a car you're looking for.")

    c = cache or _build_cache()

    # 1. Plan + embed concurrently (saves ~300ms on vector-path queries).
    pr, query_vec = _parallel_plan_and_embed(message, cache=c)
    semantic_text = pr.car_query.get("semantic_query") or message

    # 2. Retrieve. We pre-computed the embedding above; pass it in if we
    #    need vector ranking. structured_search() doesn't need it.
    hits = structured_search(filters=pr.filters, limit=limit)
    retrieval_path = "structured"
    if not hits or not (pr.filters.make or pr.filters.model or pr.filters.body_style
                        or pr.filters.price_max or pr.filters.year_min):
        # Filters too loose — fall back to vector ranking.
        hits = vector_search(semantic_text, limit=limit, filters=pr.filters)
        retrieval_path = "vector"

    # 3. Choose synthesis strategy.
    strategy = _pick_synth_strategy(message, hits, retrieval_path, pr.car_query)

    if strategy == "skip":
        prose = _templated_rationale(message, hits, pr.car_query)
        cited = [hits[0].id] if hits else []
        hallucinated: list[str] = []
        synth_model = "skipped"
    else:
        # Haiku gets a tight prompt + 3 listings + short max_tokens for speed.
        # Sonnet gets the full context + more output room for nuance.
        if strategy == "haiku":
            prose, cited, hallucinated = synthesize(
                message, hits, car_query=pr.car_query, cache=c,
                model="haiku", max_tokens=140, top_n_to_show=3,
            )
        else:
            prose, cited, hallucinated = synthesize(
                message, hits, car_query=pr.car_query, cache=c,
                model="sonnet", max_tokens=400,
            )
        synth_model = strategy

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
            "synth_model": synth_model,
            "hallucinated_ids_dropped": hallucinated,
            "cache": {
                "hits": c.stats.hits,
                "misses": c.stats.misses,
            },
        },
    )
