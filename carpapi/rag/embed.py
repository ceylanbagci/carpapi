from __future__ import annotations

"""Listing-embedding pipeline.

For each listing without an embedding, build a compact "embedding text"
from the structured fields (title, make/model/year/trim, mileage, body
style, price, region/city, maker_specs.description) and call Titan
Embed Text v2. Store the 1024-dim vector in ``listings.embedding``.

Idempotent: skips listings that already have an embedding. Re-run after
adding new listings or after a schema change to ``embedding`` dimension.

CLI: ``python -m carpapi.rag.embed [--limit N] [--make M] [--reembed]``
"""

import argparse
import logging
import os
import sys
import time
from typing import Any, Optional

import psycopg

from carpapi.cache.bedrock_client import bedrock_embed, EMBED_DIMENSIONS

log = logging.getLogger("carpapi.rag.embed")


def _dsn() -> str:
    return (
        f"host={os.environ.get('CARPAPI_DB_HOST', 'localhost')} "
        f"port={os.environ.get('CARPAPI_DB_PORT', '5433')} "
        f"dbname={os.environ.get('CARPAPI_DB_NAME', 'carpapi')} "
        f"user={os.environ.get('CARPAPI_DB_USER', 'carpapi')} "
        f"password={os.environ.get('CARPAPI_DB_PASSWORD', 'carpapi')}"
    )


def embedding_text(row: dict[str, Any]) -> str:
    """Render a listing as a short, factual paragraph for embedding.

    Order matters less than density — Titan v2 produces one vector for
    the whole text, so we pack the highest-signal fields first.
    """
    parts: list[str] = []
    title = row.get("title") or ""
    if title:
        parts.append(title)

    descriptor_bits: list[str] = []
    if row.get("year"):
        descriptor_bits.append(str(row["year"]))
    if row.get("make"):
        descriptor_bits.append(str(row["make"]))
    if row.get("model"):
        descriptor_bits.append(str(row["model"]))
    if row.get("trim"):
        descriptor_bits.append(str(row["trim"]))
    if descriptor_bits:
        parts.append(" ".join(descriptor_bits))

    if row.get("body_style"):
        parts.append(f"Body: {row['body_style']}")
    if row.get("mileage") is not None:
        try:
            miles = int(float(row["mileage"]))
            parts.append(f"Mileage: {miles:,} mi")
        except Exception:  # noqa: BLE001
            pass
    if row.get("price_amount") is not None:
        try:
            price = int(float(row["price_amount"]))
            parts.append(f"Price: ${price:,}")
        except Exception:  # noqa: BLE001
            pass
    if row.get("region") or row.get("city"):
        loc = " ".join(p for p in (row.get("city"), row.get("region")) if p)
        if loc:
            parts.append(f"Location: {loc}")
    if row.get("seller_type"):
        parts.append(f"Seller type: {row['seller_type']}")

    description = (row.get("description") or "").strip()
    if description:
        # Truncate dealer-prose to keep tokens tight.
        parts.append(description[:600])

    maker_specs = row.get("maker_specs") or {}
    if isinstance(maker_specs, dict):
        mdesc = maker_specs.get("description")
        if isinstance(mdesc, str) and mdesc:
            parts.append(f"Manufacturer description: {mdesc[:500]}")

    features = row.get("features") or []
    if isinstance(features, list) and features:
        parts.append("Features: " + ", ".join(str(f) for f in features[:15]))

    return "\n".join(parts)


def _to_vector_literal(values: list[float]) -> str:
    """pgvector accepts the literal '[1,2,3]' on the wire."""
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def _select_pending(
    cur: psycopg.Cursor,
    *,
    make: Optional[str],
    limit: int,
    reembed: bool,
) -> list[dict[str, Any]]:
    where = ["1=1"]
    params: list[Any] = []
    if not reembed:
        where.append("embedding IS NULL")
    if make:
        where.append("make = %s")
        params.append(make)
    sql = f"""
        SELECT id, vin, title, make, model, year, trim, body_style,
               mileage, price_amount, region, city, seller_type,
               description, features, maker_specs
        FROM public.listings
        WHERE {' AND '.join(where)}
        ORDER BY id
        LIMIT %s
    """
    params.append(limit)
    cur.execute(sql, params)
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def embed_batch(
    *,
    make: Optional[str] = None,
    limit: int = 5000,
    reembed: bool = False,
) -> dict[str, int]:
    """Embed up to ``limit`` listings. Returns counters."""
    counts = {"considered": 0, "embedded": 0, "skipped": 0, "errors": 0}
    started = time.time()

    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            pending = _select_pending(cur, make=make, limit=limit, reembed=reembed)
        counts["considered"] = len(pending)
        log.info("embedding %d listings (make=%s, reembed=%s)",
                 len(pending), make or "all", reembed)

        for i, row in enumerate(pending, 1):
            text = embedding_text(row)
            if not text.strip():
                counts["skipped"] += 1
                continue
            try:
                vec = bedrock_embed(text)
            except Exception as exc:  # noqa: BLE001
                counts["errors"] += 1
                log.warning("embed failed for id=%s vin=%s: %s", row["id"], row.get("vin"), exc)
                continue
            if len(vec) != EMBED_DIMENSIONS:
                counts["errors"] += 1
                continue
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE public.listings SET embedding = %s::vector "
                    "WHERE id = %s",
                    (_to_vector_literal(vec), row["id"]),
                )
            conn.commit()
            counts["embedded"] += 1
            if i % 25 == 0:
                elapsed = time.time() - started
                rate = i / elapsed if elapsed else 0
                eta = (len(pending) - i) / rate if rate else 0
                log.info(
                    "  [%d/%d] embedded=%d errors=%d (%.1f/sec, eta %.0fs)",
                    i, len(pending), counts["embedded"], counts["errors"], rate, eta,
                )

    elapsed = time.time() - started
    log.info(
        "done in %.0fs: embedded=%d skipped=%d errors=%d",
        elapsed, counts["embedded"], counts["skipped"], counts["errors"],
    )
    return counts


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="carpapi.rag.embed")
    p.add_argument("--limit", type=int, default=5000)
    p.add_argument("--make", default=None)
    p.add_argument("--reembed", action="store_true",
                   help="ignore existing embeddings; re-embed every match")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    counts = embed_batch(make=args.make, limit=args.limit, reembed=args.reembed)
    return 0 if counts["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
