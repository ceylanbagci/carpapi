from __future__ import annotations

"""Post-scrape statistical monitor.

Hard rule (context/scraper-rules.md guideline 4):
    Scraping contains zero AI. Monitoring of scrape results contains
    zero AI. Both are pure-Python statistical checks against documented
    thresholds.

Inputs: a list of post-normalization listing dicts plus optional HTTP
request stats. Outputs: a structured `ScrapeMonitorReport` with flags
populated for any threshold breach.

Wire this into every scraper run in carpapi/scrapers/* — call analyze()
on the records it emits before they're handed off to the ingest pipeline.
"""

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class ScrapeMonitorThresholds:
    """Tunable thresholds. Override per source by passing a custom instance."""

    min_record_count: int = 1
    """At least one record must come back; zero is itself an alarm."""

    max_null_rate_per_field: dict[str, float] = field(
        default_factory=lambda: {
            "vin": 0.30,
            "price_amount": 0.10,
            "make": 0.05,
            "model": 0.05,
            "mileage": 0.20,
            "year": 0.05,
        }
    )
    """Per-field null-rate ceilings. Tighter is stricter."""

    max_duplicate_rate: float = 0.05
    """Within-batch duplicates by external_id. Tight by default — pagination
    bugs usually push this up sharply, so even 5% is suspect."""

    max_http_error_rate: float = 0.05
    """HTTP 4xx/5xx rate across requests issued during the scrape."""

    min_acceptable_record_count: int | None = None
    """Optional absolute floor for record count when a baseline is known.
    Most useful for sources whose volume is roughly stable day-to-day."""


@dataclass
class ScrapeMonitorReport:
    source_id: str
    record_count: int
    null_rates: dict[str, float]
    duplicate_rate: float
    http_error_rate: float
    flags: list[str]
    thresholds: ScrapeMonitorThresholds

    @property
    def healthy(self) -> bool:
        return not self.flags


def analyze(
    records: list[dict],
    *,
    source_id: str,
    http_errors: int = 0,
    http_total: int = 0,
    thresholds: ScrapeMonitorThresholds | None = None,
) -> ScrapeMonitorReport:
    """Run the threshold checks. No I/O, no AI — pure functions."""
    th = thresholds or ScrapeMonitorThresholds()
    flags: list[str] = []

    # 1. Record count.
    if len(records) < th.min_record_count:
        flags.append(
            f"record count {len(records)} below minimum {th.min_record_count}"
        )
    if (
        th.min_acceptable_record_count is not None
        and len(records) < th.min_acceptable_record_count
    ):
        flags.append(
            f"record count {len(records)} below acceptable floor "
            f"{th.min_acceptable_record_count}"
        )

    # 2. Null rates per field.
    null_rates: dict[str, float] = {}
    for field_name, max_rate in th.max_null_rate_per_field.items():
        if not records:
            null_rates[field_name] = 0.0
            continue
        nulls = sum(1 for r in records if _is_nullish(r.get(field_name)))
        rate = nulls / len(records)
        null_rates[field_name] = rate
        if rate > max_rate:
            flags.append(
                f"{field_name} null rate {rate:.1%} exceeds threshold "
                f"{max_rate:.1%}"
            )

    # 3. Within-batch duplicates by external_id.
    dup_rate = 0.0
    if records:
        ids = [r.get("external_id") for r in records if r.get("external_id")]
        if ids:
            unique = len(set(ids))
            dup_rate = 1.0 - (unique / len(ids))
            if dup_rate > th.max_duplicate_rate:
                flags.append(
                    f"within-batch duplicate rate {dup_rate:.1%} exceeds "
                    f"threshold {th.max_duplicate_rate:.1%}"
                )

    # 4. HTTP error rate.
    err_rate = 0.0
    if http_total > 0:
        err_rate = http_errors / http_total
        if err_rate > th.max_http_error_rate:
            flags.append(
                f"HTTP error rate {err_rate:.1%} exceeds threshold "
                f"{th.max_http_error_rate:.1%}"
            )

    return ScrapeMonitorReport(
        source_id=source_id,
        record_count=len(records),
        null_rates=null_rates,
        duplicate_rate=dup_rate,
        http_error_rate=err_rate,
        flags=flags,
        thresholds=th,
    )


def render_text(report: ScrapeMonitorReport) -> str:
    """Compact human-readable summary; meant for stdout / log lines."""
    lines: list[str] = [f"Scrape monitor — {report.source_id}"]
    lines.append(f"  records: {report.record_count}")
    if report.null_rates:
        nulls = ", ".join(f"{k}={v:.1%}" for k, v in sorted(report.null_rates.items()))
        lines.append(f"  null rates: {nulls}")
    lines.append(f"  duplicate rate: {report.duplicate_rate:.1%}")
    lines.append(f"  HTTP error rate: {report.http_error_rate:.1%}")
    if report.flags:
        lines.append("  status: FLAGGED")
        for flag in report.flags:
            lines.append(f"    - {flag}")
    else:
        lines.append("  status: healthy")
    return "\n".join(lines)


def _is_nullish(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, tuple, dict, set)) and len(value) == 0:
        return True
    return False
