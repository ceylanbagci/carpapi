from __future__ import annotations

"""Integration eval for carpapi.db repositories.

Exercises every repo against the live Postgres pointed at by DATABASE_URL.
Skips cleanly (exit 0) when DATABASE_URL is unset — so the suite can run
in CI without a DB without breaking.

Each case writes to a unique source_id ('eval-smoke') so re-runs don't
collide with real data. Cleanup happens at the end via a wrapping
transaction that rolls back.

Run from repo root:
    set -a; source .env; set +a
    PYTHONPATH=. pipeline/.venv/bin/python eval/run_db_repos_eval.py
"""

import datetime as dt
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _skip_if_no_db() -> bool:
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL not set; skipping live-DB eval (exit 0)")
        return True
    return False


SOURCE_ID = f"eval-smoke-{uuid.uuid4().hex[:8]}"


def case_dealer_repo(session, fails: list[str]) -> None:
    from carpapi.db import DealerRepo

    slug = f"eval_dealer_{uuid.uuid4().hex[:8]}"
    DealerRepo.upsert(
        session,
        {
            "slug": slug,
            "name": "Eval Test Dealer",
            "homepage_url": "https://example.com",
            "cms": "dealer.com",
            "region": "NJ",
            "makes_carried": ["Toyota", "Honda"],
            "status": "active",
        },
    )
    found = DealerRepo.get_by_slug(session, slug)
    if found is None:
        fails.append("DealerRepo.get_by_slug returned None after upsert")
        return
    if found.makes_carried != ["Toyota", "Honda"]:
        fails.append(f"DealerRepo: makes_carried mismatch: {found.makes_carried!r}")
    DealerRepo.upsert(session, {"slug": slug, "name": "Eval Test Dealer", "cms": "dealeron"})
    found2 = DealerRepo.get_by_slug(session, slug)
    if found2.cms != "dealeron":
        fails.append(f"DealerRepo: upsert didn't update cms: {found2.cms!r}")


def case_source_repo(session, fails: list[str]) -> None:
    from carpapi.db import SourceRepo

    SourceRepo.upsert(
        session,
        {"id": SOURCE_ID, "name": "Eval source", "type": "fixture", "priority": 7},
    )
    found = SourceRepo.get(session, SOURCE_ID)
    if found is None or found.priority != 7:
        fails.append(f"SourceRepo upsert/get failed: {found!r}")


def case_listing_group_repo(session, fails: list[str]) -> None:
    from carpapi.db import ListingGroupRepo

    vin = "1FEVALG" + uuid.uuid4().hex[:10].upper()
    g1 = ListingGroupRepo.get_or_create_by_vin(session, vin, make="Toyota", model="Camry", year=2022)
    g2 = ListingGroupRepo.get_or_create_by_vin(session, vin)
    if g1.id != g2.id:
        fails.append(
            f"ListingGroupRepo.get_or_create_by_vin not idempotent: {g1.id} vs {g2.id}"
        )


def case_ingest_repo_full_run(session, fails: list[str]) -> None:
    from carpapi.db import IngestRepo

    run = IngestRepo.start_run(session, source_id=SOURCE_ID, run_kind="manual")
    if run.status != "running":
        fails.append(f"IngestRepo.start_run: status={run.status!r}")
    rp = IngestRepo.store_raw_pointer(
        session,
        source_id=SOURCE_ID,
        ingest_run_id=run.id,
        external_id="ext-1",
        s3_uri=f"s3://bucket/{run.id}/ext-1.json",
        raw_checksum="cks-1",
    )
    IngestRepo.log_rejection(
        session,
        ingest_run_id=run.id,
        source_id=SOURCE_ID,
        reason="schema validation failed",
        error_class="ValidationError",
        snippet="<<truncated>>",
    )
    IngestRepo.finish_run(
        session,
        run.id,
        counts={"RecordsFetched": 5, "RecordsRejected": 1},
        duration_seconds=1.234,
        status="partial",
        error_summary={"top_error": "ValidationError"},
    )

    # Re-fetch the run to confirm the update landed.
    from carpapi.db.models import IngestRun
    refreshed = session.get(IngestRun, run.id)
    if refreshed.status != "partial":
        fails.append(f"IngestRepo.finish_run: status={refreshed.status!r}")
    if refreshed.counts.get("RecordsFetched") != 5:
        fails.append(f"IngestRepo.finish_run: counts not persisted: {refreshed.counts!r}")


