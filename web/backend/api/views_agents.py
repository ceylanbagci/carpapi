"""GET /api/agents/ — live status of the autonomous-agent fleet.

Architecture note (important): App Runner's Django container runs in
VPC egress mode. Outbound traffic only reaches AWS services that have
a VPC endpoint provisioned in the VPC. Today we have endpoints for
Bedrock (Interface) and S3 (Gateway) but NOT for Lambda, EventBridge
Scheduler, CloudWatch, or Cost Explorer. Calling those services from
the Django view returns Connect-timeout errors.

So this view does NOT call AWS APIs directly. Instead, every agent
Lambda writes its latest invocation result to
`s3://<bucket>/fleet/<slug>.json` via the agent_runner dispatcher.
This view reads those objects + merges with the static roster. The
S3 reads go through the free S3 Gateway endpoint — no extra cost.

A side effect of this design: an agent that has NEVER run shows up as
`status=not_deployed` even if its Lambda + schedule are provisioned.
That's fine — the very first invocation will publish the first state
object and the dashboard fills in.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import logging
import os
from typing import Any, Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

log = logging.getLogger("carpapi.api.agents")


# ── Config ───────────────────────────────────────────────────────────
FLEET_BUCKET = os.environ.get("CARPAPI_FLEET_BUCKET",
                              "carpapi-frontend-183617081338")
FLEET_PREFIX = os.environ.get("CARPAPI_FLEET_PREFIX", "fleet").strip("/")

# 3s connect / 5s read; one attempt. The Gateway endpoint should make
# these effectively local — but if S3 burps, we want a fast fail not a
# 30 s wait that ties up gunicorn workers.
_S3_CONFIG = BotoConfig(
    connect_timeout=3, read_timeout=5,
    retries={"max_attempts": 1, "mode": "standard"},
)


# ── Roster ───────────────────────────────────────────────────────────
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
ROSTER_BY_SLUG = {e["slug"]: e for e in ROSTER}


# ── S3 reader ────────────────────────────────────────────────────────

def _s3():
    return boto3.client("s3", config=_S3_CONFIG)


def _list_state_keys() -> list[str]:
    """One ListObjectsV2 — returns the keys for every fleet/<slug>.json."""
    try:
        resp = _s3().list_objects_v2(Bucket=FLEET_BUCKET, Prefix=f"{FLEET_PREFIX}/")
    except ClientError as exc:
        log.warning("list_objects_v2 failed: %s", exc)
        return []
    return [c["Key"] for c in resp.get("Contents", []) or []
            if c["Key"].endswith(".json")]


def _read_state(key: str) -> Optional[dict]:
    try:
        resp = _s3().get_object(Bucket=FLEET_BUCKET, Key=key)
        body = resp["Body"].read()
        return json.loads(body)
    except ClientError as exc:
        log.info("state read miss %s: %s", key, exc)
        return None
    except (ValueError, json.JSONDecodeError) as exc:
        log.warning("state %s malformed: %s", key, exc)
        return None


def _read_all_states() -> dict[str, dict]:
    """Returns {slug: state_dict} for every fleet/<slug>.json that exists.

    Fanned out over a small thread pool — at 14 agents max each S3 GET
    is ~30-50ms, so serial would still complete in <1s, but parallel
    keeps tail latency flat as the fleet grows.
    """
    keys = _list_state_keys()
    if not keys:
        return {}

    def fetch(key: str):
        slug = key.rsplit("/", 1)[-1].removesuffix(".json")
        return slug, _read_state(key)

    out: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(keys))) as ex:
        for slug, state in ex.map(fetch, keys):
            if state:
                out[slug] = state
    return out


# ── Status roll-up ───────────────────────────────────────────────────

def _status_from_state(state: Optional[dict]) -> str:
    """Map a state-file blob to one of:
       online | idle | degraded | failed | not_deployed."""
    if not state:
        return "not_deployed"
    if not state.get("ok"):
        return "failed"
    # Stale check — if the last invocation was > 25h ago for a
    # daily-cadence agent, treat as degraded. We don't enforce cadence
    # here (varies per agent); the SPA can compute it from `ts_ms`.
    ts_ms = state.get("ts_ms") or 0
    age_h = (dt.datetime.now(dt.timezone.utc).timestamp() * 1000 - ts_ms) / 3_600_000
    if age_h > 48:
        return "degraded"
    return "online"


# ── View ─────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([AllowAny])
def agents_overview(request):
    """Live fleet state. See module docstring for the data-flow rationale.

    Returns:
      {
        "agents": [
          { slug, tier, type, cadence, desc,
            deployed: bool,        # has-state proxy for "Lambda exists"
            last_event: dict|null, # last invocation's S3 state blob
            metrics_24h: { invocations, errors },  # derived from state
            status: str,
          },
          ...
        ],
        "summary": { total, online, idle, ..., invocations_24h, errors_24h },
        "as_of_utc": "..."
      }
    """
    try:
        return _agents_overview_inner(request)
    except Exception as exc:  # noqa: BLE001
        import traceback
        tb = traceback.format_exc()
        log.error("agents_overview raised: %s\n%s", exc, tb)
        return Response(
            {"error": f"{type(exc).__name__}: {exc}",
             "trace": tb.splitlines()[-8:]},
            status=500,
        )


def _agents_overview_inner(request):
    slugs_param = request.query_params.get("slug")
    wanted = set(slugs_param.split(",")) if slugs_param else None

    states = _read_all_states()  # one ListObjectsV2 + N GetObject

    out_agents = []
    summary = {"total": 0, "online": 0, "idle": 0, "degraded": 0,
               "failed": 0, "not_deployed": 0,
               "invocations_24h": 0, "errors_24h": 0}

    now_ms = dt.datetime.now(dt.timezone.utc).timestamp() * 1000
    cutoff_24h_ms = now_ms - 24 * 60 * 60 * 1000

    for entry in ROSTER:
        slug = entry["slug"]
        if wanted is not None and slug not in wanted:
            continue
        state = states.get(slug)
        status = _status_from_state(state)
        # We don't have CloudWatch metrics here, so derive the only
        # things we can from the state: whether the most recent
        # invocation falls inside the last 24h (count 1) and whether
        # it failed (count 1).
        invs_24h = 1 if (state and state.get("ts_ms", 0) >= cutoff_24h_ms) else 0
        errs_24h = 1 if (invs_24h and not state.get("ok", True)) else 0
        out_agents.append({
            **entry,
            "deployed": state is not None,
            "last_event": state,
            "metrics_24h": {
                "invocations": invs_24h,
                "errors": errs_24h,
                "duration_avg_ms": (
                    int(state["elapsed_s"] * 1000)
                    if state and state.get("elapsed_s") is not None else None
                ),
            },
            "lambda": None,    # not surfaced through S3 path; SPA tolerates null
            "schedule": None,  # ditto
            "status": status,
        })
        summary["total"] += 1
        summary[status] = summary.get(status, 0) + 1
        summary["invocations_24h"] += invs_24h
        summary["errors_24h"] += errs_24h

    return Response({
        "agents": out_agents,
        "summary": summary,
        "as_of_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    })
