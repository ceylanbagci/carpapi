"""CarPapi autonomous-agent dispatcher.

One Docker image (carpapi-agent-base) backs every Lambda + Fargate
task in the fleet. The runtime reads `AGENT_NAME` from the env, imports
the matching `handlers/<name>.py` module, and runs its `handle()`
function.

The same module is invoked two ways:

  1. Lambda (image-backed). `lambda_handler(event, context)` is the
     entrypoint. We pass the Lambda event + a fabricated context dict
     to the handler.

  2. Fargate ECS task. The entrypoint runs `python -m agent_runner`
     and `if __name__ == '__main__'` falls back to `handle()` with
     an empty event.

Handlers must expose:

  def handle(event: dict, context: dict) -> dict:
      ...

Return value is logged and (for Lambda) becomes the function's response.
A handler that wants to send email uses
`notifications.email.send_email()` (the same in-process helper the
Django app uses; the agent image carries the same code path).

Failure model:
  - Handler raises → dispatcher logs + re-raises so Lambda's retry +
    DLQ kick in.
  - Handler returns `{"ok": False, ...}` → logged but not raised
    (operational failure, e.g. "no data to process").

Per `skills/rds-first-skill.md`: every handler that touches the DB
should rely on `CARPAPI_DB_*` env vars set by the task config, NOT
hard-code anything. The image NEVER bakes credentials.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import sys
import time
import traceback
from typing import Any, Optional

# ── Logging ──────────────────────────────────────────────────────────
# CloudWatch Logs swallow stderr in Lambda; we log to stdout with a
# JSON formatter so log-insights queries can grep by field. Lambda's
# default handler is fine; we just bump the level.
_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=_LOG_LEVEL,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","mod":"%(name)s","msg":"%(message)s"}',
    stream=sys.stdout,
)
log = logging.getLogger("carpapi.agent_runner")


def _resolve_agent_name(event: Optional[dict]) -> str:
    """Where the agent name comes from, in priority order:

      1. `event["agent_name"]` — caller-supplied (useful for manually
         invoking a Lambda to test a different handler).
      2. `AGENT_NAME` env var — set by the Lambda function config or
         the ECS task definition. This is the normal path.
      3. Filename-derived (if invoked as `python handlers/<name>.py`)
         — only meaningful for local dev.

    Raises if none of the above produces a non-empty string.
    """
    if event and isinstance(event, dict) and event.get("agent_name"):
        return str(event["agent_name"]).strip()
    name = (os.environ.get("AGENT_NAME") or "").strip()
    if name:
        return name
    raise RuntimeError(
        "agent name not set — pass AGENT_NAME env var "
        "or include 'agent_name' in the event payload"
    )


def _load_handler(name: str):
    """Import `handlers.<name>` and return its `handle` callable.

    The agent name is the slug used in `.claude/agents/<name>.md` and
    in EventBridge schedule names — e.g. `aws-cost-sentinel`,
    `price-anomaly-detector`, `scraper-dispatcher`. Python module names
    can't contain `-`, so we translate to `_`.
    """
    module_name = name.replace("-", "_")
    try:
        mod = importlib.import_module(f"handlers.{module_name}")
    except ImportError as exc:
        raise RuntimeError(
            f"no handler module for agent {name!r} "
            f"(expected handlers/{module_name}.py)"
        ) from exc
    handle = getattr(mod, "handle", None)
    if not callable(handle):
        raise RuntimeError(
            f"handlers/{module_name}.py is missing a top-level "
            "`handle(event, context)` function"
        )
    return handle


def lambda_handler(event: Optional[dict] = None, context: Any = None) -> dict:
    """AWS Lambda entrypoint.

    `event` is whatever EventBridge / SNS / SQS / manual `aws lambda
    invoke` passed in. `context` is the AWS Lambda runtime context
    (preserved verbatim and forwarded to handlers for things like
    `context.aws_request_id`).

    Wraps the handler in timing + error-shaping so Lambda's invocation
    record always has a structured payload regardless of success.
    """
    started = time.time()
    name = _resolve_agent_name(event)
    log.info(json.dumps({"agent": name, "event": "start"}))

    try:
        handle = _load_handler(name)
    except Exception as exc:
        log.error(json.dumps({"agent": name, "event": "load_failed", "err": str(exc)}))
        # Re-raise so Lambda surfaces it as a function error + retries.
        raise

    try:
        result = handle(event or {}, context)
    except Exception as exc:  # noqa: BLE001
        elapsed = round(time.time() - started, 3)
        log.error(json.dumps({
            "agent": name,
            "event": "handler_raised",
            "elapsed_s": elapsed,
            "err": f"{type(exc).__name__}: {exc}",
            "stack": traceback.format_exc(),
        }))
        # Re-raise: Lambda records the error, retries per its
        # async-invoke retry policy, and sends to the DLQ on final fail.
        raise

    elapsed = round(time.time() - started, 3)
    if not isinstance(result, dict):
        # Tolerate handlers that return None or scalars — wrap so the
        # log entry is always structured.
        result = {"value": result}
    result.setdefault("ok", True)
    result.setdefault("agent", name)
    result["elapsed_s"] = elapsed
    log.info(json.dumps({"agent": name, "event": "done", **{
        # Keep the log entry small — only emit a few common fields, not
        # the entire result.
        k: result[k] for k in ("ok", "elapsed_s") if k in result
    }}))
    return result


# ── Local / Fargate entrypoint ───────────────────────────────────────
# `python agent_runner.py` runs the handler synchronously. Used inside
# the ECS task definition's `command`, and also handy for dev:
#   AGENT_NAME=aws-cost-sentinel python deploy/agent_runner/agent_runner.py
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    rv = lambda_handler(event={}, context=None)
    print(json.dumps(rv, default=str, indent=2))