def case_monitor_repo(session, fails: list[str]) -> None:
    from carpapi.db import MonitorRepo

    today = dt.date.today()
    rep = MonitorRepo.insert_scrape_report(
        session,
        ingest_run_id=None,
        source_id=SOURCE_ID,
        record_count=42,
        null_rates={"price_amount": 0.05},
        duplicate_rate=0.02,
        http_error_rate=0.0,
        flags=[],
        healthy=True,
    )
    if not rep.healthy or rep.record_count != 42:
        fails.append(f"MonitorRepo: insert_scrape_report mismatch: {rep!r}")

    daily = MonitorRepo.upsert_daily_report(
        session,
        report_date=today,
        summary={"sources_run": 1},
        per_source={SOURCE_ID: {"fetched": 5}},
        markdown="# eval test",
    )
    if daily.report_date != today:
        fails.append(f"MonitorRepo.upsert_daily_report: date mismatch")
    daily2 = MonitorRepo.upsert_daily_report(
        session,
        report_date=today,
        summary={"sources_run": 2},
        per_source={SOURCE_ID: {"fetched": 10}},
        markdown="# eval test v2",
    )
    if daily.id != daily2.id:
        fails.append(f"MonitorRepo: daily-report upsert created new row instead of updating")
    if daily2.summary.get("sources_run") != 2:
        fails.append(f"MonitorRepo: daily-report update didn't apply")


def case_ai_cache_repo(session, fails: list[str]) -> None:
    from carpapi.db import AICacheRepo

    key = f"eval-key-{uuid.uuid4().hex[:8]}"
    AICacheRepo.set(
        session, key=key, value="response-v1", ttl_seconds=3600,
        skill="classify", model="haiku", max_tokens=256,
    )
    v1 = AICacheRepo.get(session, key)
    if v1 != "response-v1":
        fails.append(f"AICacheRepo.set/get round-trip failed: {v1!r}")

    AICacheRepo.set(session, key=key, value="response-v2", ttl_seconds=3600)
    v2 = AICacheRepo.get(session, key)
    if v2 != "response-v2":
        fails.append(f"AICacheRepo upsert didn't replace value: {v2!r}")

    miss = AICacheRepo.get(session, "definitely-not-there")
    if miss is not None:
        fails.append(f"AICacheRepo.get on missing key returned non-None: {miss!r}")

    call = AICacheRepo.log_call(
        session,
        skill="classify",
        model="haiku",
        max_tokens=256,
        input_tokens=120,
        output_tokens=45,
        cost_usd=0.000123,
        latency_ms=850,
    )
    if call.input_tokens != 120 or call.cost_usd is None:
        fails.append(f"AICacheRepo.log_call: bad row: {call.__dict__!r}")


def main() -> int:
    if _skip_if_no_db():
        return 0

    from carpapi.db import session_scope

    cases = [
        ("DealerRepo upsert/get_by_slug", case_dealer_repo),
        ("SourceRepo upsert/get", case_source_repo),
        ("ListingGroupRepo.get_or_create_by_vin idempotent", case_listing_group_repo),
        ("IngestRepo full run lifecycle", case_ingest_repo_full_run),
        ("MonitorRepo scrape + daily upsert", case_monitor_repo),
        ("AICacheRepo set/get/log_call", case_ai_cache_repo),
    ]

    total = 0
    failed_cases = 0
    for label, runner in cases:
        total += 1
        fails: list[str] = []
        # Each case in its own transaction; rollback at end so eval is clean.
        try:
            with session_scope(autocommit=False) as session:
                runner(session, fails)
                # Always rollback so eval doesn't pollute the DB.
                session.rollback()
        except Exception as exc:  # noqa: BLE001
            fails.append(f"raised {type(exc).__name__}: {exc}")

        if fails:
            failed_cases += 1
            print(f"  FAIL  {label}")
            for f in fails:
                print(f"    - {f}")
        else:
            print(f"  ok    {label}")

    print(f"\nDB repos eval: {total - failed_cases}/{total} passed")
    return 0 if failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
