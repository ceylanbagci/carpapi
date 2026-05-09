from __future__ import annotations

"""Generate the daily scrape report at monitoring/daily_reports/<date>_scrape_report.md.

MVP scope: reads JSONL EMF lines (one per pipeline run) from a glob, filters by
date, groups by SourceId, renders a markdown summary. Trailing-7-day baselines,
top scraper errors, and CloudWatch ingestion are TODOs — see context/monitoring-rules.md.

Usage:
    carapi-daily-report --date 2026-05-08 --logs-glob 'logs/*.jsonl' --out monitoring/daily_reports

Run with --stdout instead of --out to print without writing a file.
"""

import argparse
import glob
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

# Metric keys we know how to render. Anything else in the EMF line is ignored.
_KNOWN_METRICS = (
    "RecordsFetched",
    "RecordsNormalized",
    "RecordsInserted",
    "RecordsUpdated",
    "RecordsSkipped",
    "RecordsRejected",
    "DurationSeconds",
)


@dataclass
class SourceTotals:
    fetched: int = 0
    normalized: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    rejected: int = 0
    duration_seconds: float = 0.0
    runs: int = 0
    raw_runs: list[dict] = field(default_factory=list)

    @property
    def err_pct(self) -> float:
        if self.fetched == 0:
            return 0.0
        return 100.0 * self.rejected / self.fetched

    @property
    def healthy(self) -> bool:
        # Per context/monitoring-rules.md thresholds (subset checkable from one day):
        #   - fetched > 0
        #   - rejected/fetched <= 0.10
        # Volume-drop check needs baselines (TBD).
        if self.fetched == 0:
            return False
        return self.err_pct <= 10.0


def iter_emf_lines(logs_glob: str) -> Iterator[dict]:
    paths = sorted(glob.glob(logs_glob))
    if not paths:
        log.warning("no log files matched %s", logs_glob)
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw or not raw.startswith("{"):
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if "_aws" not in obj:
                    continue
                yield obj


