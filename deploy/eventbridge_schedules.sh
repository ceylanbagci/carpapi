#!/usr/bin/env bash
#
# CarPapi — EventBridge schedules for the autonomous agent fleet.
#
# What this does:
#   For each autonomous agent in .claude/agents/ that has an
#   "EventBridge" cadence, provision a Scheduler schedule pointing
#   at a Lambda function (or step function). The agent prompt is
#   passed in as an env var on the Lambda so the same .md file is
#   the single source of truth.
#
# Required Lambda functions (to be deployed separately — this script
# only wires the schedules):
#   - carpapi-scraper-dispatcher       runs python -m carpapi.scrapers.run
#   - carpapi-maker-enricher            runs python -m carpapi.enrich.cli enrich-stale
#   - carpapi-maker-site-doctor         runs canary check + freezes adapters
#   - carpapi-dedupe-sweeper            runs pipeline.carapi_pipeline.dedupe daily
#   - carpapi-price-anomaly-detector    runs anomaly scan
#   - carpapi-aws-cost-sentinel         runs cost-explorer + bedrock log scan
#   - carpapi-chat-quality-evaluator    runs tools/smoke_rag_accuracy.py + profile
#
# All schedule times are UTC. The cadence + reasoning live in
# .claude/agents/<name>.md ; this script is a thin AWS provisioner.
#
# Re-run safe — each schedule is upserted via put-schedule (idempotent).

set -euo pipefail

: "${AWS_REGION:=us-east-1}"
: "${ACCOUNT_ID:=$(aws sts get-caller-identity --query Account --output text)}"
: "${SCHEDULER_ROLE_NAME:=CarPapiSchedulerRole}"

log() { printf '\033[1;36m[schedules]\033[0m %s\n' "$*"; }

# --------------------------------------------------------------------- #
# 0. Scheduler IAM role (one-time)
# --------------------------------------------------------------------- #
#
# EventBridge Scheduler needs a role that lets it invoke Lambda. The
# role's trust policy permits `scheduler.amazonaws.com`.
#
TRUST=$(cat <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
"Principal":{"Service":"scheduler.amazonaws.com"},
"Action":"sts:AssumeRole"}]}
JSON
)
INLINE=$(cat <<JSON
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
"Action":"lambda:InvokeFunction",
"Resource":"arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:carpapi-*"}]}
JSON
)

if ! aws iam get-role --role-name "$SCHEDULER_ROLE_NAME" >/dev/null 2>&1; then
  log "Creating $SCHEDULER_ROLE_NAME ..."
  aws iam create-role --role-name "$SCHEDULER_ROLE_NAME" \
    --assume-role-policy-document "$TRUST" >/dev/null
fi
aws iam put-role-policy --role-name "$SCHEDULER_ROLE_NAME" \
  --policy-name CarPapiSchedulerInvoke --policy-document "$INLINE"
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${SCHEDULER_ROLE_NAME}"

# --------------------------------------------------------------------- #
# Schedule definitions — cadence comes from .claude/agents/<name>.md.
# Keep in alphabetical-by-time order for readability.
# --------------------------------------------------------------------- #
# Format: name | cron(UTC) | target lambda | input JSON (passed to Lambda)
SCHEDULES=(
  "carpapi-maker-site-doctor|0 3 * * ? *|carpapi-maker-site-doctor|{}"
  "carpapi-scraper-dispatcher|0 4 * * ? *|carpapi-scraper-dispatcher|{\"mode\":\"daily\"}"
  "carpapi-maker-enricher|0 5 * * ? *|carpapi-maker-enricher|{\"quota\":500}"
  "carpapi-dedupe-sweeper|0 6 * * ? *|carpapi-dedupe-sweeper|{\"window_hours\":36}"
  "carpapi-price-anomaly-detector|0 7 * * ? *|carpapi-price-anomaly-detector|{}"
  "carpapi-aws-cost-sentinel|0 9 * * ? *|carpapi-aws-cost-sentinel|{}"
  "carpapi-chat-quality-evaluator|0 2 * * ? *|carpapi-chat-quality-evaluator|{\"mode\":\"nightly\"}"
)

for row in "${SCHEDULES[@]}"; do
  IFS='|' read -r NAME CRON LAMBDA INPUT <<<"$row"
  TARGET_ARN="arn:aws:lambda:${AWS_REGION}:${ACCOUNT_ID}:function:${LAMBDA}"

  log "Upserting schedule $NAME → $LAMBDA at cron($CRON UTC) ..."
  aws scheduler create-schedule --region "$AWS_REGION" \
    --name "$NAME" --schedule-expression "cron($CRON)" \
    --schedule-expression-timezone UTC \
    --flexible-time-window '{"Mode":"OFF"}' \
    --target "{\"Arn\":\"$TARGET_ARN\",\"RoleArn\":\"$ROLE_ARN\",\"Input\":\"$INPUT\"}" \
    2>/dev/null \
    || aws scheduler update-schedule --region "$AWS_REGION" \
         --name "$NAME" --schedule-expression "cron($CRON)" \
         --schedule-expression-timezone UTC \
         --flexible-time-window '{"Mode":"OFF"}' \
         --target "{\"Arn\":\"$TARGET_ARN\",\"RoleArn\":\"$ROLE_ARN\",\"Input\":\"$INPUT\"}"
done

cat <<EOF

────────────────────────────────────────────────────────────────────────
 EventBridge schedules provisioned (7 autonomous agents).

 Daily UTC timeline:
   02:00  chat-quality-evaluator   (nightly RAG smoke)
   03:00  maker-site-doctor        (canary per make)
   04:00  scraper-dispatcher       (daily inventory scrape)
   05:00  maker-enricher           (cold-loop specs)
   06:00  dedupe-sweeper           (cross-source clustering)
   07:00  price-anomaly-detector   (history scan)
   09:00  aws-cost-sentinel        (daily cost digest)

 NOTE: this script wires SCHEDULES → LAMBDA functions. The Lambda
 functions themselves are NOT created by this script. Each agent's
 .md file is the prompt; the Lambda code is a thin wrapper that
 loads the prompt + executes the playbook against AWS resources.
 Build the Lambda functions before enabling these schedules to fire,
 or the cron rules will fail with ResourceNotFoundException.
────────────────────────────────────────────────────────────────────────
EOF
