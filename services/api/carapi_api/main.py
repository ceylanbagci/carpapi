from __future__ import annotations

import json
from typing import Any, Iterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from carapi_api.orchestrator import plan_car_query, relax_query
from carapi_api.query_exec import run_car_query
from carapi_pipeline.models import Listing
from carapi_pipeline.settings import load_settings


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


_settings = None
_engine = None
_SessionLocal: sessionmaker | None = None


def _get_settings():
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def _ensure_engine() -> None:
    global _engine, _SessionLocal
    if _engine is None:
        cfg = _get_settings()
        _engine = create_engine(cfg.database_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def get_session() -> Iterator[Session]:
    _ensure_engine()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def listing_payload(row: Listing) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "title": row.title,
        "listing_url": row.listing_url,
        "make": row.make,
        "model": row.model,
        "year": row.year,
        "price_amount": row.price_amount,
        "currency": row.currency,
        "mileage": row.mileage,
        "region": row.region,
        "city": row.city,
        "vin": row.vin,
        "dedupe_key": row.dedupe_key,
    }


def sse_pack(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


app = FastAPI(title="CarPapi API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


def _run_with_relaxation(
    session: Session, car_query: dict[str, Any]
) -> tuple[list[Listing], dict[str, Any] | None]:
    """Run the query; if zero results, attempt ONE relaxation step.

    Returns (rows, relaxation_info). relaxation_info is None when no
    relaxation was applied, else a dict with the explanation and the
    relaxed CarQuery actually used.
    """
    rows = run_car_query(session, car_query)
    if rows:
        return rows, None
    relaxed = relax_query(car_query)
    if relaxed is None:
        return rows, None
    relaxed_query, explanation = relaxed
    rows = run_car_query(session, relaxed_query)
    return rows, {"explanation": explanation, "car_query": relaxed_query}


@app.post("/v1/chat/stream")
def chat_stream(req: ChatRequest, session: Session = Depends(get_session)) -> StreamingResponse:
    car_query, rationale = plan_car_query(req.message)

    def event_stream() -> Iterator[str]:
        yield sse_pack({"type": "plan", "car_query": car_query, "rationale": rationale})
        original_rows = run_car_query(session, car_query)
        yield sse_pack({"type": "result_count", "count": len(original_rows)})

        rows = original_rows
        if not rows:
            relaxed = relax_query(car_query)
            if relaxed is not None:
                relaxed_query, explanation = relaxed
                yield sse_pack(
                    {
                        "type": "relaxation",
                        "explanation": explanation,
                        "car_query": relaxed_query,
                    }
                )
                rows = run_car_query(session, relaxed_query)
                yield sse_pack(
                    {"type": "result_count", "count": len(rows), "after_relaxation": True}
                )

        for row in rows:
            yield sse_pack({"type": "listing", "listing": listing_payload(row)})
        yield sse_pack({"type": "done"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/v1/query")
def structured_query(req: ChatRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    car_query, rationale = plan_car_query(req.message)
    rows, relaxation = _run_with_relaxation(session, car_query)
    return {
        "car_query": car_query,
        "rationale": rationale,
        "listings": [listing_payload(r) for r in rows],
        "relaxation": relaxation,
    }


@app.post("/v1/chat/stream-openai")
def chat_stream_openai_compat(req: ChatRequest, session: Session = Depends(get_session)) -> StreamingResponse:
    """Thin compatibility shim: streams newline-delimited JSON chunks."""
    car_query, rationale = plan_car_query(req.message)

    def ndjson_stream() -> Iterator[str]:
        yield json.dumps({"object": "plan", "car_query": car_query, "rationale": rationale}) + "\n"
        original_rows = run_car_query(session, car_query)
        yield json.dumps({"object": "result_count", "count": len(original_rows)}) + "\n"

        rows = original_rows
        if not rows:
            relaxed = relax_query(car_query)
            if relaxed is not None:
                relaxed_query, explanation = relaxed
                yield json.dumps(
                    {
                        "object": "relaxation",
                        "explanation": explanation,
                        "car_query": relaxed_query,
                    }
                ) + "\n"
                rows = run_car_query(session, relaxed_query)
                yield json.dumps(
                    {"object": "result_count", "count": len(rows), "after_relaxation": True}
                ) + "\n"

        for row in rows:
            yield json.dumps({"object": "listing", "listing": listing_payload(row)}) + "\n"
        yield json.dumps({"object": "done"}) + "\n"

    return StreamingResponse(ndjson_stream(), media_type="application/x-ndjson")


def create_app() -> FastAPI:
    return app
