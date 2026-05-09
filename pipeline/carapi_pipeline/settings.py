from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val


@dataclass(frozen=True)
class Settings:
    database_url: str
    raw_local_dir: str
    s3_bucket: str | None
    s3_prefix: str
    aws_region: str | None
    cloudwatch_namespace: str | None
    source_priority: dict[str, int]


def load_settings() -> Settings:
    db = _env("DATABASE_URL")
    if not db:
        raise RuntimeError("DATABASE_URL is required for pipeline runs")
    priority_raw = _env("CARAPI_SOURCE_PRIORITY", "demo_dealer=10,other_feed=5,default=0")
    priority: dict[str, int] = {}
    for part in priority_raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        priority[k.strip()] = int(v.strip())

    return Settings(
        database_url=db,
        raw_local_dir=_env("CARAPI_RAW_DIR", "./data/raw") or "./data/raw",
        s3_bucket=_env("CARAPI_S3_BUCKET"),
        s3_prefix=_env("CARAPI_S3_PREFIX", "raw/scrapes") or "raw/scrapes",
        aws_region=_env("AWS_REGION") or _env("AWS_DEFAULT_REGION"),
        cloudwatch_namespace=_env("CARAPI_CLOUDWATCH_NAMESPACE"),
        source_priority=priority,
    )
