from __future__ import annotations

"""Engine + session lifecycle for the carpapi DB adapter.

A single `get_engine()` function owns all connection-pool config so
nobody else has to think about it. `session_scope()` is the unit-of-work
context manager — commit on clean exit, rollback on exception.
"""

import logging
import os
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)

_ENGINE: Optional[Engine] = None
_SESSION_FACTORY: Optional[sessionmaker[Session]] = None


def _resolve_url(override: Optional[str] = None) -> str:
    if override:
        return override
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Source .env or export the variable. "
            "Adapter cannot resolve a target Postgres without it."
        )
    return url


def get_engine(url: Optional[str] = None, *, force_new: bool = False) -> Engine:
    """Lazily create one engine per process. Re-use thereafter.

    Pool sizing tuned for the local dev case (small pool, fast failure).
    Production should override via env: CARAPI_DB_POOL_SIZE, _MAX_OVERFLOW.
    """
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None and not force_new:
        return _ENGINE

    pool_size = int(os.environ.get("CARAPI_DB_POOL_SIZE", "5"))
    max_overflow = int(os.environ.get("CARAPI_DB_MAX_OVERFLOW", "10"))

    _ENGINE = create_engine(
        _resolve_url(url),
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,  # recycle connections after 30 min
        future=True,
    )
    _SESSION_FACTORY = sessionmaker(bind=_ENGINE, autoflush=False, autocommit=False, future=True)
    log.debug("created engine pool_size=%d max_overflow=%d", pool_size, max_overflow)
    return _ENGINE


def get_session_factory() -> sessionmaker[Session]:
    if _SESSION_FACTORY is None:
        get_engine()
    assert _SESSION_FACTORY is not None
    return _SESSION_FACTORY


@contextmanager
def session_scope(*, autocommit: bool = True) -> Iterator[Session]:
    """Context manager: yields a session, commits on success, rolls back
    on exception. Always closes.

    Use `autocommit=False` to drive your own transaction boundaries.
    """
    session = get_session_factory()()
    try:
        yield session
        if autocommit:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """Tear down the engine. Useful in tests."""
    global _ENGINE, _SESSION_FACTORY
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None
    _SESSION_FACTORY = None
