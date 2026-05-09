# Skill: daily-monitoring

Generate the daily scrape report at `monitoring/daily_reports/YYYY-MM-DD_scrape_report.md`.

## Read first
- [context/monitoring-rules.md](../context/monitoring-rules.md) for the metric definitions and alert thresholds
- [pipeline/carapi_pipeline/metrics.py](../pipeline/carapi_pipeline/metrics.py) for what's emitted

## Inputs
- Either CloudWatch metrics (when `CARAPI_CLOUDWATCH_NAMESPACE` is set in production) or local EMF JSON lines from `stdout` of pipeline runs.
- Date being reported on (default: yesterday in UTC).
- Per-source baselines from the trailing 7 days (computed from the same source).

## Output structure
A markdown file with the following sections:

```markdown
# CarPapi scrape report — YYYY-MM-DD

## Summary
- Sources run: N
- Sources healthy: N
- Sources flagged: N (linked anomalies below)
- Total active listings: N
- Net change today: +X / −Y
- Last 7-day trend: [tiny ASCII or sparkline-style summary]

## Anomalies (listed first)
[For each source > 40% volume drop or > 10% rejection rate:]
### <source_id>
- Fetched: N (baseline median: M, drop: X%)
- Rejected: N (X% — threshold 10%)
- Top errors: [list with counts and sample exception]
- Suggested action: <link to runbooks/scrape-failures.md>

## Per-source detail
| source_id | fetched | normalized | inserted | updated | rejected | err% | duration |
|---|---|---|---|---|---|---|---|
| ... |

## Top scraper errors today
[List with count and sample]
```

## Steps
1. Read metrics for the date window (00:00 UTC → 24:00 UTC).
2. Group by `source_id`. Compute the columns above.
3. Pull baselines (7-day median per source per metric) for trend comparison.
4. Identify anomalies per [context/monitoring-rules.md](../context/monitoring-rules.md) thresholds; render those at top.
5. Render markdown, write to `monitoring/daily_reports/YYYY-MM-DD_scrape_report.md`.
6. (Optional) Emit a one-line summary to Slack/SNS for sources flagged.

## CLI shape (when implemented)
```bash
carapi-daily-report --date 2026-05-08 --metrics-source cloudwatch
carapi-daily-report --date 2026-05-08 --metrics-source local --logs-glob 'logs/*.jsonl'
```

## Don't
- Don't compute baselines from < 7 days of data — too noisy. For new sources, mark as "baseline pending" rather than alert spuriously.
- Don't include PII in error samples (truncate / hash).
- Don't link to source URLs in the report itself — keep it operationally focused, not data-leaky.

## Done when
- Yesterday's file exists at the expected path.
- Anomaly section is empty (or all anomalies have a runbook link).
- Generator is idempotent (re-running for the same date produces identical output).
