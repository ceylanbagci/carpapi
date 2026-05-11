#!/usr/bin/env bash
#
# CarPapi — AWS bootstrap (idempotent).
#
# What this does, in order:
#   1.  Sanity-check AWS identity + region + tool versions.
#   2.  Create a security group that allows :5432 from your current public IP.
#   3.  Generate a 32-char DB master password into data/secrets/rds_master_password.txt
#       (chmod 600, gitignored).
#   4.  Create an RDS PostgreSQL 16 instance:
#         db.t4g.micro, 20 GB gp3, single AZ, public-accessible (SG-locked),
#         backup retention 0, no Multi-AZ.  ~$15/month.
#   5.  Wait for it to be Available (typically 8-12 minutes).
#   6.  Install the `vector` extension via psql.
#   7.  Print the DSN, write data/secrets/rds.env for the migration script.
#
# Re-run safe: each step checks for existence before creating.
#
# Required tools on PATH:  awscli v2, psql, curl, openssl.
#
# Usage:
#   ./deploy/aws_bootstrap.sh
#
# Cleanup (if you want to undo everything):
#   ./deploy/aws_teardown.sh

set -euo pipefail

# --------------------------------------------------------------------- #
#  Tunables — override via env if desired
# --------------------------------------------------------------------- #
: "${AWS_REGION:=us-east-1}"
: "${DB_IDENTIFIER:=carpapi-db}"
: "${DB_ENGINE_VERSION:=16.4}"
: "${DB_INSTANCE_CLASS:=db.t4g.micro}"
: "${DB_STORAGE_GB:=20}"
: "${DB_NAME:=carpapi}"
: "${DB_MASTER_USER:=carpapi}"
: "${SG_NAME:=carpapi-rds-sg}"
: "${SECRETS_DIR:=data/secrets}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$SECRETS_DIR" && chmod 700 "$SECRETS_DIR"

