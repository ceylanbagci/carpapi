#!/usr/bin/env bash
#
# CarPapi — migrate local Postgres (port 5433) → RDS.
#
# Approach: pg_dump --schema-only first to set up DDL + vector ext, then
# pg_dump --data-only of the working tables. We do NOT dump the local
# embedding column verbatim because pgvector serializes as text and the
# dimension stamp may differ on the destination side — instead, the
# Listing.embedding column is recreated empty on RDS and re-populated
# by `python -m carpapi.rag.embed` against the cloud DB.
#
# Tables migrated (data):
#   public.dealers
#   public.listings              (embedding column re-NULL'd; rebuild after)
#   public.listing_price_history
#   public.makes
#   public.maker_models
#   public.maker_specs           (if present)
#
# Prereqs:
#   - source ./data/secrets/rds.env
#   - local postgres listening on $LOCAL_PG_HOST:$LOCAL_PG_PORT
#   - pg_dump / psql / pg_restore on PATH (Postgres 16 client)
#
# Re-run safe: pg_restore uses --clean --if-exists so re-runs replace
# the destination data.

set -euo pipefail

: "${LOCAL_PG_HOST:=localhost}"
: "${LOCAL_PG_PORT:=5433}"
: "${LOCAL_PG_DB:=carpapi}"
: "${LOCAL_PG_USER:=carpapi}"
: "${LOCAL_PG_PASSWORD:=carpapi}"

