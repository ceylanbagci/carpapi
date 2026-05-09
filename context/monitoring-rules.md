# Monitoring Rules

## Default cadence — once per day
All scheduled jobs (scrape runs, monitoring report, dedup audit, eval re-runs) default to **once per day**, off-peak. Do not schedule recurring jobs at a higher frequency without an explicit reason documented per-job. Hourly or sub-hourly cadences add cost and noise without proportional value at MVP scale.

Per-source overrides can land in [runbooks/daily-schedule.md](../runbooks/daily-schedule.md) when there's a real freshness need (e.g., hot-inventory tier). Default stays daily until then.

## Two monitoring layers
1. **Per-pipeline statistical checks** — runs immediately after each scraper, no AI. Implementation: [carpapi/monitor/scrape_monitor.py](../carpapi/monitor/scrape_monitor.py). Threshold-based: record count, null rates per field, within-batch duplicate rate, HTTP error rate.
2. **Daily aggregated report** — runs once per day, reads accumulated EMF metrics, renders the per-source markdown summary. Implementation: [pipeline/carapi_pipeline/daily_report.py](../pipeline/carapi_pipeline/daily_report.py).

Neither layer uses an LLM. If a future "AI summary of overnight runs" is wanted, it goes through [ai-cache-rules.md](ai-cache-rules.md) and only consumes the report's anonymized aggregates — never raw records.

## Authoritative
- Schedule: [runbooks/daily-schedule.md](../runbooks/daily-schedule.md)
- Failure response: [runbooks/scrape-failures.md](../runbooks/scrape-failures.md)
- Metric emission: [pipeline/carapi_pipeline/metrics.py](../pipeline/carapi_pipeline/metrics.py)

## Per-pipeline-run metrics (already emitted)
EMF lines on stdout; optional `cloudwatch:put_metric_data` when `CARAPI_CLOUDWATCH_NAMESPACE` is set.

| Metric | Meaning | Healthy range (per source per day) |
|---|---|---|
| `RecordsFetched` | items pulled from source | source-specific baseline |
| `RecordsNormalized` | passed JSON-Schema validation | within 5% of `RecordsFetched` |
| `RecordsInserted` | new rows | varies; should not be 100% of fetched after first run |
| `RecordsUpdated` | upserts onto existing dedupe_key | majority for stable sources |
| `RecordsSkipped` | unchanged (raw_checksum match) | high is fine |
| `RecordsRejected` | failed normalization | ≤ 1% of fetched |

## Alert thresholds
Wire as CloudWatch alarms (or local equivalent):
- `RecordsFetched == 0` for any source in a 24h window → page.
- `RecordsRejected / RecordsFetched > 0.10` → page (likely schema drift on source HTML).
- `RecordsNormalized` drops > 40% vs. trailing 7-day median for a source → investigate.
- No successful pipeline run in 24h → page.
- DB insert error rate > 0 → investigate.

## Daily report

**Generator (built):** `carapi-daily-report` CLI in [pipeline/carapi_pipeline/daily_report.py](../pipeline/carapi_pipeline/daily_report.py). Output lands at `monitoring/daily_reports/YYYY-MM-DD_scrape_report.md`.

```bash
# After `pip install -e pipeline`:
carapi-daily-report --date 2026-05-08 --logs-glob 'logs/*.jsonl'

# Or run directly:
python -m carapi_pipeline.daily_report --date 2026-05-08 --logs-glob 'logs/*.jsonl' --stdout
```

EMF lines come from pipeline runs (each `run_ingest_batch()` emits one EMF line per source via `pipeline_summary_metrics`). To collect them, redirect pipeline stdout to a JSONL file: `carapi-run-pipeline >> logs/$(date -u +%F).jsonl`.

**Currently includes:**
- Per-source: runs, fetched, normalized, inserted, updated, skipped, rejected, error rate, total duration.
- Anomalies (single-day thresholds): rejection rate > 10%, fetched = 0.

**Still TBD (tracked in the report's "Gaps" footer):**
- Per-source 7-day baseline + volume-drop detection (needs ≥ 7 days of history).
- Top scraper errors with sample exception (needs structured error events on the EMF stream — `metrics.py` does not emit those yet).
- Total active listings + net daily change (needs a DB query — keep generator stdlib-only for now or split into a second pass).
- CloudWatch ingestion path (today reads only local JSONL).

## Query-side monitoring (gap)
Track per-API-request:
- `query_planner_latency_ms`, `query_exec_latency_ms`, `total_latency_ms`
- `result_count` (distribution; especially zero-result rate)
- `parsed_filters` (anonymized; for distribution analysis)

Not implemented yet. Add when LLM planner ships (cost tracking matters).

## What to watch most closely
1. Per-source freshness — stale data is worse than no data; users will lose trust fast.
2. Rejection rate — schema drift is the most common live-scraping failure mode.
3. Dedup-key collisions on different physical cars (manifests as listings being silently overwritten).
