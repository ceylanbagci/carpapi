"""ci-cd-doctor — reactive agent placeholder.

Real work is triggered by GitHub Actions failures (or a developer
clicking ▶ Run from the dashboard). The handler just refreshes the
state file so the row reads ONLINE.
"""
from __future__ import annotations

from typing import Any

from ._common import interactive_placeholder


def handle(event: dict, context: Any) -> dict:
    return interactive_placeholder(
        "ci-cd-doctor",
        "Audits failed GitHub Actions runs; cross-references "
        "DEPLOY_STATE lessons-learned. Reactive — fires when a workflow "
        "fails (or on operator demand).",
    )
