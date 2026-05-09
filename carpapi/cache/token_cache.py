from __future__ import annotations

"""TokenCache — the single entry point for all Claude/LLM calls in CarPapi.

Hard rule (context/ai-cache-rules.md):
    Component → TokenCache → Claude
    No component is permitted to call Claude directly.

Pipeline inside TokenCache.query():
    1. PII guard         (refuse VINs, addresses, phones, emails)
    2. Optional compress (LLMLingua + HTML strip)
    3. Hash → cache key  (sha256 over compressed prompt + model + max_tokens)
    4. Backend lookup    (SQLite default, Redis optional)
    5. Hit → return      (no LLM call, no cost)
    6. Miss → llm_call() → store with TTL → return

The actual LLM client (Bedrock / Anthropic SDK) is injected via the
`llm_call` parameter so this module has zero AI-vendor lock-in.
"""

import hashlib
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol, runtime_checkable

from carpapi.cache.pii_guard import PIIInPromptError, assert_safe

log = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h per guideline 2
DEFAULT_DB_PATH = "./data/token_cache.sqlite"

# Conservative max_tokens defaults from guideline 3.
MAX_TOKENS_BY_TASK: dict[str, int] = {
    "classify": 256,
    "extract": 512,
    "synthesize": 1024,
}


# --------------------------------------------------------------------------- #
# Backends
# --------------------------------------------------------------------------- #


@runtime_checkable
class CacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...
    def stats(self) -> dict[str, int]: ...


class SQLiteBackend:
    """Local-development backend. Single-file, TTL-aware, thread-safe."""

    def __init__(self, path: str = DEFAULT_DB_PATH) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at REAL NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_cache_expires_at ON cache (expires_at)"
        )
        self._conn.commit()

    def get(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            value, expires_at = row
            if time.time() > float(expires_at):
                self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                self._conn.commit()
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at, created_at) "
                "VALUES (?, ?, ?, ?)",
                (key, value, now + ttl_seconds, now),
            )
            self._conn.commit()

    def stats(self) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()
            return {"entries": int(row[0]) if row else 0}

    def purge_expired(self) -> int:
        """Delete expired entries. Returns deleted count."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM cache WHERE expires_at < ?", (time.time(),)
            )
            self._conn.commit()
            return cur.rowcount or 0


class RedisBackend:
    """Production backend. Lazy-imports `redis`."""

    def __init__(self, url: str) -> None:
        import redis  # noqa: PLC0415 — lazy on purpose

        self._client = redis.Redis.from_url(url, decode_responses=True)
        # Fail fast on unreachable Redis at construction.
        self._client.ping()

    def get(self, key: str) -> str | None:
        v = self._client.get(key)
        return v if v is not None else None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.setex(key, ttl_seconds, value)

    def stats(self) -> dict[str, int]:
        info = self._client.info("stats") or {}
        return {
            "keyspace_hits": int(info.get("keyspace_hits", 0)),
            "keyspace_misses": int(info.get("keyspace_misses", 0)),
        }


# --------------------------------------------------------------------------- #
# TokenCache
# --------------------------------------------------------------------------- #


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    pii_rejected: int = 0
    bypass_errors: int = 0  # raised when llm_call is None on a miss
    by_skill: dict[str, dict[str, int]] = field(default_factory=dict)

    def _bump(self, skill: str | None, kind: str) -> None:
        if skill is None:
            return
        bucket = self.by_skill.setdefault(skill, {"hits": 0, "misses": 0})
        bucket[kind] = bucket.get(kind, 0) + 1


# Type alias is a runtime expression, so PEP-604 unions (int | None) don't
# work on Python 3.9. Use typing.Optional for portability.
LLMCall = Callable[[str, Optional[int], Optional[str]], str]
"""Signature of the injected LLM client: (prompt, max_tokens, model) -> response."""


class TokenCache:
    """The single entry point for all Claude/LLM calls in the project.

    Construction:
        cache = TokenCache(
            backend=SQLiteBackend("./data/token_cache.sqlite"),
            compressor=make_compressor(rate=0.5),  # optional
            llm_call=my_bedrock_caller,            # required for actual LLM hits
        )

    Use:
        response = cache.query(
            prompt="Classify this dealer type: ...",
            ttl=86400,
            skill="classify-dealer",
            max_tokens=256,
        )
    """

    def __init__(
        self,
        *,
        backend: CacheBackend | None = None,
        compressor: Callable[[str], str] | None = None,
        llm_call: LLMCall | None = None,
        default_ttl: int = DEFAULT_TTL_SECONDS,
        pii_guard: Callable[[str], None] | None = None,
    ) -> None:
        self.backend = backend or SQLiteBackend()
        self.compressor = compressor
        self.llm_call = llm_call
        self.default_ttl = default_ttl
        self._pii_guard = pii_guard or assert_safe
        self.stats = CacheStats()

    def query(
        self,
        prompt: str,
        *,
        ttl: int | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        skill: str | None = None,
    ) -> str:
        """Return cached response or call the LLM and cache the result.

        Raises:
          PIIInPromptError: prompt contains PII (VIN/phone/email/address).
          RuntimeError: cache miss but no llm_call configured.
        """
        # 1. PII guard. Runs BEFORE compression so even raw inputs are checked.
        try:
            self._pii_guard(prompt)
        except PIIInPromptError:
            self.stats.pii_rejected += 1
            raise

        # 2. Optional compression. Keep the original around only for debugging.
        compressed = self.compressor(prompt) if self.compressor else prompt

        # 3. Cache key over (compressed_prompt, model, max_tokens). Skill is
        #    intentionally NOT in the key — same prompt under different skill
        #    names should hit the same cache entry.
        key = self._make_key(compressed, model=model, max_tokens=max_tokens)

        # 4. Lookup.
        hit = self.backend.get(key)
        if hit is not None:
            self.stats.hits += 1
            self.stats._bump(skill, "hits")
            log.debug("cache hit skill=%s key=%s", skill, key[:12])
            return hit

        # 5. Miss → real LLM call.
        if self.llm_call is None:
            self.stats.bypass_errors += 1
            raise RuntimeError(
                "TokenCache miss but no llm_call configured. "
                "Wire a Claude/Bedrock callable: "
                "TokenCache(llm_call=my_caller). "
                "Per context/ai-cache-rules.md, no component may bypass this layer."
            )

        self.stats.misses += 1
        self.stats._bump(skill, "misses")
        log.debug("cache miss skill=%s key=%s — calling LLM", skill, key[:12])
        response = self.llm_call(compressed, max_tokens, model)

        # 6. Store with TTL.
        self.backend.set(key, response, ttl or self.default_ttl)
        return response

    def hit_rate(self) -> float:
        total = self.stats.hits + self.stats.misses
        return 0.0 if total == 0 else self.stats.hits / total

    @staticmethod
    def _make_key(
        compressed_prompt: str, *, model: str | None, max_tokens: int | None
    ) -> str:
        material = json.dumps(
            {"p": compressed_prompt, "m": model, "t": max_tokens},
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()
