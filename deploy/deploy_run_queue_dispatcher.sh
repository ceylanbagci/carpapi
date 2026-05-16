#!/usr/bin/env bash
#
# Deploy the run-queue-dispatcher Lambda + wire S3 event notifications
# so writes to s3://<bucket>/fleet/queue/*.json fire it. Idempotent.
#
# Prereqs:
#   - AWS_PROFILE=carpapi (or pass via env)
#   - The 14 agent Lambdas already exist (carpapi-<slug>)
#   - The CarPapiAppRunnerInstanceRole already has read on fleet/*; we
#     ALSO need to attach s3:PutObject on fleet/queue/* — done by
#     `deploy_apprunner_fleet_write.sh` (call that first or together).

set -euo pipefail

ROLE_NAME="CarPapiRunQueueDispatcherRole"
POLICY_NAME="CarPapiRunQueueDispatcherPolicy"
FUNCTION_NAME="carpapi-run-queue-dispatcher"
LOG_GROUP="/aws/lambda/${FUNCTION_NAME}"
BUCKET="${CARPAPI_FLEET_BUCKET:-carpapi-frontend-183617081338}"
REGION="${AWS_REGION:-us-east-1}"
PROFILE="${AWS_PROFILE:-carpapi}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAMBDA_DIR="${SCRIPT_DIR}/../lambdas/run_queue_dispatcher"

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
    --description "Execution role for the run-queue-dispatcher Lambda" >/dev/null
  log "  attaching AWSLambdaBasicExecutionRole"
  aws_cli iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
fi
log "updating inline policy"
aws_cli iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$POLICY_NAME" \
  --policy-document "file://${LAMBDA_DIR}/iam_policy.json"
# Allow IAM propagation on first-create.
if aws_cli iam get-role --role-name "$ROLE_NAME" --query 'Role.CreateDate' \
     --output text | grep -q "$(date -u +%Y-%m-%d)"; then
  log "role created today — sleeping 10s for IAM propagation"
  sleep 10
fi

# ─── 2. CloudWatch log group ────────────────────────────────────────
if ! aws_cli logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" \
       --query 'logGroups[?logGroupName==`'"$LOG_GROUP"'`] | length(@)' \
       --output text | grep -q '^1$'; then
  log "creating log group $LOG_GROUP"
  aws_cli logs create-log-group --log-group-name "$LOG_GROUP"
fi
aws_cli logs put-retention-policy --log-group-name "$LOG_GROUP" \
  --retention-in-days 30 >/dev/null

# ─── 3. Package + deploy Lambda (zip) ───────────────────────────────
ZIP="${LAMBDA_DIR}/build.zip"
log "packaging handler → $ZIP"
( cd "$LAMBDA_DIR" && rm -f build.zip && zip -q build.zip handler.py )

if aws_cli lambda get-function --function-name "$FUNCTION_NAME" >/dev/null 2>&1; then
  log "function exists — updating code + config"
  aws_cli lambda update-function-code \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://$ZIP" --publish >/dev/null
  aws_cli lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.12 --handler handler.handler \
    --timeout 30 --memory-size 256 \
    --role "$ROLE_ARN" \
    --environment "Variables={CARPAPI_FLEET_BUCKET=${BUCKET},CARPAPI_FLEET_PREFIX=fleet,CARPAPI_ALLOWED_LAMBDA_PREFIX=carpapi-}" \
    >/dev/null
else
  log "creating function $FUNCTION_NAME"
  aws_cli lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.12 --handler handler.handler \
    --role "$ROLE_ARN" \
    --zip-file "fileb://$ZIP" \
    --timeout 30 --memory-size 256 \
    --description "Reads fleet/queue/*.json markers and invokes the target agent Lambda" \
    --environment "Variables={CARPAPI_FLEET_BUCKET=${BUCKET},CARPAPI_FLEET_PREFIX=fleet,CARPAPI_ALLOWED_LAMBDA_PREFIX=carpapi-}" \
    >/dev/null
fi
FN_ARN=$(aws_cli lambda get-function --function-name "$FUNCTION_NAME" \
  --query 'Configuration.FunctionArn' --output text)
log "Lambda ARN: $FN_ARN"

# ─── 4. Grant S3 permission to invoke the Lambda ────────────────────
STATEMENT_ID="s3-fleet-queue-invoke"
if aws_cli lambda get-policy --function-name "$FUNCTION_NAME" 2>/dev/null \
     | grep -q "$STATEMENT_ID"; then
  log "S3 invoke permission already attached"
else
  log "granting S3 invoke permission"
  aws_cli lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id "$STATEMENT_ID" \
    --action lambda:InvokeFunction \
    --principal s3.amazonaws.com \
    --source-arn "arn:aws:s3:::${BUCKET}" \
    --source-account "$ACCOUNT_ID" \
    >/dev/null
fi

# ─── 5. Wire S3 bucket notification ─────────────────────────────────
# IMPORTANT: put-bucket-notification-configuration REPLACES the entire
# config. So we read the current config, merge our LambdaFunctionConfig,
# and write it back.
log "wiring S3 ObjectCreated:* for fleet/queue/*.json → Lambda"
CURRENT=$(aws_cli s3api get-bucket-notification-configuration --bucket "$BUCKET" 2>/dev/null || echo '{}')

python3 - "$CURRENT" "$FN_ARN" "$BUCKET" <<'PY' > /tmp/carpapi_notif.json
import json, sys
current, fn_arn, bucket = json.loads(sys.argv[1] or '{}'), sys.argv[2], sys.argv[3]
configs = list(current.get("LambdaFunctionConfigurations", []))
configs = [c for c in configs if c.get("Id") != "carpapi-run-queue-dispatch"]
configs.append({
    "Id": "carpapi-run-queue-dispatch",
    "LambdaFunctionArn": fn_arn,
    "Events": ["s3:ObjectCreated:*"],
    "Filter": {"Key": {"FilterRules": [
        {"Name": "prefix", "Value": "fleet/queue/"},
        {"Name": "suffix", "Value": ".json"},
    ]}},
})
out = {k: v for k, v in current.items() if k != "ResponseMetadata"}
out["LambdaFunctionConfigurations"] = configs
print(json.dumps(out))
PY

aws_cli s3api put-bucket-notification-configuration \
  --bucket "$BUCKET" \
  --notification-configuration "file:///tmp/carpapi_notif.json"

# ─── 6. Done ────────────────────────────────────────────────────────
cat <<EOF

────────────────────────────────────────────────────────────────────────
 run-queue-dispatcher deployed
 Lambda:    $FN_ARN
 Role:      $ROLE_ARN
 Trigger:   s3://${BUCKET}/fleet/queue/*.json  (ObjectCreated)
 Log group: $LOG_GROUP
────────────────────────────────────────────────────────────────────────
 Try it from your machine:
   curl -sS -X POST https://api.carpappi.com/api/agents/aws-cost-sentinel/run/ \\
     -H 'content-type: application/json' \\
     -d '{"reason":"smoke-test"}'
 Then watch logs:
   aws --profile $PROFILE --region $REGION logs tail $LOG_GROUP --follow
EOF
