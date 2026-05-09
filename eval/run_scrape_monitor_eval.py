from __future__ import annotations

"""Smoke test for carpapi.monitor.scrape_monitor.

Pure stdlib. No I/O, no AI. Verifies the threshold logic flags the right
cases and stays quiet on healthy ones.

Run from repo root:
    python eval/run_scrape_monitor_eval.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from carpapi.monitor.scrape_monitor import (  # noqa: E402
    ScrapeMonitorThresholds,
    analyze,
)


def _record(**fields: object) -> dict:
    base = {
        "external_id": "id-1",
        "make": "Toyota",
        "model": "Camry",
        "year": 2022,
        "price_amount": 24500,
        "mileage": 18000,
        "vin": "4T1C11AK5NU123456",
    }
    base.update(fields)
    return base


def case_healthy() -> list[str]:
    fails: list[str] = []
    records = [_record(external_id=f"id-{i}") for i in range(50)]
    r = analyze(records, source_id="demo", http_total=50, http_errors=1)
    if not r.healthy:
        fails.append(f"expected healthy, got flags: {r.flags}")
    if r.record_count != 50:
        fails.append(f"record_count: expected 50, got {r.record_count}")
    return fails


def case_zero_records() -> list[str]:
    fails: list[str] = []
    r = analyze([], source_id="silent", http_total=10, http_errors=0)
    if r.healthy:
        fails.append("expected flagged for zero records, got healthy")
    if not any("record count" in f for f in r.flags):
        fails.append(f"expected 'record count' flag, got {r.flags}")
    return fails


def case_high_null_rate_blocked() -> list[str]:
    fails: list[str] = []
    # 100 records, 50 missing price_amount → 50% null > 10% threshold
    records = (
        [_record(external_id=f"id-{i}", price_amount=None) for i in range(50)]
        + [_record(external_id=f"id-{i}") for i in range(50, 100)]
    )
    r = analyze(records, source_id="bad-prices")
    if r.healthy:
        fails.append("expected flagged, got healthy")
    if not any("price_amount" in f for f in r.flags):
        fails.append(f"expected price_amount flag, got {r.flags}")
    return fails


def case_within_batch_duplicates() -> list[str]:
    fails: list[str] = []
    # 20 records with only 5 unique external_ids → 75% duplicate
    records = [_record(external_id=f"id-{i % 5}") for i in range(20)]
    r = analyze(records, source_id="paginator-bug")
    if r.healthy:
        fails.append("expected flagged, got healthy")
    if not any("duplicate" in f for f in r.flags):
        fails.append(f"expected duplicate flag, got {r.flags}")
    return fails


def case_http_error_rate_flagged() -> list[str]:
    fails: list[str] = []
    records = [_record(external_id=f"id-{i}") for i in range(20)]
    # 10% http error rate, threshold is 5% → flag.
    r = analyze(records, source_id="flaky", http_total=20, http_errors=2)
    if r.healthy:
        fails.append("expected flagged, got healthy")
    if not any("HTTP error rate" in f for f in r.flags):
        fails.append(f"expected HTTP error rate flag, got {r.flags}")
    return fails


def case_threshold_override() -> list[str]:
    fails: list[str] = []
    records = [_record(external_id=f"id-{i}", vin=None) for i in range(20)]
    # Default threshold for vin null rate is 30%; here it's 100%, so flagged.
    default = analyze(records, source_id="no-vin")
    if default.healthy:
        fails.append("default thresholds: expected flagged on 100% null vin")
    # Loosen to 100% null rate; should pass.
    loose = ScrapeMonitorThresholds(
        max_null_rate_per_field={"vin": 1.0, "price_amount": 1.0, "make": 1.0,
                                 "model": 1.0, "mileage": 1.0, "year": 1.0}
    )
    relaxed = analyze(records, source_id="no-vin", thresholds=loose)
    if not relaxed.healthy:
        fails.append(f"loose thresholds: expected healthy, got {relaxed.flags}")
    return fails


def main() -> int:
    cases = [
        ("healthy batch", case_healthy),
        ("zero records flagged", case_zero_records),
        ("high price null rate flagged", case_high_null_rate_blocked),
        ("within-batch duplicates flagged", case_within_batch_duplicates),
        ("HTTP error rate flagged", case_http_error_rate_flagged),
        ("threshold override respected", case_threshold_override),
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
    print(f"\nscrape monitor eval: {total - failed}/{total} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
