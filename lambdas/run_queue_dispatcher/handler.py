"""run-queue-dispatcher — bridges the SPA's Run button to a real Lambda invoke.

Why this exists:
  App Runner's Django container runs in VPC egress mode, and the VPC
  has no Interface endpoint for AWS Lambda — only S3 (Gateway) and
  Bedrock. A boto3 lambda.invoke() from Django Connect-times-out. So
  the SPA flow is:

      SPA → POST /api/agents/<slug>/run/
      Django → s3:PutObject  s3://<bucket>/fleet/queue/<slug>.json   (works, has Gateway endpoint)
      S3 ObjectCreated event → this Lambda
      this Lambda → lambda:InvokeFunction("carpapi-<slug>", payload)
      this Lambda → s3:DeleteObject (so the same marker doesn't re-fire)

Trigger:
  S3 event notification on the carpapi-frontend bucket for ObjectCreated:*
  with prefix=`fleet/queue/` and suffix=`.json`. Configured via
  put-bucket-notification-configuration.

Marker shape (written by api/views_agents.py::agent_run):
  {
    "slug": "scraper-dispatcher",
    "lambda_name": "carpapi-scraper-dispatcher",
    "requested_at_ms": int,
    "requested_by": str,
    "reason": str,
    "idempotency_key": uuid hex,
    "payload": { ... },   # forwarded as the target Lambda's event body
  }

Concurrency / dedup:
  S3 notifications are at-least-once. Two safeguards:
    1. The dispatcher deletes the marker after a successful Invoke; a
       duplicate event for the same key 404s on get_object and is a
       no-op.
    2. The InvocationType=Event call is fire-and-forget; if it really
       did double-fire, the worst case is the target agent runs twice.
       That's safe for every agent in the roster (all idempotent).
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

log = logging.getLogger()
log.setLevel(logging.INFO)

FLEET_BUCKET = os.environ.get("CARPAPI_FLEET_BUCKET",
                              "carpapi-frontend-183617081338")
FLEET_PREFIX = os.environ.get("CARPAPI_FLEET_PREFIX", "fleet").strip("/")
ALLOWED_LAMBDA_PREFIX = os.environ.get("CARPAPI_ALLOWED_LAMBDA_PREFIX",
                                       "carpapi-")

_s3 = boto3.client("s3")
_lambda = boto3.client("lambda")


def _read_marker(bucket: str, key: str) -> dict | None:
    try:
        resp = _s3.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read())
    except ClientError as exc:
        # 404 → marker already consumed by a previous delivery; not an error.
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            log.info("marker %s already deleted; skipping", key)
            return None
        log.error("get_object failed for %s: %s", key, exc)
        raise
    except (ValueError, json.JSONDecodeError) as exc:
        log.error("marker %s malformed JSON: %s", key, exc)
        return None


def _invoke_target(marker: dict) -> dict:
    fn_name = marker.get("lambda_name") or f"carpapi-{marker['slug']}"
    if not fn_name.startswith(ALLOWED_LAMBDA_PREFIX):
        raise ValueError(
            f"refusing to invoke {fn_name!r}: must start with "
            f"{ALLOWED_LAMBDA_PREFIX!r}"
        )
    payload = {
        "source": "run-queue-dispatcher",
        "slug": marker["slug"],
        "requested_at_ms": marker.get("requested_at_ms"),
        "requested_by": marker.get("requested_by"),
        "reason": marker.get("reason"),
        "idempotency_key": marker.get("idempotency_key"),
        **(marker.get("payload") or {}),
    }
    resp = _lambda.invoke(
        FunctionName=fn_name,
        InvocationType="Event",            # async, fire-and-forget
        Payload=json.dumps(payload).encode("utf-8"),
    )
    return {
        "lambda_name": fn_name,
        "invoke_status": resp.get("StatusCode"),
        "invoke_request_id": resp["ResponseMetadata"].get("RequestId"),
    }


def _delete_marker(bucket: str, key: str) -> None:
    try:
        _s3.delete_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        # Non-fatal — at-least-once semantics handle a stale marker on
        # the next delivery (or by an EventBridge sweeper if added).
        log.warning("delete_object failed for %s: %s", key, exc)


def handler(event: dict, context: Any) -> dict:
    """Lambda entry. Processes every Record in the S3 event batch."""
    started = time.time()
    processed = []
    errors = []
    for rec in event.get("Records", []):
        try:
            bucket = rec["s3"]["bucket"]["name"]
            key    = unquote_plus(rec["s3"]["object"]["key"])
            if not key.startswith(f"{FLEET_PREFIX}/queue/"):
                log.info("ignoring out-of-scope key %s", key)
                continue
            marker = _read_marker(bucket, key)
            if marker is None:
                continue   # already deleted or malformed
            result = _invoke_target(marker)
            _delete_marker(bucket, key)
            processed.append({
                "key": key,
                "slug": marker.get("slug"),
                "result": result,
            })
        except Exception as exc:                     # noqa: BLE001
            log.exception("dispatch failed for record %s", rec)
            errors.append({"record": rec, "error": str(exc)})

    elapsed = round(time.time() - started, 3)
    log.info("dispatched=%s errors=%s in %ss",
             len(processed), len(errors), elapsed)
    return {"processed": processed, "errors": errors, "elapsed_s": elapsed}
