#!/usr/bin/env bash
#
# CarPapi — destroy everything aws_bootstrap.sh + deploy_apprunner.sh
# created. Idempotent. Safe to re-run.
#
# Order is the reverse of creation:
#   1. App Runner service
#   2. App Runner IAM roles (instance + ECR access)
#   3. Bedrock IAM policy
#   4. ECR repo (with force-delete of images)
#   5. RDS instance (skip-final-snapshot)
#   6. RDS security group
#
# The local password/env files under data/secrets/ are NOT deleted —
# delete them by hand once you confirm the cloud-side is gone.

set -euo pipefail

: "${AWS_REGION:=us-east-1}"
: "${DB_IDENTIFIER:=carpapi-db}"
: "${SG_NAME:=carpapi-rds-sg}"
: "${EGRESS_SG_NAME:=carpapi-apprunner-egress}"
: "${VPC_CONNECTOR_NAME:=carpapi-vpc-connector}"
: "${ECR_REPO:=carpapi-api}"
: "${SERVICE_NAME:=carpapi-api}"
: "${INSTANCE_ROLE_NAME:=CarPapiAppRunnerInstanceRole}"
: "${ACCESS_ROLE_NAME:=CarPapiAppRunnerEcrAccessRole}"
: "${DEPLOY_ROLE_NAME:=CarPapiGitHubDeployer}"
: "${BEDROCK_POLICY_NAME:=CarPapiBedrockInvoke}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log() { printf '\033[1;31m[teardown]\033[0m %s\n' "$*"; }

read -p "About to destroy CarPapi AWS resources in account $ACCOUNT_ID. Type 'destroy' to continue: " confirm
[[ "$confirm" == "destroy" ]] || { echo "aborted"; exit 1; }

# --------------------------------------------------------------------- #
# 1. App Runner service
# --------------------------------------------------------------------- #
APP_ARN=$(aws apprunner list-services --region "$AWS_REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" \
  --output text 2>/dev/null || echo "None")
if [[ "$APP_ARN" != "None" && -n "$APP_ARN" ]]; then
  log "Deleting App Runner service $SERVICE_NAME ..."
  aws apprunner delete-service --region "$AWS_REGION" --service-arn "$APP_ARN" >/dev/null
  log "  (service deletion is async; takes ~5 min to finish)"
fi

# --------------------------------------------------------------------- #
# 2. IAM roles + policy
# --------------------------------------------------------------------- #
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${BEDROCK_POLICY_NAME}"

for ROLE in "$INSTANCE_ROLE_NAME" "$ACCESS_ROLE_NAME"; do
  if aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
    log "Detaching policies from $ROLE ..."
    aws iam list-attached-role-policies --role-name "$ROLE" \
      --query 'AttachedPolicies[].PolicyArn' --output text 2>/dev/null \
      | tr '\t' '\n' \
      | while read -r arn; do
          [[ -n "$arn" ]] || continue
          aws iam detach-role-policy --role-name "$ROLE" --policy-arn "$arn" 2>/dev/null || true
        done
    aws iam delete-role --role-name "$ROLE" 2>/dev/null || true
  fi
done

if aws iam get-policy --policy-arn "$POLICY_ARN" >/dev/null 2>&1; then
  log "Deleting policy $BEDROCK_POLICY_NAME ..."
  # Drop non-default versions first.
  aws iam list-policy-versions --policy-arn "$POLICY_ARN" \
    --query 'Versions[?!IsDefaultVersion].VersionId' --output text \
    | tr '\t' '\n' \
    | while read -r v; do
        [[ -n "$v" ]] || continue
        aws iam delete-policy-version --policy-arn "$POLICY_ARN" --version-id "$v" 2>/dev/null || true
      done
  aws iam delete-policy --policy-arn "$POLICY_ARN" 2>/dev/null || true
fi

# --------------------------------------------------------------------- #
# 3. ECR repo
# --------------------------------------------------------------------- #
if aws ecr describe-repositories --region "$AWS_REGION" \
     --repository-names "$ECR_REPO" >/dev/null 2>&1; then
  log "Deleting ECR repo $ECR_REPO (with all images) ..."
  aws ecr delete-repository --region "$AWS_REGION" \
    --repository-name "$ECR_REPO" --force >/dev/null
fi

# --------------------------------------------------------------------- #
# 4. RDS instance
# --------------------------------------------------------------------- #
if aws rds describe-db-instances --region "$AWS_REGION" \
     --db-instance-identifier "$DB_IDENTIFIER" >/dev/null 2>&1; then
  log "Deleting RDS $DB_IDENTIFIER (skip-final-snapshot) ..."
  aws rds delete-db-instance --region "$AWS_REGION" \
    --db-instance-identifier "$DB_IDENTIFIER" \
    --skip-final-snapshot --delete-automated-backups \
    >/dev/null
  log "  Waiting for deletion (~5 min) ..."
  aws rds wait db-instance-deleted --region "$AWS_REGION" \
    --db-instance-identifier "$DB_IDENTIFIER"
fi

# --------------------------------------------------------------------- #
# 5. RDS security group
# --------------------------------------------------------------------- #
DEFAULT_VPC=$(aws ec2 describe-vpcs --region "$AWS_REGION" \
  --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)

# 4a. App Runner VPC connector (must come before SGs that it references)
VPC_CONN_ARN=$(aws apprunner list-vpc-connectors --region "$AWS_REGION" \
  --query "VpcConnectors[?VpcConnectorName=='${VPC_CONNECTOR_NAME}'].VpcConnectorArn | [0]" \
  --output text 2>/dev/null || echo "None")
if [[ "$VPC_CONN_ARN" != "None" && -n "$VPC_CONN_ARN" ]]; then
  log "Deleting VPC connector $VPC_CONNECTOR_NAME ..."
  aws apprunner delete-vpc-connector --region "$AWS_REGION" \
    --vpc-connector-arn "$VPC_CONN_ARN" >/dev/null 2>&1 \
    || log "  (delete failed — service may still be referencing it; retry after service deletes)"
fi

# 4b. GitHub deploy role (separate IAM role used only by Actions)
if aws iam get-role --role-name "$DEPLOY_ROLE_NAME" >/dev/null 2>&1; then
  log "Deleting inline policy + role $DEPLOY_ROLE_NAME ..."
  aws iam delete-role-policy --role-name "$DEPLOY_ROLE_NAME" \
    --policy-name CarPapiDeployInline 2>/dev/null || true
  aws iam delete-role --role-name "$DEPLOY_ROLE_NAME" 2>/dev/null || true
fi

# 5. Security groups — RDS SG first (was created first), then egress SG.
#    Order doesn't strictly matter since neither is in use after RDS is gone.
for sg in "$SG_NAME" "$EGRESS_SG_NAME"; do
  SG_ID=$(aws ec2 describe-security-groups --region "$AWS_REGION" \
    --filters "Name=group-name,Values=${sg}" "Name=vpc-id,Values=${DEFAULT_VPC}" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")
  if [[ "$SG_ID" != "None" && -n "$SG_ID" ]]; then
    log "Deleting security group $sg ($SG_ID) ..."
    aws ec2 delete-security-group --region "$AWS_REGION" --group-id "$SG_ID" 2>/dev/null \
      || log "  (failed — likely still attached to a removing resource; retry in a few min)"
  fi
done

cat <<'EOF'

────────────────────────────────────────────────────────────────────────
 Cloud teardown complete (or scheduled).
 If you also want to wipe local artifacts:
     rm -rf data/secrets data/dumps
────────────────────────────────────────────────────────────────────────
EOF
