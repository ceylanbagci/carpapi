"""Post-scrape statistical monitor — zero AI used, threshold-based only.

Per context/scraper-rules.md (guideline 4): scrapers contain no LLM calls;
monitoring inspects the records they emit using pure statistical checks.
"""

from carpapi.monitor.scrape_monitor import (
    ScrapeMonitorReport,
    ScrapeMonitorThresholds,
    analyze,
    render_text,
)

__all__ = [
    "ScrapeMonitorReport",
    "ScrapeMonitorThresholds",
    "analyze",
    "render_text",
]
