#!/usr/bin/env bash
#
# Deploy the aws-cost-sentinel agent end-to-end:
#   1. IAM role + inline policy (CostExplorer + S3 fleet/ + CloudWatch Logs)
#   2. Lambda function (Python 3.12, zip deploy, 256 MB, 60 s timeout)
#   3. EventBridge schedule (cron(0 9 * * ? *) daily 09:00 UTC)
#   4. CloudWatch log group with 30-day retention
#   5. Manual one-shot invoke to verify state-file write
#
# Idempotent: every step checks first and only creates / updates if
# the resource doesn't already exist. Safe to re-run.
#
# Prereqs (already true on this machine):
#   - AWS_PROFILE=carpapi (set on the calling shell or pass --profile)
#   - python3 + zip in PATH
#   - boto3 is on the Lambda Python 3.12 runtime by default — no
#     pip install / vendoring needed.

set -euo pipefail

ROLE_NAME="CarPapiAwsCostSentinelRole"
POLICY_NAME="CarPapiAwsCostSentinelPolicy"
FUNCTION_NAME="carpapi-aws-cost-sentinel"
SCHEDULE_NAME="carpapi-aws-cost-sentinel-daily"
LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"
REGION="${AWS_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAMBDA_DIR="${SCRIPT_DIR}/../lambdas/aws_cost_sentinel"
PROFILE="${AWS_PROFILE:-carpapi}"

aws_cli() { aws --profile "$PROFILE" --region "$REGION" "$@"; }

log() { printf '\033[1;36m[deploy]\033[0m %s\n' "$*"; }

ACCOUNT_ID=$(aws_cli sts get-caller-identity --query Account --output text)
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

# ─── 1. IAM role + inline policy ────────────────────────────────────
if aws_cli iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  log "role $ROLE_NAME exists"
else
  log "creating role $ROLE_NAME"
  aws_cli iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://${LAMBDA_DIR}/trust_policy.json" \
    --description "Execution role for the aws-cost-sentinel agent Lambda" >/dev/null
  log "  attaching AWSLambdaBasicExecutionRole for CW Logs"
  aws_cli iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
fi

log "updating inline policy (idempotent put)"
aws_cli iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --policy-document "file://${LAMBDA_DIR}/iam_policy.json"

# IAM takes a few seconds to propagate for first-time create. Sleep
# guarded so re-runs don't pay the cost.
if aws_cli iam get-role --role-name "$ROLE_NAME" \
     --query 'Role.CreateDate' --output text | grep -q "$(date -u +%Y-%m-%d)"; then
  log "role created today — waiting 10s for IAM propagation"
  sleep 10
fi

# ─── 2. CloudWatch log group with retention ────────────────────────
if aws_cli logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" \
     --query 'logGroups[?logGroupName==`'"$LOG_GROUP"'`] | length(@)' --output text \
     | grep -q '^1$'; then
  log "log group $LOG_GROUP exists"
else
  log "creating log group $LOG_GROUP"
  aws_cli logs create-log-group --log-group-name "$LOG_GROUP"
fi
aws_cli logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 30 >/dev/null

# ─── 3. Build deployment package (zip) ─────────────────────────────
ZIP="${LAMBDA_DIR}/build.zip"
log "packaging handler → $ZIP"
( cd "$LAMBDA_DIR" && rm -f build.zip && zip -q build.zip handler.py )

# ─── 4. Create or update the Lambda function ───────────────────────
if aws_cli lambda get-function --function-name "$FUNCTION_NAME" >/dev/null 2>&1; then
  log "function $FUNCTION_NAME exists — updating code + config"
  aws_cli lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$ZIP" \
    --publish >/dev/null
  aws_cli lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.12 \
    --handler handler.handler \
    --timeout 60 \
    --memory-size 256 \
    --role "$ROLE_ARN" \
    --environment "Variables={CARPAPI_FLEET_BUCKET=carpapi-frontend-183617081338,CARPAPI_FLEET_PREFIX=fleet,CARPAPI_MONTHLY_BUDGET_USD=100}" \
    >/dev/null
else
  log "creating function $FUNCTION_NAME"
  aws_cli lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.12 \
    --handler handler.handler \
    --role "$ROLE_ARN" \
    --zip-file "fileb://$ZIP" \
    --timeout 60 \
    --memory-size 256 \
    --description "CarPapi aws-cost-sentinel agent — daily Cost Explorer digest" \
    --environment "Variables={CARPAPI_FLEET_BUCKET=carpapi-frontend-183617081338,CARPAPI_FLEET_PREFIX=fleet,CARPAPI_MONTHLY_BUDGET_USD=100}" \
    >/dev/null
fi

FN_ARN=$(aws_cli lambda get-function --function-name "$FUNCTION_NAME" \
  --query 'Configuration.FunctionArn' --output text)
log "Lambda ARN: $FN_ARN"

# ─── 5. EventBridge schedule — daily 09:00 UTC ─────────────────────
RULE_ARN_QUERY=$(aws_cli events describe-rule --name "$SCHEDULE_NAME" \
  --query 'Arn' --output text 2>/dev/null || echo "")
if [ -n "$RULE_ARN_QUERY" ] && [ "$RULE_ARN_QUERY" != "None" ]; then
  log "EventBridge rule $SCHEDULE_NAME exists"
else
  log "creating EventBridge rule $SCHEDULE_NAME (cron 09:00 UTC daily)"
  aws_cli events put-rule \
    --name "$SCHEDULE_NAME" \
    --schedule-expression "cron(0 9 * * ? *)" \
    --state ENABLED \
    --description "Daily 09:00 UTC trigger for aws-cost-sentinel Lambda" >/dev/null
fi

# Permission for EventBridge to invoke the Lambda
STATEMENT_ID="${SCHEDULE_NAME}-invoke"
if aws_cli lambda get-policy --function-name "$FUNCTION_NAME" 2>/dev/null \
     | grep -q "$STATEMENT_ID"; then
  log "EventBridge invoke permission already attached"
else
  log "granting EventBridge invoke permission"
  aws_cli lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id "$STATEMENT_ID" \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/${SCHEDULE_NAME}" \
    >/dev/null
fi

# Wire the rule to the function
log "wiring rule → Lambda target"
aws_cli events put-targets \
  --rule "$SCHEDULE_NAME" \
  --targets "Id"="1","Arn"="$FN_ARN" >/dev/null

# ─── 6. Manual one-shot invocation to seed the fleet state file ────
log "manual invoke (synchronous) to seed state file…"
RC_FILE=$(mktemp)
aws_cli lambda invoke --function-name "$FUNCTION_NAME" \
  --log-type Tail \
  --payload '{"source":"deploy-script"}' --cli-binary-format raw-in-base64-out \
  "$RC_FILE" --query 'LogResult' --output text | base64 -d | tail -30 || true
log "response payload:"
cat "$RC_FILE"; echo
rm -f "$RC_FILE"

# ─── 7. Done ──────────────────────────────────────────────────────
cat <<EOF

────────────────────────────────────────────────────────────────────────
 aws-cost-sentinel deployed
 Lambda:           $FN_ARN
 Role:             $ROLE_ARN
 Schedule:         cron(0 9 * * ? *)  (daily 09:00 UTC)
 Log group:        $LOG_GROUP
 State file:       s3://carpapi-frontend-183617081338/fleet/aws-cost-sentinel.json
 Dashboard:        https://carpappi.com/agents  (refresh after ~30s)

 Cost estimate:    Lambda ~free, Cost Explorer \$0.01/request (1 req/day = \$0.30/mo)
────────────────────────────────────────────────────────────────────────
EOF
