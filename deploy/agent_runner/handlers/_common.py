"""Shared helpers for agent handlers.

Most agents need three things: a Postgres connection, a tiny helper
for the standard return shape, and the ability to skip out fast when
their precondition isn't met (e.g. interactive-only agents that
shouldn't actually do work on the scheduled invocation).

Keeping this in a single module so we don't copy-paste the DSN
construction or the result dict 14 times.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Optional

import psycopg

log = logging.getLogger("carpapi.agent._common")


def db_dsn() -> str:
    """Build a libpq DSN from the standard env vars set on every
    agent Lambda's config."""
    return (
        f"host={os.environ['CARPAPI_DB_HOST']} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5432')} "
        f"dbname={os.environ['CARPAPI_DB_NAME']} "
        f"user={os.environ['CARPAPI_DB_USER']} "
        f"password={os.environ['CARPAPI_DB_PASSWORD']} "
        f"connect_timeout=8"
    )


def db_connect():
    """Open a connection. Handlers must `with db_connect() as conn:`."""
    return psycopg.connect(db_dsn())


def interactive_placeholder(slug: str, description: str) -> dict:
    """Return shape for an agent that's purely interactive — the
    scheduled Lambda fires (to keep the dashboard happy) but the real
    work happens when a human summons it from Claude Code.

    Eventually we can drop these Lambdas + extend the dashboard to
    render `type: interactive` as a different state (not NOT_DEPLOYED,
    not ONLINE either — maybe "STANDBY"). Until then, this is enough
    to keep the row green and explain itself.
    """
    return {
        "ok": True,
        "mode": "interactive_placeholder",
        "agent": slug,
        "note": (
            f"{slug} is interactive — its real work happens when a human "
            "invokes it from Claude Code (see `.claude/agents/<slug>.md`). "
            "This scheduled fire just refreshes the dashboard state."
        ),
        "description": description,
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
