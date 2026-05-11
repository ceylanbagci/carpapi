"""Profile the smart-routing RAG pipeline.

Runs a fixed set of queries that exercise each routing branch:
  - skip path  : "Toyota Camry under $25k"  (make+model+price → concrete)
  - haiku path : "SUV around 50k miles"     (filters present, no Sonnet cues)
  - sonnet path: "Which SUV is most reliable under $30k?"  (reliable cue)
  - vector path: "fun weekend car"          (no filters → vector)

For each query we measure:
  - plan+embed time   (parallelized)
  - retrieval time
  - synthesis time    (or 0 if skipped)
  - total wall-clock

Run twice per query: first call hits Bedrock, second call should be
cache-warm. We print both so we can see the real-world cache benefit.

Usage:
    python -m tools.profile_rag_latency
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

# Allow importing carpapi.* without installing.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("CARPAPI_DB_HOST", "localhost")
os.environ.setdefault("CARPAPI_DB_PORT", "5433")
os.environ.setdefault("CARPAPI_DB_NAME", "carpapi")
os.environ.setdefault("CARPAPI_DB_USER", "carpapi")
os.environ.setdefault("CARPAPI_DB_PASSWORD", "carpapi")

from carpapi.cache.bedrock_client import bedrock_chat  # noqa: E402
from carpapi.cache.token_cache import SQLiteBackend, TokenCache  # noqa: E402
from carpapi.rag.answer import answer  # noqa: E402

QUERIES = [
    ("skip-expected", "Toyota Camry under $25k"),
    ("haiku-expected", "SUV around 50k miles"),
    ("sonnet-expected", "Which SUV is most reliable under $30k?"),
    ("vector-expected", "fun weekend car"),
]


def main() -> int:
    cache = TokenCache(
        backend=SQLiteBackend("./data/profile_cache.sqlite"),
        llm_call=bedrock_chat(default_model="haiku", default_max_tokens=512),
    )

    rows: list[dict[str, Any]] = []
    for label, q in QUERIES:
        for run_idx in (1, 2):
            t0 = time.perf_counter()
            res = answer(q, cache=cache, limit=8)
            dt = time.perf_counter() - t0
            rows.append({
                "label": label,
                "run": run_idx,
                "query": q,
                "total_s": round(dt, 3),
                "synth_model": res.diagnostics.get("synth_model"),
                "retrieval_path": res.retrieval_path,
                "hits": res.diagnostics.get("hits"),
                "cache_hits": res.diagnostics.get("cache", {}).get("hits"),
                "cache_misses": res.diagnostics.get("cache", {}).get("misses"),
                "answer_head": (res.answer or "")[:80].replace("\n", " "),
            })

    # Print a compact table.
    print(f"\n{'label':<18}{'run':<5}{'total_s':<10}{'synth':<10}{'path':<12}"
          f"{'hits':<6}{'cache(h/m)':<14}query")
    print("-" * 120)
    for r in rows:
        print(
            f"{r['label']:<18}{r['run']:<5}{r['total_s']:<10}"
            f"{str(r['synth_model']):<10}{r['retrieval_path']:<12}"
            f"{str(r['hits']):<6}"
            f"{str(r['cache_hits']) + '/' + str(r['cache_misses']):<14}"
            f"{r['query']}"
        )
    print("-" * 120)

    medians = {}
    for label, _ in QUERIES:
        cold = [r["total_s"] for r in rows if r["label"] == label and r["run"] == 1]
        warm = [r["total_s"] for r in rows if r["label"] == label and r["run"] == 2]
        medians[label] = (cold[0] if cold else None, warm[0] if warm else None)

    print("\nLatency summary (cold / warm seconds):")
    for label, (cold, warm) in medians.items():
        verdict = ""
        if cold is not None and warm is not None:
            verdict = "✓" if warm <= 2.0 else "✗ over 2s warm"
        print(f"  {label:<20} cold={cold}  warm={warm}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
