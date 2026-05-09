#!/usr/bin/env python3
"""Generate the NJ dealers report from output/dealers_final.json.

Writes two files:
  - output/report_nj_agent.txt  (human-readable, sorted by count desc)
  - output/report_nj_agent.json (machine-readable summary)

Usage:
    python tools/generate_nj_report.py
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

INPUT = Path("output/dealers_final.json")
TXT_OUT = Path("output/report_nj_agent.txt")
JSON_OUT = Path("output/report_nj_agent.json")

NAME_COL = 32
COUNT_COL = 6
RULE = "=" * 50
THIN_RULE = "-" * 50


def load_dealers(path: Path) -> list[dict]:
    with path.open() as fh:
        return json.load(fh)


def build_summary(dealers: list[dict]) -> dict:
    by_make_counter: Counter[str] = Counter()
    make_id: dict[str, str] = {}
    needs_verify_by_make: defaultdict[str, int] = defaultdict(int)

    for d in dealers:
        make = d.get("make") or "Unknown"
        by_make_counter[make] += 1
        if "make_id" in d and make not in make_id:
            make_id[make] = d["make_id"]
        if d.get("website_needs_verification"):
            needs_verify_by_make[make] += 1

    by_make = [
        {
            "make": make,
            "make_id": make_id.get(make),
            "count": count,
            "needs_verification": needs_verify_by_make.get(make, 0),
        }
        for make, count in by_make_counter.most_common()
    ]

    return {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(INPUT),
        "total_dealers": len(dealers),
        "distinct_makes": len(by_make_counter),
        "websites_needing_verification": sum(needs_verify_by_make.values()),
        "by_make": by_make,
    }


def render_txt(summary: dict) -> str:
    lines: list[str] = []
    lines.append(RULE)
    lines.append("  DealerRater NJ — Dealers Final Report")
    lines.append(f"  Source: {summary['source']}")
    lines.append(f"  Generated: {summary['timestamp']}")
    lines.append(RULE)
    lines.append(f"{'Make':<{NAME_COL}}{'Dealers':>{COUNT_COL}}")
    lines.append(THIN_RULE)
    for row in summary["by_make"]:
        marker = "  *" if row["needs_verification"] else ""
        name = f"{row['make']}{marker}"
        lines.append(f"{name:<{NAME_COL}}{row['count']:>{COUNT_COL}}")
    lines.append(THIN_RULE)
    lines.append(f"{'TOTAL':<{NAME_COL}}{summary['total_dealers']:>{COUNT_COL}}")
    lines.append(RULE)
    lines.append(f"  Distinct makes:               {summary['distinct_makes']}")
    lines.append(
        f"  Websites needing verification: {summary['websites_needing_verification']}"
    )
    lines.append(RULE)
    if summary["websites_needing_verification"]:
        lines.append("")
        lines.append("  * = at least one dealer's website still needs verification.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    dealers = load_dealers(INPUT)
    summary = build_summary(dealers)

    JSON_OUT.write_text(json.dumps(summary, indent=2) + "\n")
    TXT_OUT.write_text(render_txt(summary))

    print(f"Wrote {TXT_OUT} and {JSON_OUT}")
    print(f"  total_dealers = {summary['total_dealers']}")
    print(f"  distinct_makes = {summary['distinct_makes']}")


if __name__ == "__main__":
    main()
