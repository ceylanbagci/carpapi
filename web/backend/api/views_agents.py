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

import datetime as dt
import json
import logging
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

log = logging.getLogger("carpapi.api.agents")


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
    return boto3.client("lambda", region_name="us-east-1")
def _scheduler():
    return boto3.client("scheduler", region_name="us-east-1")
def _logs():
    return boto3.client("logs", region_name="us-east-1")
def _cw():
    return boto3.client("cloudwatch", region_name="us-east-1")


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


def _fetch_lambda_config(slug: str) -> Optional[dict]:
    """Returns Lambda config if it exists, else None."""
    resp = _safe(_lambda().get_function, FunctionName=_lambda_fn_name(slug))
    if not resp:
        return None
    cfg = resp.get("Configuration", {})
    return {
        "arn": cfg.get("FunctionArn"),
        "state": cfg.get("State"),
        "last_modified": cfg.get("LastModified"),
        "memory_mb": cfg.get("MemorySize"),
        "timeout_s": cfg.get("Timeout"),
        "package_type": cfg.get("PackageType"),
    }


def _fetch_schedule_for(slug: str) -> Optional[dict]:
    """Find a schedule in carpapi-agents group whose target points at
    this Lambda. Returns the schedule descriptor or None."""
    list_resp = _safe(_scheduler().list_schedules, GroupName="carpapi-agents")
    if not list_resp:
        return None
    fn_arn_suffix = f"function:{_lambda_fn_name(slug)}"
    for s in list_resp.get("Schedules", []):
        # ListSchedules doesn't include Target — need GetSchedule per item.
        full = _safe(_scheduler().get_schedule,
                     GroupName="carpapi-agents", Name=s["Name"])
        if not full:
            continue
        target_arn = (full.get("Target") or {}).get("Arn") or ""
        if target_arn.endswith(fn_arn_suffix):
            return {
                "name": full.get("Name"),
                "expression": full.get("ScheduleExpression"),
                "timezone": full.get("ScheduleExpressionTimezone"),
                "state": full.get("State"),
            }
    return None


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

@api_view(["GET"])
@permission_classes([AllowAny])
def agents_overview(request):
    """Return live fleet state. Optional `?slug=<one-or-more>` to filter."""
    slugs_param = request.query_params.get("slug")
    wanted = set(slugs_param.split(",")) if slugs_param else None

    out_agents = []
    summary = {"total": 0, "online": 0, "idle": 0, "degraded": 0,
               "failed": 0, "not_deployed": 0,
               "invocations_24h": 0, "errors_24h": 0}

    for entry in ROSTER:
        slug = entry["slug"]
        if wanted is not None and slug not in wanted:
            continue
        cfg = _fetch_lambda_config(slug)
        deployed = cfg is not None
        schedule = _fetch_schedule_for(slug) if deployed else None
        metrics = _fetch_metrics_24h(slug) if deployed else {
            "invocations": 0, "errors": 0, "duration_avg_ms": None,
        }
        last_event = _fetch_last_event(slug) if deployed else None
        status = _status_from(
            deployed=deployed, schedule=schedule,
            last_event=last_event, metrics=metrics,
        )
        out_agents.append({
            **entry,
            "deployed": deployed,
            "lambda": cfg,
            "schedule": schedule,
            "metrics_24h": metrics,
            "last_event": last_event,
            "status": status,
        })
        summary["total"] += 1
        summary[status] = summary.get(status, 0) + 1
        summary["invocations_24h"] += metrics.get("invocations", 0)
        summary["errors_24h"] += metrics.get("errors", 0)

    # Server time so the SPA can render "as of N seconds ago" without
    # depending on the client clock being correct.
    return Response({
        "agents": out_agents,
        "summary": summary,
        "as_of_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    })
