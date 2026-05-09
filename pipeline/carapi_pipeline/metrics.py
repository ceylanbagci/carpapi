from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)



def emit_emf(
    namespace: str,
    dimensions: dict[str, str],
    metrics: dict[str, float],
) -> None:
    """CloudWatch Embedded Metric Format (works with Lambda/ECS log ingestion)."""
    dim_keys = list(dimensions.keys())
    body: dict[str, Any] = {
        "_aws": {
            "Timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": namespace,
                    "Dimensions": [dim_keys],
                    "Metrics": [{"Name": name, "Unit": "Count"} for name in metrics],
                }
            ],
        },
        **dimensions,
        **metrics,
    }
    print(json.dumps(body), file=sys.stdout, flush=True)


def publish_cloudwatch(
    settings,
    metric_name: str,
    value: float,
    dimensions: dict[str, str] | None = None,
) -> None:
    if not settings.cloudwatch_namespace:
        return
    dimensions = dimensions or {}
    try:
        import boto3

        region = settings.aws_region or "us-east-1"
        cw = boto3.client("cloudwatch", region_name=region)
        cw.put_metric_data(
            Namespace=settings.cloudwatch_namespace,
            MetricData=[
                {
                    "MetricName": metric_name,
                    "Value": value,
                    "Unit": "Count",
                    "Dimensions": [{"Name": k, "Value": v} for k, v in dimensions.items()],
                }
            ],
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("CloudWatch put_metric_data skipped: %s", exc)


def pipeline_summary_metrics(
    settings,
    counts: dict[str, int],
    source_id: str | None = None,
    duration_seconds: float | None = None,
) -> None:
    """Emit EMF + optional API metrics for pipeline runs.

    `source_id` is included as a dimension when provided, so the daily report
    can break metrics down per source. `duration_seconds` is emitted as a
    separate metric (Unit=Seconds) when provided.
    """
    ns = settings.cloudwatch_namespace or "CarPapi/Pipeline"
    dimensions = {"Service": "pipeline", "Environment": "local"}
    if source_id:
        dimensions["SourceId"] = source_id
    metrics = {k: float(v) for k, v in counts.items()}
    if duration_seconds is not None:
        metrics["DurationSeconds"] = float(duration_seconds)
    emit_emf(ns, dimensions, metrics)
    if settings.cloudwatch_namespace:
        cw_dims = {k: v for k, v in dimensions.items() if k == "SourceId"}
        for name, val in metrics.items():
            publish_cloudwatch(settings, name, val, cw_dims or None)
