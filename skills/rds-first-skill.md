# Skill: RDS-first — always write to production from agents

## When to use this

Any time an operational agent (`.claude/agents/*.md`) or a developer
runs a pipeline script locally that:

- inserts or updates rows in `public.listings`, `public.dealers`,
  `public.maker_specs`, `public.listing_price_history`,
  `public.listing_groups`, `public.makes`, `public.maker_models`,
  `public.sources`, or
- reads from those tables for analysis the team will act on.

In short: **production state lives in RDS, not on your laptop.**
The local Postgres on `:5433` is a snapshot for one-off local
experiments + the UI dev stack — it goes stale the moment any agent
writes to RDS. If you need the real numbers, point at RDS.

## What this skill enforces

Before running any agent or pipeline tool from your laptop, source
the RDS connection file:

```bash
source data/secrets/rds.env
```

That sets these env vars in your shell:

```
CARPAPI_DB_HOST=carpapi-db.c7oasmx9kbh5.us-east-1.rds.amazonaws.com
CARPAPI_DB_PORT=5432
CARPAPI_DB_NAME=carpapi
CARPAPI_DB_USER=carpapi
CARPAPI_DB_PASSWORD=<32-char master pw>
AWS_REGION=us-east-1
```

The pipeline (`pipeline/carapi_pipeline/*`), the RAG package
(`carpapi/rag/*`), the scrapers (`carpapi/scrapers/*`), the enrichment
loop (`carpapi/enrich/*`), and every monitor (`carpapi/monitor/*`)
all read these env vars at runtime. They have no hard-coded DSN.

Once sourced, any command that opens a `psycopg.connect()` connects
to RDS automatically:

```bash
source data/secrets/rds.env

# Scrape one dealer + ingest to RDS
python -m carpapi.scrapers.run --dealer-slug performance-ford

# Enrich a VIN against the maker site, write back to RDS
python -m carpapi.enrich.cli enrich-vin --vin 1FMCU9G6XLU... --make Ford

# Re-embed listings (Titan v2 via Bedrock; rows updated on RDS)
python -m carpapi.rag.embed --limit 200

# Run the RAG smoke suite against RDS data
python tools/smoke_rag_accuracy.py
```

## Why RDS, not local

| Concern | Local PG :5433 | RDS production |
|---|---|---|
| Source of truth for scrape state | ❌ goes stale on every prod write | ✅ canonical |
| Visible to the App Runner API | ❌ unreachable | ✅ — same row the API serves |
| Daily report numbers | ❌ wrong | ✅ correct |
| Cost of a wrong write | $0 (local) | recoverable but visible |
| Speed | faster (no network) | slower (~50ms RTT) |

The cost asymmetry matters: a developer who writes to local Postgres
thinking they're updating prod gets silently no-op'd. A developer
who writes to RDS sees the change land everywhere immediately. **The
default should be the visible, canonical one.**

## The lone exception — `scripts/dev-local.sh`

When you're iterating on the **SPA or Django UI** (not the data
pipeline), use the local stack:

```bash
./scripts/dev-local.sh
# Vite on :5173, Django on :8000, points at localhost:5433
```

That keeps your work isolated from production while you're tweaking
React components or auth flows. See `deploy/DEV.md` for the full
local-dev workflow. **As soon as you flip to an agent or pipeline
script, source `rds.env`.**

## Safety contract — what NOT to point at RDS

Even when sourced for RDS, do NOT run from local:

- `manage.py migrate` against RDS — migrations apply automatically
  on every App Runner container boot via the Dockerfile CMD. Running
  it locally races the auto-apply and can leave the migration
  table inconsistent if the app rolls back. Use the deploy pipeline.
- `manage.py createsuperuser` / `loaddata` / `flush` against RDS —
  user accounts on RDS are real. Use the Django admin UI.
- Bulk `DELETE FROM public.listings` / `TRUNCATE` — irreversible
  without a backup, and we don't enable backup retention by default.
  If you need to test a destructive query, dump locally first
  (`./deploy/migrate_to_rds.sh` reverse) and run it there.
- Loading personal info or PII not already in the schema — RDS isn't
  encrypted-at-rest by default and the snapshot the team might share
  for debugging carries everything.

## How agents enforce this

Every `.claude/agents/*.md` that touches data references this skill
and includes the source-`rds.env` step in its operating procedure.
If you're writing a new agent, copy the pattern:

```markdown
## Preflight (always run before any DB read or write)

```bash
source data/secrets/rds.env   # writes go to RDS
```

See `skills/rds-first-skill.md` for the rationale.
```

## How to know which database you're hitting

Quick check from any shell:

```bash
echo "PG: $CARPAPI_DB_HOST:$CARPAPI_DB_PORT/$CARPAPI_DB_NAME (user $CARPAPI_DB_USER)"
```

- `carpapi-db.c7oasmx9kbh5...:5432` → RDS production
- `localhost:5433` or `127.0.0.1:5433` → local dev stack
- unset → defaults to `localhost:5432` (probably wrong; source `rds.env`)

If you're using a graphical tool (DBeaver / TablePlus), pin two
connection profiles — one for RDS, one for local — and **never
rename them**. Many incidents start with someone clicking the
wrong profile.

## Rotation

The RDS master password rotates per `deploy/PRODUCTION.md §4.1`. When
it rotates:

1. AWS `modify-db-instance --master-user-password ...` sets the
   new value.
2. `data/secrets/rds_master_password.txt` and `rds.env` get
   regenerated.
3. App Runner env var `CARPAPI_DB_PASSWORD` is updated (causes a
   service redeploy).
4. Anyone who has `rds.env` sourced in an open shell loses
   connectivity until they re-source.
