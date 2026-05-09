# carapi-api

Install **`carapi-pipeline`** in the same virtualenv first (shared SQLAlchemy models):

```bash
cd /Users/ahu/Documents/CarPapi/pipeline
python -m venv .venv && source .venv/bin/activate
pip install -e .
cd ../services/api
pip install -e .
```

Run:

```bash
export DATABASE_URL=postgresql+psycopg://carapi:carapi@127.0.0.1:5432/carapi
uvicorn carapi_api.main:app --reload --port 8000
```
