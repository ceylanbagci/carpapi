"""GET /api/agents/ — live status of the autonomous-agent fleet.

Merges the static roster (the 14 agents defined under
`.claude/agents/<name>.md`) with whatever's actually deployed on AWS:

  - Lambda functions named `carpapi-<agent-name>` (image-backed)
  - EventBridge Scheduler schedules under group `carpapi-agents`
  - Last 24h of CloudWatch invocation + error metrics
  - Most recent done/raised event from the Lambda's log group

Reads only; never mutates. Cached at the App Runner edge for 20s so
the SPA can poll cheaply without hammering CloudWatch.

The endpoint deliberately returns ALL 14 agents — even the ones
that aren't deployed yet — so the SPA can render the full roster
and mark each row as `deployed=true|false`. The frontend doesn't
need to know what's been provisioned; it just renders what the
backend says.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import logging
from typing import Any, Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

log = logging.getLogger("carpapi.api.agents")

# Cap any single AWS API call at 5s and disable boto3's automatic
# retry storm — the dashboard prefers "no data this row" over "30 s
# wait for the whole endpoint." Each individual ClientError is
# swallowed by `_safe`.
_BOTO_CONFIG = BotoConfig(
    connect_timeout=3,
    read_timeout=5,
    retries={"max_attempts": 1, "mode": "standard"},
)


# ── Roster ───────────────────────────────────────────────────────────
# The full 14-agent fleet, keyed by slug. Tier + cadence + description
# are sourced from `.claude/agents/<slug>.md` and `AGENTS.md`. Stays
# in sync with the historical-reference section of the plan file at
# `~/.claude/plans/analyze-this-and-update-peppy-ullman.md`.
#
# We hardcode here rather than parsing the .md files at request time —
# the App Runner container doesn't ship the `.claude/` directory, and
# the agent list changes rarely.
ROSTER = [
    # Tier — INGEST
    {"slug": "scraper-dispatcher",      "tier": "ingest",   "type": "dual",
     "cadence": "daily 04:00 UTC",
     "desc": "Walks active dealers, batches by CMS, dispatches scrapers with rate limits and robots.txt compliance."},
    {"slug": "listing-validator",       "tier": "ingest",   "type": "autonomous",
     "cadence": "per scrape batch",
     "desc": "Normalises raw payloads against schema; quarantines failures to ingest.raw_payloads with parse_error tag."},
    {"slug": "dedupe-sweeper",          "tier": "ingest",   "type": "autonomous",
     "cadence": "daily 06:00 UTC",
     "desc": "Clusters cross-source duplicates into listing_groups. Refuses to merge across different VINs."},
    {"slug": "dealer-prospector",       "tier": "ingest",   "type": "interactive",
     "cadence": "weekly",
     "desc": "Discovers candidate dealers via discover_cms; opens a PR adding new dealers to the active roster."},
    # Tier — ENRICH
    {"slug": "maker-enricher",          "tier": "enrich",   "type": "dual",
     "cadence": "daily 05:00 UTC",
     "desc": "Cold-loop on listings with NULL maker_specs; calls the maker adapter; writes specs back to RDS."},
    {"slug": "maker-site-doctor",       "tier": "enrich",   "type": "autonomous",
     "cadence": "daily 03:00 UTC",
     "desc": "Per make, hits the maker site with a canary VIN. Freezes the adapter on JSON-LD drift."},
    # Tier — QUALITY
    {"slug": "scrape-watchdog",         "tier": "quality",  "type": "autonomous",
     "cadence": "per scrape + hourly",
     "desc": "Reads monitor.scrape_monitor_reports; alerts on null-rate / record-count / HTTP-error breaches."},
    {"slug": "data-quality-auditor",    "tier": "quality",  "type": "interactive",
     "cadence": "weekly",
     "desc": "Scans listings/dealers/maker_specs; writes a markdown audit to monitoring/data_quality/."},
    {"slug": "price-anomaly-detector",  "tier": "quality",  "type": "autonomous",
     "cadence": "daily 07:00 UTC",
     "desc": "Joins listings ↔ listing_price_history; flags rows whose latest ratio is > 1.5 or < 0.5."},
    # Tier — CLOUD-OPS
    {"slug": "carpapi-deployer",        "tier": "cloud",    "type": "interactive",
     "cadence": "n/a",
     "desc": "Bootstraps, deploys, rolls back AWS infra. Already in production."},
    {"slug": "rds-steward",             "tier": "cloud",    "type": "dual",
     "cadence": "daily",
     "desc": "Snapshots, slow-query log, free-storage + connection-count thresholds; promotes pg_stat findings."},
    {"slug": "aws-cost-sentinel",       "tier": "cloud",    "type": "autonomous",
     "cadence": "daily 09:00 UTC",
     "desc": "Daily AWS cost digest from Cost Explorer; alarms at 50/80/100% of monthly budget."},
    # Tier — DELIVERY
    {"slug": "ci-cd-doctor",            "tier": "delivery", "type": "interactive",
     "cadence": "reactive",
     "desc": "Audits failed GitHub Actions runs; cross-references DEPLOY_STATE lessons-learned."},
    {"slug": "chat-quality-evaluator",  "tier": "delivery", "type": "dual",
     "cadence": "per PR + nightly",
     "desc": "Runs offline eval harnesses on PR; full smoke + latency profile nightly against App Runner."},
]


# ── AWS clients (lazy-init so the test path can mock easily) ─────────
def _lambda():
    return boto3.client("lambda", region_name="us-east-1", config=_BOTO_CONFIG)
def _scheduler():
    return boto3.client("scheduler", region_name="us-east-1", config=_BOTO_CONFIG)
def _logs():
    return boto3.client("logs", region_name="us-east-1", config=_BOTO_CONFIG)
def _cw():
    return boto3.client("cloudwatch", region_name="us-east-1", config=_BOTO_CONFIG)


# ── Helpers ──────────────────────────────────────────────────────────

def _lambda_fn_name(slug: str) -> str:
    return f"carpapi-{slug}"


def _safe(fn, *args, **kwargs):
    """Call an AWS API; return None on ClientError (don't crash the
    whole response if one service is throttled or one resource is
    missing).
    """
    try:
        return fn(*args, **kwargs)
    except ClientError as exc:
        log.info("aws call failed: %s", exc)
        return None


def _list_all_carpapi_lambdas() -> dict[str, dict]:
    """One paginated `list-functions` call → map of slug → config dict.

    The slug is derived from the function name (`carpapi-<slug>`).
    Returns only functions in that prefix; ignores everything else in
    the account. One API call regardless of fleet size.
    """
    out: dict[str, dict] = {}
    client = _lambda()
    paginator = client.get_paginator("list_functions")
    try:
        for page in paginator.paginate():
            for fn in page.get("Functions", []) or []:
                name = fn.get("FunctionName", "")
                if not name.startswith("carpapi-"):
                    continue
                slug = name[len("carpapi-"):]
                out[slug] = {
                    "arn": fn.get("FunctionArn"),
                    "state": fn.get("State", "Active"),
                    "last_modified": fn.get("LastModified"),
                    "memory_mb": fn.get("MemorySize"),
                    "timeout_s": fn.get("Timeout"),
                    "package_type": fn.get("PackageType"),
                }
    except ClientError as exc:
        log.warning("list_functions failed: %s", exc)
    return out


def _list_all_schedules_by_target() -> dict[str, dict]:
    """Map of `function:<lambda-name>` suffix → schedule descriptor.

    Uses ListSchedules (no Target) followed by GetSchedule per item
    (which IS what reveals the Target). We do this once globally — at
    fleet scale (14 schedules) that's ~14 calls instead of 14 × N
    inside the per-agent loop.
    """
    out: dict[str, dict] = {}
    list_resp = _safe(_scheduler().list_schedules, GroupName="carpapi-agents")
    if not list_resp:
        return out
    for s in list_resp.get("Schedules", []) or []:
        full = _safe(_scheduler().get_schedule,
                     GroupName="carpapi-agents", Name=s["Name"])
        if not full:
            continue
        target_arn = (full.get("Target") or {}).get("Arn") or ""
        # Key by the trailing `function:<name>` so callers look up by
        # the Lambda name they already know.
        if ":function:" in target_arn:
            key = target_arn.split(":function:", 1)[1]
            out[key] = {
                "name": full.get("Name"),
                "expression": full.get("ScheduleExpression"),
                "timezone": full.get("ScheduleExpressionTimezone"),
                "state": full.get("State"),
            }
    return out


def _fetch_metrics_24h(slug: str) -> dict:
    """Lambda Invocations + Errors + average Duration over the last 24h."""
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(hours=24)
    common = dict(
        Namespace="AWS/Lambda",
        Dimensions=[{"Name": "FunctionName", "Value": _lambda_fn_name(slug)}],
        StartTime=start, EndTime=end, Period=86400,
    )
    out = {"invocations": 0, "errors": 0, "duration_avg_ms": None}
    inv = _safe(_cw().get_metric_statistics, MetricName="Invocations",
                Statistics=["Sum"], **common)
    if inv and inv.get("Datapoints"):
        out["invocations"] = int(inv["Datapoints"][0].get("Sum", 0))
    err = _safe(_cw().get_metric_statistics, MetricName="Errors",
                Statistics=["Sum"], **common)
    if err and err.get("Datapoints"):
        out["errors"] = int(err["Datapoints"][0].get("Sum", 0))
    dur = _safe(_cw().get_metric_statistics, MetricName="Duration",
                Statistics=["Average"], **common)
    if dur and dur.get("Datapoints"):
        out["duration_avg_ms"] = round(dur["Datapoints"][0].get("Average", 0))
    return out


def _fetch_last_event(slug: str) -> Optional[dict]:
    """Pull the most recent `event:"done"` or `event:"handler_raised"`
    line from CloudWatch Logs. We log JSON, so we can substring-grep."""
    group = f"/aws/lambda/{_lambda_fn_name(slug)}"
    end_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    start_ms = end_ms - 7 * 24 * 60 * 60 * 1000  # last 7d
    resp = _safe(
        _logs().filter_log_events,
        logGroupName=group,
        startTime=start_ms, endTime=end_ms,
        filterPattern='?"event":"done" ?"event":"handler_raised"',
        limit=20,
    )
    if not resp:
        return None
    events = resp.get("events") or []
    if not events:
        return None
    # Most recent. Lambda's filterLogEvents doesn't sort — sort here.
    events.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    msg = events[0].get("message", "")
    # Strip leading boilerplate (timestamps from the runtime log).
    try:
        body = msg[msg.index("{") : msg.rindex("}") + 1]
        parsed = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        parsed = {"raw": msg}
    parsed["ts_ms"] = events[0].get("timestamp")
    return parsed


def _status_from(
    *, deployed: bool, schedule: Optional[dict], last_event: Optional[dict],
    metrics: dict,
) -> str:
    """Roll up to one of: online | idle | degraded | failed | not_deployed."""
    if not deployed:
        return "not_deployed"
    if metrics.get("errors", 0) > 0:
        return "failed" if not last_event or last_event.get("event") == "handler_raised" else "degraded"
    if not schedule or schedule.get("state") != "ENABLED":
        return "idle"
    return "online"


# ── View ─────────────────────────────────────────────────────────────

def _enrich_deployed_agent(entry: dict, cfg: dict, schedule: Optional[dict]) -> dict:
    """Per-agent enrichment that talks to CloudWatch + Logs.
    Pulled out so we can fan it out across a ThreadPoolExecutor —
    the metrics + logs calls dominate the wall-clock budget."""
    slug = entry["slug"]
    metrics = _fetch_metrics_24h(slug)
    last_event = _fetch_last_event(slug)
    status = _status_from(
        deployed=True, schedule=schedule,
        last_event=last_event, metrics=metrics,
    )
    return {
        **entry,
        "deployed": True,
        "lambda": cfg,
        "schedule": schedule,
        "metrics_24h": metrics,
        "last_event": last_event,
        "status": status,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def agents_overview(request):
    """Return live fleet state. Optional `?slug=<one-or-more>` to filter.

    Two-phase pipeline:
      1. Bulk-list everything from AWS (one `list_functions`, one
         `list_schedules` + N `get_schedule`). Two round trips total
         regardless of roster size.
      2. For each agent on the static roster, look up bulk data + (only
         if deployed) fan out metrics + last-event fetches in parallel.

    Bounded to ~5s tail latency by the boto config plus the
    ThreadPoolExecutor's wait — no single call can hang the request.

    A top-level try/except returns the exception as JSON in non-debug
    builds so the SPA can show the operator what went wrong — Django's
    default handler500 returns an opaque HTML page that's useless when
    the request comes from `fetch()`.
    """
    try:
        return _agents_overview_inner(request)
    except Exception as exc:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc()
        log.error("agents_overview raised: %s\n%s", exc, tb)
        return Response(
            {
                "error": f"{type(exc).__name__}: {exc}",
                "trace": tb.splitlines()[-8:],
            },
            status=500,
        )


def _agents_overview_inner(request):
    slugs_param = request.query_params.get("slug")
    wanted = set(slugs_param.split(",")) if slugs_param else None

    # Phase 1 — two bulk AWS calls (independent, run in parallel).
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as bulk_ex:
        f_lambdas = bulk_ex.submit(_list_all_carpapi_lambdas)
        f_schedules = bulk_ex.submit(_list_all_schedules_by_target)
        lambda_by_slug = f_lambdas.result()
        schedule_by_fn = f_schedules.result()

    # Phase 2 — enrich each DEPLOYED agent in parallel. Not-deployed
    # agents need no AWS calls so they don't even enter the pool.
    deployed_entries = []
    not_deployed_agents = []
    for entry in ROSTER:
        if wanted is not None and entry["slug"] not in wanted:
            continue
        cfg = lambda_by_slug.get(entry["slug"])
        if cfg is None:
            # Status: not_deployed. Cheap — no AWS calls.
            not_deployed_agents.append({
                **entry,
                "deployed": False,
                "lambda": None,
                "schedule": None,
                "metrics_24h": {"invocations": 0, "errors": 0, "duration_avg_ms": None},
                "last_event": None,
                "status": "not_deployed",
            })
            continue
        sched = schedule_by_fn.get(_lambda_fn_name(entry["slug"]))
        deployed_entries.append((entry, cfg, sched))

    enriched = []
    if deployed_entries:
        # 14 agents max → 14 workers is fine. Each does ~5 AWS calls.
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(14, len(deployed_entries))
        ) as ex:
            enriched = list(ex.map(
                lambda args: _enrich_deployed_agent(*args),
                deployed_entries,
            ))

    out_agents = enriched + not_deployed_agents

    # Re-sort to match ROSTER order (predictable UI rendering).
    roster_index = {e["slug"]: i for i, e in enumerate(ROSTER)}
    out_agents.sort(key=lambda a: roster_index.get(a["slug"], 999))

    summary = {"total": 0, "online": 0, "idle": 0, "degraded": 0,
               "failed": 0, "not_deployed": 0,
               "invocations_24h": 0, "errors_24h": 0}
    for a in out_agents:
        summary["total"] += 1
        summary[a["status"]] = summary.get(a["status"], 0) + 1
        summary["invocations_24h"] += a["metrics_24h"].get("invocations", 0)
        summary["errors_24h"] += a["metrics_24h"].get("errors", 0)

    return Response({
        "agents": out_agents,
        "summary": summary,
        "as_of_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    })