# RDS connection (must already be exported via data/secrets/rds.env)
: "${CARPAPI_DB_HOST:?source data/secrets/rds.env first}"
: "${CARPAPI_DB_PORT:?}"
: "${CARPAPI_DB_NAME:?}"
: "${CARPAPI_DB_USER:?}"
: "${CARPAPI_DB_PASSWORD:?}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DUMP_DIR="${DUMP_DIR:-data/dumps/$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$DUMP_DIR"

log() { printf '\033[1;36m[migrate]\033[0m %s\n' "$*"; }

# --------------------------------------------------------------------- #
# 1. Schema (no data, no ownership, no privileges)
# --------------------------------------------------------------------- #
log "Dumping schema from local ($LOCAL_PG_HOST:$LOCAL_PG_PORT) ..."
PGPASSWORD="$LOCAL_PG_PASSWORD" pg_dump \
  -h "$LOCAL_PG_HOST" -p "$LOCAL_PG_PORT" \
  -U "$LOCAL_PG_USER" -d "$LOCAL_PG_DB" \
  --schema=public --schema-only --no-owner --no-acl \
  -f "$DUMP_DIR/schema.sql"
log "  → $DUMP_DIR/schema.sql ($(wc -l < "$DUMP_DIR/schema.sql") lines)"

# --------------------------------------------------------------------- #
# 2. Data — table-by-table so a single bad row doesn't abort everything
# --------------------------------------------------------------------- #
# Build TABLES list dynamically from the live local schema so we don't
# have to chase drift between this script and the actual public.*
# layout. Order matters for FK-honoring restores — dealers/makes/sources
# first, then groups/listings, then dependent rows.
ORDERED_PREFERENCE=(
  public.sources
  public.dealers
  public.makes
  public.maker_models
  public.maker_specs
  public.listing_groups
  public.listings
  public.listing_price_history
)
EXISTING=$(PGPASSWORD="$LOCAL_PG_PASSWORD" psql -At \
  -h "$LOCAL_PG_HOST" -p "$LOCAL_PG_PORT" \
  -U "$LOCAL_PG_USER" -d "$LOCAL_PG_DB" \
  -c "SELECT 'public.' || tablename FROM pg_tables WHERE schemaname='public'")
TABLES=()
for t in "${ORDERED_PREFERENCE[@]}"; do
  if grep -qFx "$t" <<<"$EXISTING"; then
    TABLES+=("$t")
  fi
done
log "Migrating tables: ${TABLES[*]}"

for tbl in "${TABLES[@]}"; do
  log "Dumping $tbl ..."
  PGPASSWORD="$LOCAL_PG_PASSWORD" pg_dump \
    -h "$LOCAL_PG_HOST" -p "$LOCAL_PG_PORT" \
    -U "$LOCAL_PG_USER" -d "$LOCAL_PG_DB" \
    --data-only --no-owner --no-acl \
    -t "$tbl" \
    -f "$DUMP_DIR/data_${tbl#public.}.sql"
done

# --------------------------------------------------------------------- #
# 3. Restore schema → RDS, then data
# --------------------------------------------------------------------- #
RDS_FLAGS=(-h "$CARPAPI_DB_HOST" -p "$CARPAPI_DB_PORT" \
           -U "$CARPAPI_DB_USER" -d "$CARPAPI_DB_NAME")

log "Ensuring vector extension on RDS ..."
PGPASSWORD="$CARPAPI_DB_PASSWORD" psql "${RDS_FLAGS[@]}" \
  -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"

# Strip PG-17-only SET directives the destination PG-16 doesn't know.
# `transaction_timeout` (added in PG 17) is the only blocker today; if
# AWS adds more later, append patterns here.
log "Sanitizing dumps for cross-version restore (PG17 -> PG16) ..."
for f in "$DUMP_DIR"/*.sql; do
  sed -i.bak -E '/^SET transaction_timeout/d' "$f"
done

log "Applying schema to RDS ..."
PGPASSWORD="$CARPAPI_DB_PASSWORD" psql "${RDS_FLAGS[@]}" \
  -v ON_ERROR_STOP=0 -f "$DUMP_DIR/schema.sql" \
  > "$DUMP_DIR/schema.log" 2>&1 || \
  log "  (some schema warnings — see $DUMP_DIR/schema.log)"

for tbl in "${TABLES[@]}"; do
  short="${tbl#public.}"
  log "Loading $tbl ..."
  PGPASSWORD="$CARPAPI_DB_PASSWORD" psql "${RDS_FLAGS[@]}" \
    -v ON_ERROR_STOP=1 -f "$DUMP_DIR/data_${short}.sql" \
    > "$DUMP_DIR/load_${short}.log" 2>&1
done

# --------------------------------------------------------------------- #
# 4. Re-NULL embeddings + rebuild HNSW index on RDS (we re-embed below)
# --------------------------------------------------------------------- #
log "Resetting embeddings and rebuilding HNSW index on RDS ..."
PGPASSWORD="$CARPAPI_DB_PASSWORD" psql "${RDS_FLAGS[@]}" -v ON_ERROR_STOP=1 <<'SQL'
DROP INDEX IF EXISTS ix_listings_embedding_hnsw;
ALTER TABLE public.listings DROP COLUMN IF EXISTS embedding;
ALTER TABLE public.listings ADD COLUMN embedding vector(1024);
CREATE INDEX ix_listings_embedding_hnsw
  ON public.listings USING hnsw (embedding vector_cosine_ops);
SQL

# --------------------------------------------------------------------- #
# 5. Sanity counts
# --------------------------------------------------------------------- #
log "Row counts on RDS:"
PGPASSWORD="$CARPAPI_DB_PASSWORD" psql "${RDS_FLAGS[@]}" -At <<'SQL'
SELECT '  dealers              = ' || COUNT(*) FROM public.dealers;
SELECT '  listings             = ' || COUNT(*) FROM public.listings;
SELECT '  listing_price_history= ' || COUNT(*) FROM public.listing_price_history;
SELECT '  makes                = ' || COUNT(*) FROM public.makes;
SELECT '  maker_models         = ' || COUNT(*) FROM public.maker_models;
SQL

cat <<EOF

────────────────────────────────────────────────────────────────────────
 Data migration complete.

 Next: re-embed listings against RDS (one Titan call per listing,
 ~\$0.02 per 1k listings, plus ~1-2 min for 4.4k rows):

     source data/secrets/rds.env
     python -m carpapi.rag.embed --limit 5000

 Then smoke the chat against the cloud DB:

     source data/secrets/rds.env
     python tools/smoke_rag_accuracy.py
────────────────────────────────────────────────────────────────────────
EOF
