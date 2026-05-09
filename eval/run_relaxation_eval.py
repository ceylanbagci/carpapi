from __future__ import annotations

"""Smoke-test the zero-result relaxation logic.

Tests pure relax_query() — no DB, no API. Verifies one filter relaxes per
call, in the documented priority order: radius_miles → price_max →
mileage_max → year_min.

Run from repo root:
    python eval/run_relaxation_eval.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from carapi_api.orchestrator import relax_query  # noqa: E402


CASES = [
    # (label, input, expected_changes_in_relaxed, expected_explanation_substr)
    (
        "doubles small radius",
        {"radius_miles": 25, "price_max": 25000},
        {"radius_miles": 50.0},
        "25 mi to 50 mi",
    ),
    (
        "caps radius at 200",
        {"radius_miles": 150, "price_max": 25000},
        {"radius_miles": 200.0},
        "to 200 mi",
    ),
    (
        "drops radius once at cap",
        {"radius_miles": 200, "zip_code": "07470"},
        {"radius_miles": None, "zip_code": None},
        "removed location",
    ),
    (
        "raises price by ~10%",
        {"price_max": 25000},
        {"price_max": 27500.0},
        "from $25,000 to $27,500",
    ),
    (
        "raises mileage by ~20%",
        {"mileage_max": 50000},
        {"mileage_max": 60000.0},
        "from 50,000 to 60,000 mi",
    ),
    (
        "decrements year_min",
        {"year_min": 2018},
        {"year_min": 2017},
        "earlier model year (2017)",
    ),
    (
        "no-op when nothing relaxable",
        {"make": "Toyota", "body_style": "SUV"},
        None,
        None,
    ),
]


def main() -> int:
    failures: list[str] = []
    for label, q, expected_changes, expected_substr in CASES:
        result = relax_query(q)
        if expected_changes is None:
            if result is not None:
                failures.append(f"{label}: expected None, got {result}")
            continue
        if result is None:
            failures.append(f"{label}: expected relaxation, got None")
            continue
        relaxed, explanation = result
        for k, v in expected_changes.items():
            if relaxed.get(k) != v:
                failures.append(
                    f"{label}: field {k!r} expected {v!r}, got {relaxed.get(k)!r}"
                )
        if expected_substr and expected_substr not in explanation:
            failures.append(
                f"{label}: explanation missing {expected_substr!r}; got: {explanation!r}"
            )

    passed = len(CASES) - len(failures)
    print(f"\nrelaxation eval: {passed}/{len(CASES)} passed")
    if failures:
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
