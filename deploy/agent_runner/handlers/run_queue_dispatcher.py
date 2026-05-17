"""run-queue-dispatcher — S3-triggered agent invoker.

How it gets called:
  s3://carpapi-frontend-183617081338/fleet/queue/<slug>-<ts>.json
   ↓ ObjectCreated:*
  Lambda `carpapi-run-queue-dispatcher`
   ↓ this handler
  lambda:InvokeFunction("carpapi-<slug>", InvocationType=Event)
   ↓
  Marker deleted; agent state file refreshes when the agent
  finishes its work.

Why this exists: App Runner can't call `lambda:InvokeFunction` from
its VPC (only Bedrock + S3 endpoints are provisioned). So the Django
backend writes a marker to S3 and this Lambda — which lives OUTSIDE
the VPC — translates that into a real invoke.

Failure model:
  - Marker missing key fields → DLQ + alert (corrupt write).
  - Slug not in the allowlist → log + skip (delete the marker).
  - Lambda.InvokeFunction fails → DLQ (do NOT delete the marker
    so a manual retry from the DLQ can re-fire it).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from typing import Any
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger("carpapi.agent.run_queue_dispatcher")

ALLOWED_SLUGS = {
    "aws-cost-sentinel", "scraper-dispatcher", "listing-validator",
    "dedupe-sweeper", "dealer-prospector", "maker-enricher",
    "maker-site-doctor", "scrape-watchdog", "data-quality-auditor",
    "price-anomaly-detector", "rds-steward", "ci-cd-doctor",
    "chat-quality-evaluator", "carpapi-deployer",
    # NEW-listings-only scraper; spec at
    # .claude/agents/listing_agents/listing_scrapper.md.
    "listing-scrapper",
}

# Same naming convention used by the dashboard: Lambda name is
# `carpapi-<slug>` except the `carpapi-deployer` slug already has the
# prefix so it ended up as `carpapi-carpapi-deployer` (kept for
# back-compat — see views_agents.ROSTER).
SLUG_TO_LAMBDA = {s: f"carpapi-{s}" for s in ALLOWED_SLUGS}
SLUG_TO_LAMBDA["carpapi-deployer"] = "carpapi-carpapi-deployer"


def _process_record(rec: dict, *, s3, lam) -> dict:
    """Handle one S3 event record."""
    bucket = rec["s3"]["bucket"]["name"]
    key = unquote_plus(rec["s3"]["object"]["key"])

    log.info("processing marker s3://%s/%s", bucket, key)

    # Skip non-queue keys (S3 notifications are scoped by prefix on the
    # bucket side, but defense-in-depth: re-check the prefix here too).
    if not key.startswith("fleet/queue/"):
        return {"key": key, "skipped": True, "reason": "wrong prefix"}

    # Read the marker payload (small JSON).
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        body = json.loads(obj["Body"].read())
    except ClientError as exc:
        log.error("get marker failed %s: %s", key, exc)
        # Don't delete — let the DLQ catch the retry.
        return {"key": key, "ok": False, "error": str(exc)[:120]}

    slug = (body.get("slug") or "").strip()
    if slug not in ALLOWED_SLUGS:
        log.warning("marker %s has bad slug %r — deleting", key, slug)
        _safe_delete(s3, bucket, key)
        return {"key": key, "ok": False, "error": f"bad slug: {slug!r}"}

    fn = SLUG_TO_LAMBDA[slug]
    invoke_payload = {
        "agent_name": slug,
        "queued_by": body.get("queued_by"),
        "queued_at_utc": body.get("queued_at_utc"),
        "marker_s3_key": key,
        "invoked_from": "run-queue-dispatcher",
    }
    try:
        resp = lam.invoke(
            FunctionName=fn,
            InvocationType="Event",  # async — fire-and-forget
            Payload=json.dumps(invoke_payload).encode("utf-8"),
        )
    except ClientError as exc:
        log.error("invoke %s failed: %s", fn, exc)
        # Leave the marker so DLQ retry can re-fire.
        return {"key": key, "ok": False, "error": str(exc)[:120]}

    log.info(
        "invoked %s queued_by=%s status=%s",
        fn, body.get("queued_by", "?"), resp.get("StatusCode"),
    )

    # Async invoke succeeded → delete the marker so we don't re-fire it
    # if S3 ever replays the event (it can, on rare consistency issues).
    _safe_delete(s3, bucket, key)

    return {
        "key": key,
        "ok": True,
        "agent": slug,
        "function": fn,
        "invoke_status": resp.get("StatusCode"),
    }


def _safe_delete(s3, bucket: str, key: str) -> None:
    try:
        s3.delete_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        log.warning("delete marker %s failed: %s", key, exc)


def handle(event: dict, context: Any) -> dict:
    """S3 event source delivers one or more Records. Each one is a
    PutObject on fleet/queue/*.json that we should process."""
    s3 = boto3.client("s3", region_name="us-east-1")
    lam = boto3.client("lambda", region_name="us-east-1")

    results = []
    for rec in event.get("Records", []) or []:
        results.append(_process_record(rec, s3=s3, lam=lam))

    return {
        "ok": all(r.get("ok", False) for r in results) if results else True,
        "processed": len(results),
        "results": results,
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
