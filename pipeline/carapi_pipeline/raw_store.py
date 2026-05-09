from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_raw_payload(
    *,
    settings,
    source_id: str,
    batch_id: str,
    payload: dict[str, Any],
    body_bytes: bytes | None = None,
) -> str:
    """Persist raw scrape payload locally and optionally to S3. Returns checksum hex."""
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    if body_bytes is not None:
        raw = body_bytes
    digest = hashlib.sha256(raw).hexdigest()
    rel = f"{source_id}/{batch_id}.json"
    local_root = Path(settings.raw_local_dir)
    local_root.mkdir(parents=True, exist_ok=True)
    path = local_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if body_bytes is None:
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    else:
        path.write_bytes(body_bytes)

    if settings.s3_bucket:
        try:
            import boto3

            region = settings.aws_region or "us-east-1"
            client = boto3.client("s3", region_name=region)
            key = f"{settings.s3_prefix.strip('/')}/{rel}"
            client.put_object(
                Bucket=settings.s3_bucket,
                Key=key,
                Body=raw,
                ContentType="application/json",
                Metadata={"scraped_at": _utc_now_iso(), "source_id": source_id},
            )
            log.info("Uploaded raw payload to s3://%s/%s", settings.s3_bucket, key)
        except Exception as exc:  # noqa: BLE001
            log.warning("S3 upload failed (continuing with local only): %s", exc)

    return digest
