from __future__ import annotations

"""Bedrock-backed LLM and embedding clients.

This is the ONLY place in the project that opens a boto3 ``bedrock-runtime``
client. Everywhere else goes through ``carpapi.cache.token_cache.TokenCache``
per the rule in ``context/ai-cache-rules.md``.

Exposes two factory functions:

  - ``bedrock_chat(model_alias)`` -> ``LLMCall`` suitable as
    ``TokenCache(llm_call=...)``. The alias resolves to a Bedrock model id;
    today we ship Claude Sonnet 4.5 (synthesis) and Claude Haiku 4.5
    (cheap parsing).

  - ``bedrock_embed(text)`` -> ``list[float]``. Single-call helper around
    Titan Embed Text v2 (1024 dimensions). The TokenCache contract is for
    text-in / text-out, so embeddings have their own thin wrapper rather
    than living behind it.

Costs at the time of writing (USD per million tokens, on-demand):

  - claude-sonnet-4-5  input $3 / output $15
  - claude-haiku-4-5   input $1 / output $5
  - titan-embed-text-v2 $0.02 per 1,000 input tokens

The cache layer absorbs the cost of repeat prompts; the chat closure is
careful to count and surface input/output tokens so the AICall audit log
in ``ai.ai_calls`` can track real spend.
"""

import json
import logging
import os
from typing import Any, Optional

log = logging.getLogger(__name__)

# Model id aliases. Bedrock model ids are long and change with new releases;
# keep one place in the code that maps friendly names to current ids.
#
# The newer Anthropic models on Bedrock require *inference-profile* IDs
# (prefixed `us.`) — invoking the bare modelId throws ValidationException.
# We resolve aliases to those profile IDs directly.
MODEL_ALIASES: dict[str, str] = {
    "sonnet":         "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "sonnet-4.5":     "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "haiku":          "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "haiku-4.5":      "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    # If unset, the chat closure defaults to haiku for the parsing path;
    # synthesis callers explicitly pass model="sonnet".
}

# Titan v2 supports 256/512/1024 dimensions. 1024 is the default and is
# what we size the listings.embedding column to.
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBED_DIMENSIONS = 1024


def _client():
    """Lazy boto3 bedrock-runtime client. Region from CARPAPI_BEDROCK_REGION
    or AWS_REGION, defaulting to us-east-1 (where every model we use is GA)."""
    import boto3  # noqa: PLC0415

    region = (
        os.environ.get("CARPAPI_BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or "us-east-1"
    )
    return boto3.client("bedrock-runtime", region_name=region)


def _resolve_model(alias: Optional[str], default: str = "haiku") -> str:
    name = (alias or default).lower()
    if name in MODEL_ALIASES:
        return MODEL_ALIASES[name]
    # Pass-through: caller may pass a full Bedrock model id.
    return name


# --------------------------------------------------------------------------- #
# Chat — Anthropic Claude on Bedrock (messages API)
# --------------------------------------------------------------------------- #


def bedrock_chat(
    *,
    default_model: str = "haiku",
    default_max_tokens: int = 512,
    system: Optional[str] = None,
    on_call: Optional[Any] = None,
):
    """Return an LLMCall closure for ``TokenCache(llm_call=...)``.

    Signature matches ``carpapi.cache.token_cache.LLMCall``:
      ``(prompt: str, max_tokens: int | None, model: str | None) -> str``

    Args:
      default_model: alias used when the caller doesn't pass ``model``.
      default_max_tokens: ditto for max_tokens.
      system: optional system prompt prepended to every call. Pass
        ``None`` to omit. (TokenCache callers can also bake the system
        prompt into the user prompt; either works.)
      on_call: optional callback receiving ``(skill, model, input_tokens,
        output_tokens, latency_ms, error)`` so the caller can route to
        ``AICacheRepo.log_call``.
    """
    client = _client()

    def call(prompt: str, max_tokens: Optional[int], model: Optional[str]) -> str:
        import time  # noqa: PLC0415

        model_id = _resolve_model(model, default=default_model)
        mt = int(max_tokens or default_max_tokens)

        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": mt,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        started = time.time()
        err: Optional[str] = None
        in_tokens = out_tokens = None
        try:
            resp = client.invoke_model(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body).encode("utf-8"),
            )
            payload = json.loads(resp["body"].read())
            content = payload.get("content") or []
            # Anthropic on Bedrock returns content as a list of blocks
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            usage = payload.get("usage") or {}
            in_tokens = usage.get("input_tokens")
            out_tokens = usage.get("output_tokens")
            return text
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            log.exception("Bedrock chat failed: %s", err)
            raise
        finally:
            latency_ms = int((time.time() - started) * 1000)
            if on_call is not None:
                try:
                    on_call(
                        model=model_id,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        latency_ms=latency_ms,
                        error=err,
                    )
                except Exception:  # noqa: BLE001
                    pass  # never let the audit hook break the LLM path

    return call


# --------------------------------------------------------------------------- #
# Embeddings — Titan Embed Text v2 (1024-dim by default)
# --------------------------------------------------------------------------- #


def bedrock_embed(
    text: str,
    *,
    dimensions: int = EMBED_DIMENSIONS,
    normalize: bool = True,
) -> list[float]:
    """Return a Titan v2 embedding for the input text.

    Truncates long inputs to roughly Titan's context (~8192 tokens / 32K
    chars conservatively) — callers should pre-build a compact embedding
    text rather than dumping raw HTML.
    """
    if not text:
        # Embedding empty input is a programmer error — surface it loudly.
        raise ValueError("bedrock_embed: empty text")

    body = {
        "inputText": text[:30_000],
        "dimensions": dimensions,
        "normalize": bool(normalize),
    }
    resp = _client().invoke_model(
        modelId=EMBED_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body).encode("utf-8"),
    )
    payload = json.loads(resp["body"].read())
    emb = payload.get("embedding")
    if not isinstance(emb, list) or len(emb) != dimensions:
        raise RuntimeError(
            f"Titan returned unexpected embedding shape (len={len(emb) if isinstance(emb, list) else 'n/a'})"
        )
    return emb
