from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from carapi_pipeline.models import init_schema
from carapi_pipeline.normalize import load_fixture
from carapi_pipeline.pipeline import run_ingest_batch
from carapi_pipeline.settings import load_settings


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="CarPapi ingestion pipeline runner")
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Documented flag for README compatibility (MVP always loads bundled fixtures).",
    )
    parser.add_argument(
        "--source-id",
        default="demo_batch",
        help="Logical batch source identifier for raw storage paths",
    )
    args = parser.parse_args(argv)
    _ = args.sample  # reserved for future live crawl vs fixtures switch

    try:
        settings = load_settings()
    except RuntimeError as exc:
        logging.error("%s", exc)
        return 2

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    init_schema(engine)

    docs = load_fixture()

    with Session(engine) as session:
        counts = run_ingest_batch(session, settings, docs, source_id=args.source_id)
        session.commit()

    logging.info("Done: %s", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
