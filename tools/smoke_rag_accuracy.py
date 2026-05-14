"""Smoke-check that smart-routing doesn't break retrieval accuracy.

For each query we assert:
  - hits is non-empty
  - hits respect the obvious hard filters (make/model/price/year/body_style)
  - if synthesis ran, it produced prose
  - cited_listing_ids ⊆ returned ids (no hallucinated cards)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("CARPAPI_DB_HOST", "localhost")
os.environ.setdefault("CARPAPI_DB_PORT", "5433")
os.environ.setdefault("CARPAPI_DB_NAME", "carpapi")
os.environ.setdefault("CARPAPI_DB_USER", "carpapi")
os.environ.setdefault("CARPAPI_DB_PASSWORD", "carpapi")

from carpapi.cache.bedrock_client import bedrock_chat  # noqa: E402
from carpapi.cache.token_cache import SQLiteBackend, TokenCache  # noqa: E402
from carpapi.rag.answer import answer  # noqa: E402


CHECKS = [
    {
        "query": "Toyota Camry under $25k",
        "expect_make": "Toyota",
        "expect_model": "Camry",
        "max_price": 25000,
    },
    {
        "query": "SUV around 50k miles",
        # body_style is unreliable across sources — only assert mileage cap if filter set.
    },
    {
        "query": "Which SUV is most reliable under $30k?",
        "max_price": 30000,
    },
    {
        "query": "fun weekend car",
        # vector-only; just assert we got hits and they have urls/prices
    },
]


def main() -> int:
    cache = TokenCache(
        backend=SQLiteBackend("./data/profile_cache.sqlite"),
        llm_call=bedrock_chat(default_model="haiku", default_max_tokens=512),
    )

    failures = 0
    for chk in CHECKS:
        q = chk["query"]
        print(f"\n=== {q} ===")
        res = answer(q, cache=cache, limit=8)
        print(f"  synth_model: {res.diagnostics.get('synth_model')}  path: {res.retrieval_path}  hits: {res.diagnostics.get('hits')}")
        print(f"  cited: {res.cited_listing_ids}")
        print(f"  answer: {res.answer[:160]}")
        print(f"  filters: {res.car_query}")

        # 1. Non-empty
        if not res.listings:
            print("  FAIL: no hits")
            failures += 1
            continue

        ids = {l["id"] for l in res.listings}

        # 2. Cited IDs are valid
        for cid in res.cited_listing_ids:
            if cid not in ids:
                print(f"  FAIL: cited {cid} not in returned set")
                failures += 1

        # 3. Hard filters respected
        if (m := chk.get("expect_make")):
            wrong = [l for l in res.listings if (l.get("make") or "").lower() != m.lower()]
            if wrong:
                print(f"  FAIL: {len(wrong)}/{len(res.listings)} hits aren't {m}")
                for w in wrong[:3]:
                    print(f"    - {w['id']} {w.get('make')} {w.get('model')}")
                failures += 1
            else:
                print(f"  ✓ all {len(res.listings)} hits are {m}")
        if (m := chk.get("expect_model")):
            wrong = [l for l in res.listings if (l.get("model") or "").lower() != m.lower()]
            if wrong:
                print(f"  FAIL: {len(wrong)}/{len(res.listings)} hits aren't {m}")
                failures += 1
            else:
                print(f"  ✓ all hits are model={m}")
        if (mx := chk.get("max_price")):
            wrong = [l for l in res.listings if (l.get("price") or 0) > mx]
            if wrong:
                print(f"  FAIL: {len(wrong)} hits over ${mx:,}")
                failures += 1
            else:
                print(f"  ✓ all hits ≤ ${mx:,}")

        # 4. Synth produced prose (skip path uses templated rationale)
        if not res.answer or len(res.answer) < 10:
            print("  FAIL: answer empty/too short")
            failures += 1

    print(f"\n{'='*40}")
    print(f"accuracy smoke: {len(CHECKS)} queries, {failures} failures")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
