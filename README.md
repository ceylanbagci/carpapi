# CarPapi

ChatGPT-like car search: natural language → validated structured queries → ranked listings with citations.

## Prerequisites

- **Python 3.10+** (3.11 recommended). The ingestion package and API use modern typing syntax.
- **Docker** (optional but recommended) for Postgres with pgvector: `docker compose up -d` from this directory.

## Quick start (local)

1. **Infrastructure**

   ```bash
   cd /Users/ahu/Documents/CarPapi
   docker compose up -d
   ```

2. **Pipeline** (normalize sample JSON and upsert into Postgres)

   ```bash
   cd pipeline
   python -m venv .venv && source .venv/bin/activate
   pip install -e .
   export DATABASE_URL=postgresql+psycopg://carapi:carapi@localhost:5432/carapi
   carapi-run-pipeline
   ```

3. **API**

   ```bash
   cd services/api
   python -m venv .venv && source .venv/bin/activate
   pip install -e ../../pipeline
   pip install -e .
   export DATABASE_URL=postgresql+psycopg://carapi:carapi@localhost:5432/carapi
   uvicorn carapi_api.main:app --reload --port 8000
   ```

4. **Web UI**

   Open `web/index.html` in a browser, or serve statically:

   ```bash
   cd web && python -m http.server 3000
   ```

   Configure `API_BASE` in `web/app.js` if not using `http://localhost:8000`.

## Documentation

- [architecture.md](architecture.md) — full system design  
- [STACK_DECISION.md](STACK_DECISION.md) — database / vector choice  
- [schema/](schema/) — canonical listing schema  
- [runbooks/](runbooks/) — operations  

## Paths

Typical dev root: `~/Documents/CarPapi`. Sandboxed/notebook environments may use `/mnt/data/Documents/CarPapi`.
