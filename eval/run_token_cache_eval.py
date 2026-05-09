from __future__ import annotations

"""Smoke test for the TokenCache layer.

Covers:
  - cache miss → llm_call invoked → result stored
  - cache hit → llm_call NOT invoked → cached result returned
  - PII guard rejects VINs, phones, emails, addresses BEFORE any LLM call
  - missing llm_call on a miss raises (no silent bypass)
  - model + max_tokens are part of the cache key (different params = different keys)

Pure stdlib + the carpapi package — no Claude/Bedrock auth needed.

Run from repo root:
    python eval/run_token_cache_eval.py
"""

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from carpapi.cache.pii_guard import PIIInPromptError  # noqa: E402
from carpapi.cache.token_cache import SQLiteBackend, TokenCache  # noqa: E402


class _CallCounter:
    """Stand-in for the real LLM client. Records calls, returns canned response."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int | None, str | None]] = []

    def __call__(self, prompt: str, max_tokens: int | None, model: str | None) -> str:
        self.calls.append((prompt, max_tokens, model))
        return f"resp({len(self.calls)})"


def _fresh_cache() -> tuple[TokenCache, _CallCounter, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    counter = _CallCounter()
    cache = TokenCache(backend=SQLiteBackend(tmp.name), llm_call=counter)
    return cache, counter, tmp.name


def case_miss_then_hit() -> list[str]:
    failures: list[str] = []
    cache, counter, _ = _fresh_cache()

    r1 = cache.query("Classify body style: SUV", skill="classify", max_tokens=256)
    if r1 != "resp(1)":
        failures.append(f"miss: expected 'resp(1)', got {r1!r}")
    if len(counter.calls) != 1:
        failures.append(f"miss: expected 1 LLM call, got {len(counter.calls)}")

    r2 = cache.query("Classify body style: SUV", skill="classify", max_tokens=256)
    if r2 != "resp(1)":
        failures.append(f"hit: expected 'resp(1)' (cached), got {r2!r}")
    if len(counter.calls) != 1:
        failures.append(
            f"hit: expected still 1 LLM call (cached), got {len(counter.calls)}"
        )
    if cache.stats.hits != 1 or cache.stats.misses != 1:
        failures.append(
            f"stats: expected hits=1 misses=1, got hits={cache.stats.hits} "
            f"misses={cache.stats.misses}"
        )
    return failures


def case_pii_rejected() -> list[str]:
    failures: list[str] = []
    cache, counter, _ = _fresh_cache()

    pii_inputs = [
        ("VIN", "Decode VIN 4T1C11AK5NU123456 for me"),
        ("phone", "Call seller at 555-867-5309"),
        ("email", "Reach out to seller@example.com"),
        ("address", "Visit 123 Main Street for inspection"),
    ]
    for kind, prompt in pii_inputs:
        try:
            cache.query(prompt, skill="extract")
        except PIIInPromptError:
            continue
        failures.append(f"PII guard failed to block {kind}: {prompt!r}")

    if counter.calls:
        failures.append(
            f"PII guard let prompts through: {len(counter.calls)} LLM calls"
        )
    if cache.stats.pii_rejected != len(pii_inputs):
        failures.append(
            f"stats.pii_rejected expected {len(pii_inputs)}, "
            f"got {cache.stats.pii_rejected}"
        )
    return failures


def case_no_llm_call_configured() -> list[str]:
    failures: list[str] = []
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.close()
    cache = TokenCache(backend=SQLiteBackend(tmp.name), llm_call=None)
    try:
        cache.query("anything", skill="classify")
    except RuntimeError as exc:
        if "no llm_call configured" not in str(exc).lower():
            failures.append(f"unexpected RuntimeError text: {exc!r}")
    else:
        failures.append("expected RuntimeError for missing llm_call, got nothing")
    return failures


def case_key_includes_model_and_max_tokens() -> list[str]:
    failures: list[str] = []
    cache, counter, _ = _fresh_cache()

    cache.query("same prompt", skill="classify", model="haiku", max_tokens=256)
    cache.query("same prompt", skill="classify", model="sonnet", max_tokens=256)
    cache.query("same prompt", skill="classify", model="haiku", max_tokens=512)
    cache.query("same prompt", skill="classify", model="haiku", max_tokens=256)

    if len(counter.calls) != 3:
        failures.append(
            f"expected 3 distinct LLM calls (model/max_tokens vary, last is "
            f"a hit), got {len(counter.calls)}"
        )
    return failures


def main() -> int:
    cases = [
        ("miss then hit", case_miss_then_hit),
        ("PII rejected", case_pii_rejected),
        ("missing llm_call raises", case_no_llm_call_configured),
        ("key varies by model/max_tokens", case_key_includes_model_and_max_tokens),
    ]
    total = 0
    failed = 0
    for label, runner in cases:
        total += 1
        fails = runner()
        if fails:
            failed += 1
            print(f"  FAIL  {label}")
            for f in fails:
                print(f"    - {f}")
        else:
            print(f"  ok    {label}")

    print(f"\ntoken cache eval: {total - failed}/{total} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