log()  { printf '\033[1;36m[bootstrap]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[bootstrap] %s\033[0m\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------------- #
# 1. Sanity checks
# --------------------------------------------------------------------- #
log "AWS identity:"
aws sts get-caller-identity --output table || fail "AWS creds missing/broken"
[[ "$(aws configure get region 2>/dev/null || echo "$AWS_REGION")" == "$AWS_REGION" ]] \
  || log "(warning) configured region != ${AWS_REGION}; using --region flag"

command -v psql >/dev/null  || fail "psql is required (brew install libpq && brew link --force libpq)"
command -v curl >/dev/null  || fail "curl is required"

# --------------------------------------------------------------------- #
# 2. Default VPC + Security Group
# --------------------------------------------------------------------- #
DEFAULT_VPC=$(aws ec2 describe-vpcs --region "$AWS_REGION" \
  --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)
[[ "$DEFAULT_VPC" == "None" ]] && fail "No default VPC found in $AWS_REGION"
log "Default VPC: $DEFAULT_VPC"

EXISTING_SG=$(aws ec2 describe-security-groups --region "$AWS_REGION" \
  --filters "Name=group-name,Values=${SG_NAME}" "Name=vpc-id,Values=${DEFAULT_VPC}" \
  --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

if [[ "$EXISTING_SG" == "None" || -z "$EXISTING_SG" ]]; then
  log "Creating security group $SG_NAME ..."
  SG_ID=$(aws ec2 create-security-group --region "$AWS_REGION" \
    --group-name "$SG_NAME" \
    --description "CarPapi RDS access (Postgres 5432)" \
    --vpc-id "$DEFAULT_VPC" \
    --query 'GroupId' --output text)
  log "  → $SG_ID"
else
  SG_ID="$EXISTING_SG"
  log "Reusing security group $SG_ID"
fi

MY_IP="$(curl -fsS https://checkip.amazonaws.com)"
log "Your public IP: $MY_IP — adding inbound :5432 rule"
aws ec2 authorize-security-group-ingress --region "$AWS_REGION" \
  --group-id "$SG_ID" \
  --protocol tcp --port 5432 --cidr "${MY_IP}/32" 2>/dev/null \
  || log "  (rule already exists, skipping)"

# --------------------------------------------------------------------- #
# 3. Master password
# --------------------------------------------------------------------- #
PASS_FILE="$SECRETS_DIR/rds_master_password.txt"
if [[ ! -s "$PASS_FILE" ]]; then
  log "Generating master password → $PASS_FILE"
  # 32-char URL-safe random; no @ / " or backslash (avoids shell + URL escaping).
  openssl rand -base64 48 \
    | tr -d '\n=+/@"\\' \
    | cut -c1-32 \
    > "$PASS_FILE"
  chmod 600 "$PASS_FILE"
else
  log "Reusing existing password from $PASS_FILE"
fi
DB_PASS="$(cat "$PASS_FILE")"
[[ ${#DB_PASS} -ge 16 ]] || fail "Password too short ($PASS_FILE)"

# --------------------------------------------------------------------- #
# 4. RDS instance
# --------------------------------------------------------------------- #
RDS_STATUS=$(aws rds describe-db-instances --region "$AWS_REGION" \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || echo "missing")

if [[ "$RDS_STATUS" == "missing" ]]; then
  log "Creating RDS instance $DB_IDENTIFIER ($DB_INSTANCE_CLASS, ${DB_STORAGE_GB}GB, pg${DB_ENGINE_VERSION}) ..."
  aws rds create-db-instance --region "$AWS_REGION" \
    --db-instance-identifier "$DB_IDENTIFIER" \
    --db-instance-class "$DB_INSTANCE_CLASS" \
    --engine postgres \
    --engine-version "$DB_ENGINE_VERSION" \
    --allocated-storage "$DB_STORAGE_GB" \
    --storage-type gp3 \
    --master-username "$DB_MASTER_USER" \
    --master-user-password "$DB_PASS" \
    --db-name "$DB_NAME" \
    --vpc-security-group-ids "$SG_ID" \
    --publicly-accessible \
    --backup-retention-period 0 \
    --no-multi-az \
    --no-deletion-protection \
    --no-enable-performance-insights \
    --tags Key=Project,Value=CarPapi Key=Env,Value=mvp \
    >/dev/null
  log "  → submitted; instance will be 'creating' for ~10 min"
else
  log "RDS $DB_IDENTIFIER already exists (status=$RDS_STATUS)"
fi

# --------------------------------------------------------------------- #
# 5. Wait for Available
# --------------------------------------------------------------------- #
log "Waiting for $DB_IDENTIFIER to become available (up to 20 min) ..."
aws rds wait db-instance-available --region "$AWS_REGION" \
  --db-instance-identifier "$DB_IDENTIFIER"
log "  → available"

DB_ENDPOINT=$(aws rds describe-db-instances --region "$AWS_REGION" \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --query 'DBInstances[0].Endpoint.Address' --output text)
DB_PORT=$(aws rds describe-db-instances --region "$AWS_REGION" \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --query 'DBInstances[0].Endpoint.Port' --output text)
log "Endpoint: $DB_ENDPOINT:$DB_PORT"

# --------------------------------------------------------------------- #
# 6. Install pgvector
# --------------------------------------------------------------------- #
export PGPASSWORD="$DB_PASS"
log "Installing 'vector' extension ..."
psql -h "$DB_ENDPOINT" -p "$DB_PORT" -U "$DB_MASTER_USER" -d "$DB_NAME" \
  -v ON_ERROR_STOP=1 \
  -c "CREATE EXTENSION IF NOT EXISTS vector;" \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'plpgsql');"
unset PGPASSWORD

# --------------------------------------------------------------------- #
# 7. Write DSN/env for downstream scripts
# --------------------------------------------------------------------- #
cat > "$SECRETS_DIR/rds.env" <<EOF
# CarPapi RDS connection — generated by deploy/aws_bootstrap.sh
# Source this file before running migrate_to_rds.sh or starting the API
# against the cloud DB.
export CARPAPI_DB_HOST=$DB_ENDPOINT
export CARPAPI_DB_PORT=$DB_PORT
export CARPAPI_DB_NAME=$DB_NAME
export CARPAPI_DB_USER=$DB_MASTER_USER
export CARPAPI_DB_PASSWORD=$(cat "$PASS_FILE")
export AWS_REGION=$AWS_REGION
EOF
chmod 600 "$SECRETS_DIR/rds.env"
log "Wrote $SECRETS_DIR/rds.env (chmod 600, gitignored)"

cat <<EOF

────────────────────────────────────────────────────────────────────────
 RDS is up.  Cost: ~\$15/month idle (\$0.018/hr db.t4g.micro + storage).
 Endpoint:  $DB_ENDPOINT:$DB_PORT
 DSN:       postgres://$DB_MASTER_USER:****@$DB_ENDPOINT:$DB_PORT/$DB_NAME
 SG:        $SG_ID  (locked to $MY_IP/32)

 Next:  source $SECRETS_DIR/rds.env && ./deploy/migrate_to_rds.sh
────────────────────────────────────────────────────────────────────────
EOF
