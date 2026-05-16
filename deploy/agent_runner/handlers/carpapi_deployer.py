"""carpapi-deployer — interactive agent placeholder.

The real deployer lives at `.claude/agents/carpapi-deployer.md` and
is summoned by a developer from Claude Code (runs locally — needs
docker buildx, aws cli, and direct ECR push permissions).

This Lambda fires on demand only — there's no schedule. Its sole job
is to keep the dashboard state file fresh so the row reads ONLINE.
"""
from __future__ import annotations

from typing import Any

from ._common import interactive_placeholder


def handle(event: dict, context: Any) -> dict:
    return interactive_placeholder(
        "carpapi-deployer",
        "Bootstraps + deploys + rolls back AWS infrastructure.",
    )
