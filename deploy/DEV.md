# CarPapi — local development

Run Django + React on your laptop against the same local Postgres
that has the production data dump. Same-origin via the Vite proxy so
JWT tokens + cookies behave identically to production without CORS
games.

## One-command start

```bash
./scripts/dev-local.sh
```

Brings up:

- **Django** on http://localhost:8000 (`manage.py runserver`)
- **Vite**   on http://localhost:5173 (`npm run dev`, proxies `/api` → `:8000`)

Open http://localhost:5173 — that's the SPA.

`Ctrl-C` stops both processes.

## Prereqs (one-time)

```bash
# 1. Local Postgres on port 5433 with role/db carpapi/carpapi.
#    If you ran any of the deploy scripts, you have this.
brew services start postgresql@17
PGPASSWORD=carpapi psql -h localhost -p 5433 -U carpapi -d carpapi \
  -c "SELECT COUNT(*) FROM public.listings"
# → should print 4391

# 2. Python venv + backend deps
python3 -m venv .venv
.venv/bin/pip install -r web/backend/requirements.txt
.venv/bin/pip install -r requirements.txt

# 3. Frontend deps
cd web/frontend && npm install && cd -

# 4. Optional: an admin user for /admin/
export DJANGO_SUPERUSER_EMAIL=you@dev.local
export DJANGO_SUPERUSER_PASSWORD=devdevdev
export DJANGO_SUPERUSER_FULL_NAME='Dev User'
# The script's `ensure_superuser` step will pick these up on first
# boot. Without these set, the admin has no users; create one with
# `python manage.py createsuperuser`.
```

## What the script sets

| Env | Value | Why |
|---|---|---|
| `DJANGO_DEBUG` | `true` | Skips the JWT gate on `/api/chat/` for ad-hoc testing |
| `DJANGO_SECRET_KEY` | `dev-only-...` | Throwaway; never re-use in prod |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,*` | Permissive for local |
| `CARPAPI_DB_*` | `localhost:5433/carpapi` | Points at the local data dump |
| `DJANGO_EMAIL_BACKEND` | `console.EmailBackend` | Password-reset emails print to stdout |
| `VITE_API_TARGET` | `http://localhost:8000` | Vite proxies `/api` here |

## Verifying it works

In another terminal:

```bash
# Health
curl -fsS http://localhost:8000/api/healthz/
curl -fsS http://localhost:5173/api/healthz/   # proxied to :8000

# Stats
curl -fsS http://localhost:8000/api/stats/ | jq .

# Register a test user via the SPA
open http://localhost:5173/register
# Or curl directly:
curl -X POST http://localhost:8000/api/auth/registration/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"a@dev.local","password1":"longpass123","password2":"longpass123"}'

# Then exercise the chat (DEBUG=true bypasses the JWT gate so this
# works without a Bearer header in dev):
curl -X POST http://localhost:8000/api/chat/ \
  -H 'Content-Type: application/json' \
  -d '{"message":"Toyota Camry under $25k"}'
```

## Auth in dev (and why production differs)

- Local backend runs with `DJANGO_DEBUG=true`. That flag in
  `web/backend/api/views.py::chat` short-circuits the JWT gate so
  you can hit `/api/chat/` without a token while debugging.
- The SPA still sends `Authorization: Bearer <jwt>` if it has one.
  When you sign in via `/login`, real JWT tokens are issued by
  `dj-rest-auth` exactly as they are in production, persisted to
  `localStorage` under `carpapi.auth.v2`. So you can develop the
  auth UI flows end-to-end against the local backend.
- Password reset emails (`/api/auth/password/reset/`) print the
  reset link to the Django stdout instead of sending email. Watch
  the terminal where you ran `./scripts/dev-local.sh`.
- The mockAuth bridge (`web/frontend/src/data/mockAuth.js`) calls
  the real backend now. The Account/Signup/Forgot/Reset pages all
  work against `:8000`. Three features remain local-only because
  the backend doesn't expose them yet: API tokens, preferences,
  and account deletion. See the LOCAL-ONLY section in that file.

## Common dev workflows

### "I want to test the chat against the live RDS"

Don't. Run against `localhost:5433` — the local DB has the same
4,391 listings + embeddings as RDS. If you must hit RDS:

```bash
source data/secrets/rds.env
# now CARPAPI_DB_* env vars point at carpapi-db.c7oasmx9kbh5...
./scripts/dev-local.sh backend
```

This will only work from your home IP (the RDS SG is locked to it).

### "I want to develop the SPA against the live App Runner API"

```bash
cd web/frontend
VITE_API_BASE=https://gt3mapscrz.us-east-1.awsapprunner.com/api \
  npm run dev
```

Note: production has `CARPAPI_API_KEY` empty AND no longer the
shared-passphrase gate; `/api/chat/` requires a real JWT, so you
need to log in via `/login` first to get tokens.

### "I broke migrations; how do I reset?"

```bash
# Drop + recreate the local Postgres data (loses everything)
PGPASSWORD=carpapi psql -h localhost -p 5433 -U carpapi -d postgres \
  -c "DROP DATABASE carpapi;"
PGPASSWORD=carpapi psql -h localhost -p 5433 -U carpapi -d postgres \
  -c "CREATE DATABASE carpapi;"

# Restore from the latest dump
DUMP=$(ls -dt data/dumps/*/ | head -1)
PGPASSWORD=carpapi psql -h localhost -p 5433 -U carpapi -d carpapi \
  -c "CREATE EXTENSION vector;"
for f in "$DUMP"/data_*.sql; do
  PGPASSWORD=carpapi psql -h localhost -p 5433 -U carpapi -d carpapi -f "$f"
done

# Run Django migrations again
./scripts/dev-local.sh backend
```

### "How do I clear my SPA login state in dev?"

```js
// In the browser console at http://localhost:5173
localStorage.removeItem("carpapi.auth.v2");
localStorage.removeItem("carpapi.auth.prefs.v1");
localStorage.removeItem("carpapi.auth.apiTokens.v1");
location.reload();
```

## Hot-reload + debugging

- **Vite**: edits to `web/frontend/src/**` reload instantly via HMR.
- **Django**: edits to `web/backend/**` reload via the autoreloader
  baked into `runserver`. Watch for "Performing system checks…" in
  the backend terminal.
- **Postgres**: every change you write via Django persists; restart
  the dev script to pick up env-var changes.

## When to leave local + use the cloud

| Symptom | Where to go |
|---|---|
| Bedrock-specific bug (cache, planner, synth) | Local — same Titan v2 / Haiku 4.5 / Sonnet 4.5 via AWS Bedrock from your laptop |
| Real-traffic latency profiling | Live App Runner — local doesn't reproduce VPC-endpoint cost |
| Cross-origin / CORS issue | Live (CloudFront → App Runner). Same-origin in dev hides those |
| Auth flow (registration, login, reset, Google OAuth) | Local first; deploy to verify production-only paths (HttpOnly cookies, custom domain) |
| Migration testing | Local. Always. Never test a destructive migration on RDS first. |
