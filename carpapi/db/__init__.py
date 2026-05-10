"""CarPapi PostgreSQL adapter.

Single layer that owns:
  - Connection / pool management (engine.py)
  - Schema bootstrap (schema.sql + cli.py)
  - Typed CRUD helpers per domain (repositories.py)
  - SQLAlchemy ORM models for the new tables (models.py)

The pre-existing `carapi_pipeline.models.Listing` is *not* duplicated
here — we share the underlying table; this package only adds new tables
and convenience helpers.

CLI entry point:  python -m carpapi.db {init|status|seed-dealers|drop-all}

See carpapi/db/schema.sql for the structural source of truth.
"""

from carpapi.db.engine import get_engine, session_scope
from carpapi.db.models import (
    AICall,
    Base,
    Dealer,
    DailyReport,
    IngestRun,
    ListingGroup,
    ListingPriceHistory,
    RawPayload,
    RejectionLog,
    ScrapeMonitorReport,
    Source,
    TokenCacheRow,
)
from carpapi.db.repositories import (
    AICacheRepo,
    DealerRepo,
    IngestRepo,
    ListingGroupRepo,
    MonitorRepo,
    PriceHistoryRepo,
    SourceRepo,
)

__all__ = [
    # engine
    "get_engine",
    "session_scope",
    # models
    "Base",
    "Dealer",
    "ListingGroup",
    "ListingPriceHistory",
    "Source",
    "IngestRun",
    "RawPayload",
    "RejectionLog",
    "ScrapeMonitorReport",
    "DailyReport",
    "TokenCacheRow",
    "AICall",
    # repositories
    "DealerRepo",
    "ListingGroupRepo",
    "PriceHistoryRepo",
    "SourceRepo",
    "IngestRepo",
    "MonitorRepo",
    "AICacheRepo",
]
