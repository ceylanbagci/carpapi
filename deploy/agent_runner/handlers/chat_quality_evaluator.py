"""chat-quality-evaluator — nightly offline eval rollup.

The full evals (`tools/smoke_rag_accuracy.py`, `profile_rag_latency.py`)
need Bedrock + App Runner reachability and are heavy. This handler
emits a lightweight heartbeat — counts how many `eval/run_*_eval.py`
files ship in the repo and reports last_event with a TODO note. The
real eval Lambda is a future expansion.
"""
from __future__ import annotations

import datetime as dt
from typing import Any


def handle(event: dict, context: Any) -> dict:
    # Heartbeat-only for now. The real eval suite ships as part of CI
    # (web/backend's GitHub Actions CI runs them on PR) — this Lambda
    # is the autonomous nightly equivalent that we'll fill in once we
    # decide which evals are worth re-running outside CI.
    return {
        "ok": True,
        "agent": "chat-quality-evaluator",
        "mode": "heartbeat",
        "note": (
            "Nightly RAG smoke + latency profile not yet wired into the "
            "Lambda — runs from CI on PRs. This heartbeat keeps the "
            "dashboard row alive."
        ),
        "evals_in_repo": [
            "eval/run_planner_eval.py",
            "eval/run_pii_redaction_eval.py",
            "eval/run_token_cache_eval.py",
            "eval/run_relaxation_eval.py",
        ],
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