def line_date(obj: dict) -> date | None:
    try:
        ts_ms = int(obj["_aws"]["Timestamp"])
    except (KeyError, TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()


def aggregate(
    lines: Iterator[dict], target: date
) -> tuple[dict[str, SourceTotals], int]:
    """Return (per-source totals, total_lines_seen_for_date)."""
    by_source: dict[str, SourceTotals] = defaultdict(SourceTotals)
    seen = 0
    for obj in lines:
        if line_date(obj) != target:
            continue
        seen += 1
        source_id = obj.get("SourceId") or "unknown"
        t = by_source[source_id]
        t.runs += 1
        t.fetched += int(obj.get("RecordsFetched", 0) or 0)
        t.normalized += int(obj.get("RecordsNormalized", 0) or 0)
        t.inserted += int(obj.get("RecordsInserted", 0) or 0)
        t.updated += int(obj.get("RecordsUpdated", 0) or 0)
        t.skipped += int(obj.get("RecordsSkipped", 0) or 0)
        t.rejected += int(obj.get("RecordsRejected", 0) or 0)
        t.duration_seconds += float(obj.get("DurationSeconds", 0) or 0)
        t.raw_runs.append({k: obj.get(k) for k in _KNOWN_METRICS})
    return by_source, seen


def render(target: date, by_source: dict[str, SourceTotals], total_seen: int) -> str:
    out: list[str] = []
    out.append(f"# CarPapi scrape report — {target.isoformat()}\n")

    # Summary
    sources_run = len(by_source)
    healthy = sum(1 for t in by_source.values() if t.healthy)
    flagged = sources_run - healthy
    total_inserted = sum(t.inserted for t in by_source.values())
    total_updated = sum(t.updated for t in by_source.values())
    total_rejected = sum(t.rejected for t in by_source.values())
    total_fetched = sum(t.fetched for t in by_source.values())
    total_duration = sum(t.duration_seconds for t in by_source.values())

    out.append("## Summary")
    out.append(f"- Pipeline runs counted: **{total_seen}**")
    out.append(f"- Sources run: **{sources_run}** (healthy: {healthy}, flagged: {flagged})")
    out.append(f"- Records fetched: **{total_fetched:,}**")
    out.append(f"- Records inserted today: **+{total_inserted:,}**")
    out.append(f"- Records updated today: **{total_updated:,}**")
    out.append(f"- Records rejected: **{total_rejected:,}**")
    out.append(f"- Total run duration: **{total_duration:.1f}s**")
    out.append("")

    # Anomalies — only the per-day-checkable ones until 7-day baselines exist.
    anomalies: list[tuple[str, SourceTotals, list[str]]] = []
    for sid, t in sorted(by_source.items()):
        reasons: list[str] = []
        if t.fetched == 0:
            reasons.append("fetched 0 records")
        if t.err_pct > 10.0:
            reasons.append(f"rejection rate {t.err_pct:.1f}% > 10% threshold")
        if reasons:
            anomalies.append((sid, t, reasons))

    if anomalies:
        out.append("## Anomalies (action required)")
        for sid, t, reasons in anomalies:
            out.append(f"### `{sid}`")
            for r in reasons:
                out.append(f"- {r}")
            out.append(
                f"- Runbook: [scrape-failures.md](../../runbooks/scrape-failures.md)"
            )
            out.append("")
    else:
        out.append("## Anomalies")
        out.append("- None detected (per single-day thresholds; baselines TBD)")
        out.append("")

    # Per-source detail table
    out.append("## Per-source detail")
    out.append(
        "| source_id | runs | fetched | normalized | inserted | updated | skipped | rejected | err% | duration |"
    )
    out.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    if by_source:
        for sid, t in sorted(by_source.items()):
            out.append(
                f"| `{sid}` | {t.runs} | {t.fetched:,} | {t.normalized:,} | "
                f"{t.inserted:,} | {t.updated:,} | {t.skipped:,} | {t.rejected:,} | "
                f"{t.err_pct:.1f}% | {t.duration_seconds:.1f}s |"
            )
    else:
        out.append("| _no runs found for this date_ | | | | | | | | | |")
    out.append("")

    # Footer — gaps that aren't filled yet so readers know what's missing.
    out.append("## Gaps not yet covered (see context/monitoring-rules.md)")
    out.append("- 7-day baseline comparison + volume-drop detection")
    out.append("- Top scraper errors with sample exception")
    out.append("- Total active listings + net daily change (requires DB query)")
    out.append("- CloudWatch metrics ingestion (this generator reads local JSONL only)")
    out.append("")

    return "\n".join(out)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="carapi-daily-report",
        description="Generate CarPapi daily scrape report from EMF JSONL logs.",
    )
    p.add_argument(
        "--date",
        default=None,
        help="ISO date (YYYY-MM-DD) to report on. Defaults to today (UTC).",
    )
    p.add_argument(
        "--logs-glob",
        required=True,
        help="Glob pattern for JSONL files containing EMF lines, e.g. 'logs/*.jsonl'",
    )
    p.add_argument(
        "--out",
        default="monitoring/daily_reports",
        help="Output directory; report file is named <date>_scrape_report.md",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print to stdout instead of writing a file (overrides --out).",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    if args.date:
        try:
            target = date.fromisoformat(args.date)
        except ValueError:
            log.error("invalid --date %r (expected YYYY-MM-DD)", args.date)
            return 2
    else:
        target = datetime.now(timezone.utc).date()

    lines = iter_emf_lines(args.logs_glob)
    by_source, seen = aggregate(lines, target)
    report = render(target, by_source, seen)

    if args.stdout:
        sys.stdout.write(report)
        return 0

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target.isoformat()}_scrape_report.md"
    out_path.write_text(report, encoding="utf-8")
    log.info("wrote %s (sources=%d, runs=%d)", out_path, len(by_source), seen)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
