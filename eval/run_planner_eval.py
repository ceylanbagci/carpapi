from __future__ import annotations

"""Evaluate the query planner against eval/fixtures/queries.jsonl.

Each line has {"message", "expected"}. The runner calls plan_car_query() and
asserts that every key in `expected` is present in the planner output with the
same value. The planner may return additional fields — those are not checked.

Run from repo root:
    python eval/run_planner_eval.py

Returns exit code 0 if all cases pass, 1 otherwise. Prints a per-case diff for
failures.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
sys.path.insert(0, str(REPO_ROOT / "pipeline"))

from carapi_api.orchestrator import plan_car_query  # noqa: E402

FIXTURES = REPO_ROOT / "eval" / "fixtures" / "queries.jsonl"


def main() -> int:
    if not FIXTURES.exists():
        print(f"missing fixtures: {FIXTURES}", file=sys.stderr)
        return 2

    failures: list[tuple[str, dict, dict]] = []
    total = 0

    for line in FIXTURES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        total += 1
        case = json.loads(line)
        message = case["message"]
        expected = case.get("expected", {})

        actual, _rationale = plan_car_query(message)
        diff = {
            k: (expected[k], actual.get(k))
            for k in expected
            if actual.get(k) != expected[k]
        }
        if diff:
            failures.append((message, expected, diff))

    passed = total - len(failures)
    print(f"\nplanner eval: {passed}/{total} passed")

    if failures:
        print("\nfailures:")
        for message, expected, diff in failures:
            print(f"  - {message!r}")
            print(f"      expected: {expected}")
            print(f"      mismatched fields (expected, actual): {diff}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
