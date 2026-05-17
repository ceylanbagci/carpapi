"""aws-cost-sentinel — first deployed agent in the CarPapi fleet.

Runtime contract (per .claude/agents/aws-cost-sentinel.md):
  - Triggered daily at 09:00 UTC by an EventBridge schedule.
  - Reads Cost Explorer for yesterday, 7-day window, MTD.
  - Detects anomalies vs a $100/mo budget (override via env).
  - Writes its state to s3://<FLEET_BUCKET>/fleet/aws-cost-sentinel.json
    so the /agents dashboard can read it.

State-file shape (must match what
web/backend/api/views_agents.py::_status_from_state expects):
  { "ok": bool, "ts_ms": int, "elapsed_s": float,
    "event": "done"|"handler_raised", "err": str|null,
    "agent": "aws-cost-sentinel",
    "yesterday_usd": float, "mtd_usd": float, "budget_usd": float,
    "burndown_pct": int, "top_services": [...], "anomalies": [...],
    "digest": str }

Permissions needed on the execution role:
  - ce:GetCostAndUsage  (Cost Explorer; us-east-1 only)
  - s3:PutObject on   arn:aws:s3:::<FLEET_BUCKET>/fleet/aws-cost-sentinel.json
  - logs:CreateLogStream, logs:PutLogEvents (AWSLambdaBasicExecutionRole)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import statistics
import time
import traceback
from typing import Any

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)

# ── Config ──────────────────────────────────────────────────────────
FLEET_BUCKET = os.environ.get(
    "CARPAPI_FLEET_BUCKET", "carpapi-frontend-183617081338",
)
FLEET_PREFIX = os.environ.get("CARPAPI_FLEET_PREFIX", "fleet").strip("/")
SLUG = "aws-cost-sentinel"
MONTHLY_BUDGET_USD = float(os.environ.get("CARPAPI_MONTHLY_BUDGET_USD", "100"))

# Cost Explorer only exists in us-east-1 regardless of where the
# Lambda runs.
CE_REGION = "us-east-1"

# ── AWS clients (lazy — Lambda reuses warm container; init once) ────
_ce = boto3.client("ce", region_name=CE_REGION)
_s3 = boto3.client("s3")


# ── Cost Explorer helpers ───────────────────────────────────────────

def _ce_daily_by_service(start_iso: str, end_iso: str) -> list[dict]:
    """Returns [{service, cost_usd}] for the given [start, end) window.

    Cost Explorer is exclusive on End. Pass start=YYYY-MM-DD,
    end=next-day to get a single day.
    """
    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": start_iso, "End": end_iso},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    rows = []
    for day in resp.get("ResultsByTime", []):
        for g in day.get("Groups", []):
            amount = float(g["Metrics"]["UnblendedCost"]["Amount"])
            if amount <= 0:
                continue
            rows.append({
                "service": g["Keys"][0],
                "cost_usd": round(amount, 2),
            })
    rows.sort(key=lambda r: r["cost_usd"], reverse=True)
    return rows


def _ce_total(start_iso: str, end_iso: str) -> float:
    """Total UnblendedCost for the window. End is exclusive."""
    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": start_iso, "End": end_iso},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )
    total = 0.0
    for day in resp.get("ResultsByTime", []):
        total += float(day["Total"]["UnblendedCost"]["Amount"])
    return round(total, 2)


def _ce_daily_totals(start_iso: str, end_iso: str) -> list[float]:
    """Per-day totals across [start, end). Used for 7-day median."""
    resp = _ce.get_cost_and_usage(
        TimePeriod={"Start": start_iso, "End": end_iso},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )
    return [
        round(float(day["Total"]["UnblendedCost"]["Amount"]), 2)
        for day in resp.get("ResultsByTime", [])
    ]


# ── Core logic ──────────────────────────────────────────────────────

def collect_report(now: dt.datetime) -> dict[str, Any]:
    """Pull yesterday + 7-day window + MTD; return a digest dict."""
    today_iso = now.strftime("%Y-%m-%d")
    yesterday = (now - dt.timedelta(days=1))
    yesterday_iso = yesterday.strftime("%Y-%m-%d")
    week_ago_iso = (now - dt.timedelta(days=8)).strftime("%Y-%m-%d")
    month_start_iso = now.strftime("%Y-%m-01")

    # 1. Yesterday's spend, broken out by service
    yesterday_services = _ce_daily_by_service(yesterday_iso, today_iso)
    yesterday_total = round(sum(r["cost_usd"] for r in yesterday_services), 2)

    # 2. MTD
    mtd_total = _ce_total(month_start_iso, today_iso)

    # 3. 7-day window, daily totals (for median + anomaly check)
    week_daily = _ce_daily_totals(week_ago_iso, yesterday_iso)
    median_7d = round(statistics.median(week_daily), 2) if week_daily else 0.0

    # 4. Anomaly detection
    anomalies = []
    if median_7d and yesterday_total > median_7d * 3:
        anomalies.append({
            "severity": "red",
            "msg": f"Yesterday ${yesterday_total} is >3x 7-day median ${median_7d}",
        })
    elif median_7d and yesterday_total > median_7d * 1.5:
        anomalies.append({
            "severity": "yellow",
            "msg": f"Yesterday ${yesterday_total} is >1.5x 7-day median ${median_7d}",
        })

    days_in_month = (now.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
    day_of_month = now.day
    burndown_pct = (
        int(mtd_total / MONTHLY_BUDGET_USD * 100) if MONTHLY_BUDGET_USD else 0
    )
    pace_pct = int(day_of_month / days_in_month.day * 100)
    if burndown_pct >= 100:
        anomalies.append({"severity": "red", "msg": f"MTD ${mtd_total} >= ${MONTHLY_BUDGET_USD} budget"})
    elif burndown_pct >= 80:
        anomalies.append({"severity": "red", "msg": f"MTD ${mtd_total} at {burndown_pct}% of ${MONTHLY_BUDGET_USD} budget"})
    elif burndown_pct >= 50 and day_of_month < 15:
        anomalies.append({"severity": "red", "msg": f"MTD at {burndown_pct}% by day {day_of_month}"})
    elif burndown_pct > pace_pct + 20:
        anomalies.append({"severity": "yellow", "msg": f"MTD pace ahead: {burndown_pct}% spent by day {day_of_month}/{days_in_month.day}"})

    # 5. Burn rate projection (linear from MTD)
    burn_rate_monthly = round(mtd_total / day_of_month * days_in_month.day, 2) if day_of_month else 0.0

    # 6. Human-readable digest
    top3 = yesterday_services[:3]
    top3_str = ", ".join(f"{r['service']}=${r['cost_usd']}" for r in top3) or "(none)"
    digest_lines = [
        f"=== aws-cost-sentinel daily {yesterday_iso} ===",
        f"Yesterday:    ${yesterday_total}  (7-day median ${median_7d})",
        f"MTD:          ${mtd_total} / ${MONTHLY_BUDGET_USD} budget  ({burndown_pct}% on day {day_of_month}/{days_in_month.day})",
        f"Burn rate:    ${burn_rate_monthly}/month at current pace",
        f"Top services: {top3_str}",
        "Anomalies:    " + (
            "; ".join(f"[{a['severity']}] {a['msg']}" for a in anomalies)
            if anomalies else "none"
        ),
    ]

    return {
        "yesterday_usd": yesterday_total,
        "yesterday_services": yesterday_services[:10],
        "median_7d_usd": median_7d,
        "mtd_usd": mtd_total,
        "budget_usd": MONTHLY_BUDGET_USD,
        "burndown_pct": burndown_pct,
        "pace_pct": pace_pct,
        "burn_rate_monthly_usd": burn_rate_monthly,
        "day_of_month": day_of_month,
        "days_in_month": days_in_month.day,
        "anomalies": anomalies,
        "digest": "\n".join(digest_lines),
    }


# ── State-file writer ───────────────────────────────────────────────

def write_state(state: dict[str, Any]) -> str:
    """Upload state.json to S3 at the path the dashboard reads."""
    key = f"{FLEET_PREFIX}/{SLUG}.json"
    _s3.put_object(
        Bucket=FLEET_BUCKET,
        Key=key,
        Body=json.dumps(state, indent=2).encode("utf-8"),
        ContentType="application/json",
        CacheControl="no-cache",
    )
    return f"s3://{FLEET_BUCKET}/{key}"


# ── Lambda entry point ─────────────────────────────────────────────

def handler(event, context):
    """EventBridge 09:00 UTC → handler(event, context).

    Always writes a state file (even on failure) so the dashboard
    reflects what happened on the most recent run.
    """
    started = time.time()
    now_utc = dt.datetime.now(dt.timezone.utc)
    ts_ms = int(now_utc.timestamp() * 1000)
    log.info("[%s] start event=%s", SLUG, json.dumps(event)[:200])

    try:
        report = collect_report(now_utc)
        elapsed = round(time.time() - started, 3)
        state = {
            "agent": SLUG,
            "ok": True,
            "ts_ms": ts_ms,
            "elapsed_s": elapsed,
            "event": "done",
            "err": None,
            "as_of_utc": now_utc.isoformat(timespec="seconds"),
            **report,
        }
        s3_uri = write_state(state)
        log.info("[%s] done in %ss → %s", SLUG, elapsed, s3_uri)
        return {"ok": True, "elapsed_s": elapsed, "state_s3_uri": s3_uri,
                "digest": report["digest"]}
    except Exception as exc:                                  # noqa: BLE001
        elapsed = round(time.time() - started, 3)
        tb = traceback.format_exc()
        log.exception("[%s] handler raised", SLUG)
        # Best-effort state-file write so the dashboard sees the failure.
        try:
            write_state({
                "agent": SLUG,
                "ok": False,
                "ts_ms": ts_ms,
                "elapsed_s": elapsed,
                "event": "handler_raised",
                "err": f"{type(exc).__name__}: {exc}",
                "trace_tail": tb.splitlines()[-6:],
                "as_of_utc": now_utc.isoformat(timespec="seconds"),
            })
        except Exception as inner:                            # noqa: BLE001
            log.error("[%s] also failed to write failure state: %s", SLUG, inner)
        raise
