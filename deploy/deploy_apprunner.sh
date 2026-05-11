#!/usr/bin/env bash
#
# CarPapi — build, push, and (re)deploy the Django/RAG container to
# App Runner. Idempotent: re-run creates resources only if missing.
#
# Order:
#   1.  Create an ECR repo `carpapi-api` (if missing).
#   2.  docker build & push the image tagged with the current git SHA
#       plus `latest`.
#   3.  Create the App Runner instance role with the Bedrock policy in
#       deploy/iam_bedrock_policy.json (if missing).
#   4.  Create or update an App Runner service that pulls from ECR.
#       Auto-deploy on push is enabled.
#   5.  Print the service URL.
#
# Prereqs:
#   - source data/secrets/rds.env  (so the service knows its DB)
#   - docker logged in (we do `aws ecr get-login-password` inline)
#   - awscli v2, docker
#
# Cost: App Runner = $0.064/vCPU-hr + $0.007/GB-hr while RUNNING.
#       Idle suspend (default) drops to ~$0/hr.
#       1 vCPU / 2 GB active 12h/day → ~$25/month.

set -euo pipefail

: "${AWS_REGION:=us-east-1}"
: "${ECR_REPO:=carpapi-api}"
: "${SERVICE_NAME:=carpapi-api}"
: "${INSTANCE_ROLE_NAME:=CarPapiAppRunnerInstanceRole}"
: "${BEDROCK_POLICY_NAME:=CarPapiBedrockInvoke}"

: "${CARPAPI_DB_HOST:?source data/secrets/rds.env first}"
: "${CARPAPI_DB_PORT:?}"
: "${CARPAPI_DB_NAME:?}"
: "${CARPAPI_DB_USER:?}"
: "${CARPAPI_DB_PASSWORD:?}"
: "${DJANGO_SECRET_KEY:=$(openssl rand -base64 48 | tr -d '\n=+/' | cut -c1-50)}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
GIT_SHA=$(git rev-parse --short=12 HEAD 2>/dev/null || echo "dev")
IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

log() { printf '\033[1;36m[apprunner]\033[0m %s\n' "$*"; }

# --------------------------------------------------------------------- #
# 1. ECR repo
# --------------------------------------------------------------------- #
if ! aws ecr describe-repositories --region "$AWS_REGION" \
       --repository-names "$ECR_REPO" >/dev/null 2>&1; then
  log "Creating ECR repo $ECR_REPO ..."
  aws ecr create-repository --region "$AWS_REGION" \
    --repository-name "$ECR_REPO" \
    --image-scanning-configuration scanOnPush=true \
    --image-tag-mutability MUTABLE >/dev/null
else
  log "ECR repo $ECR_REPO exists"
fi

# --------------------------------------------------------------------- #
# 2. Build & push
# --------------------------------------------------------------------- #
log "Docker login → ECR ..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin \
      "${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

log "Building image (this can take 3-5 min on first build) ..."
docker build -f deploy/Dockerfile -t "${ECR_REPO}:${GIT_SHA}" -t "${ECR_REPO}:latest" .

log "Pushing $IMAGE_URI:{$GIT_SHA,latest} ..."
docker tag "${ECR_REPO}:${GIT_SHA}"  "${IMAGE_URI}:${GIT_SHA}"
docker tag "${ECR_REPO}:latest"      "${IMAGE_URI}:latest"
docker push "${IMAGE_URI}:${GIT_SHA}"
docker push "${IMAGE_URI}:latest"

# --------------------------------------------------------------------- #
# 3. App Runner instance role with Bedrock policy
# --------------------------------------------------------------------- #
TRUST_DOC='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"tasks.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

if ! aws iam get-role --role-name "$INSTANCE_ROLE_NAME" >/dev/null 2>&1; then
  log "Creating IAM role $INSTANCE_ROLE_NAME ..."
  aws iam create-role --role-name "$INSTANCE_ROLE_NAME" \
    --assume-role-policy-document "$TRUST_DOC" >/dev/null
fi

POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${BEDROCK_POLICY_NAME}"
if ! aws iam get-policy --policy-arn "$POLICY_ARN" >/dev/null 2>&1; then
  log "Creating IAM policy $BEDROCK_POLICY_NAME ..."
  aws iam create-policy --policy-name "$BEDROCK_POLICY_NAME" \
    --policy-document file://deploy/iam_bedrock_policy.json >/dev/null
fi
aws iam attach-role-policy --role-name "$INSTANCE_ROLE_NAME" \
  --policy-arn "$POLICY_ARN" 2>/dev/null || true

INSTANCE_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${INSTANCE_ROLE_NAME}"
log "Instance role: $INSTANCE_ROLE_ARN"

# --------------------------------------------------------------------- #
# 4. App Runner access role (lets App Runner pull from ECR)
# --------------------------------------------------------------------- #
ACCESS_ROLE_NAME="CarPapiAppRunnerEcrAccessRole"
ACCESS_TRUST='{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"build.apprunner.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
if ! aws iam get-role --role-name "$ACCESS_ROLE_NAME" >/dev/null 2>&1; then
  log "Creating ECR access role $ACCESS_ROLE_NAME ..."
  aws iam create-role --role-name "$ACCESS_ROLE_NAME" \
    --assume-role-policy-document "$ACCESS_TRUST" >/dev/null
  aws iam attach-role-policy --role-name "$ACCESS_ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess >/dev/null
fi
ACCESS_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ACCESS_ROLE_NAME}"

# --------------------------------------------------------------------- #
# 5. Create or update the App Runner service
# --------------------------------------------------------------------- #
SOURCE_CFG_FILE=$(mktemp)
trap 'rm -f "$SOURCE_CFG_FILE"' EXIT
cat > "$SOURCE_CFG_FILE" <<JSON
{
  "ImageRepository": {
    "ImageIdentifier": "${IMAGE_URI}:latest",
    "ImageRepositoryType": "ECR",
    "ImageConfiguration": {
      "Port": "8000",
      "RuntimeEnvironmentVariables": {
        "AWS_REGION": "${AWS_REGION}",
        "DJANGO_SETTINGS_MODULE": "carpapi_web.settings",
        "DJANGO_ALLOWED_HOSTS": "*",
        "DJANGO_SECRET_KEY": "${DJANGO_SECRET_KEY}",
        "CARPAPI_DB_HOST": "${CARPAPI_DB_HOST}",
        "CARPAPI_DB_PORT": "${CARPAPI_DB_PORT}",
        "CARPAPI_DB_NAME": "${CARPAPI_DB_NAME}",
        "CARPAPI_DB_USER": "${CARPAPI_DB_USER}",
        "CARPAPI_DB_PASSWORD": "${CARPAPI_DB_PASSWORD}"
      }
    }
  },
  "AutoDeploymentsEnabled": true,
  "AuthenticationConfiguration": {
    "AccessRoleArn": "${ACCESS_ROLE_ARN}"
  }
}
JSON

INSTANCE_CFG='{"Cpu":"1 vCPU","Memory":"2 GB","InstanceRoleArn":"'"$INSTANCE_ROLE_ARN"'"}'
HEALTH_CFG='{"Protocol":"HTTP","Path":"/api/stats/","Interval":20,"Timeout":5,"HealthyThreshold":1,"UnhealthyThreshold":3}'

EXISTING_ARN=$(aws apprunner list-services --region "$AWS_REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" \
  --output text 2>/dev/null || echo "None")

if [[ "$EXISTING_ARN" == "None" || -z "$EXISTING_ARN" ]]; then
  log "Creating App Runner service $SERVICE_NAME ..."
  aws apprunner create-service --region "$AWS_REGION" \
    --service-name "$SERVICE_NAME" \
    --source-configuration "file://$SOURCE_CFG_FILE" \
    --instance-configuration "$INSTANCE_CFG" \
    --health-check-configuration "$HEALTH_CFG" \
    --tags Key=Project,Value=CarPapi Key=Env,Value=mvp \
    >/dev/null
  EXISTING_ARN=$(aws apprunner list-services --region "$AWS_REGION" \
    --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" \
    --output text)
else
  log "Updating App Runner service $SERVICE_NAME ..."
  aws apprunner update-service --region "$AWS_REGION" \
    --service-arn "$EXISTING_ARN" \
    --source-configuration "file://$SOURCE_CFG_FILE" \
    --instance-configuration "$INSTANCE_CFG" \
    --health-check-configuration "$HEALTH_CFG" >/dev/null
fi

log "Waiting for service to be RUNNING (5-8 min) ..."
while true; do
  STATUS=$(aws apprunner describe-service --region "$AWS_REGION" \
    --service-arn "$EXISTING_ARN" \
    --query 'Service.Status' --output text)
  log "  status=$STATUS"
  [[ "$STATUS" == "RUNNING" ]] && break
  [[ "$STATUS" == "CREATE_FAILED" || "$STATUS" == "OPERATION_IN_PROGRESS" && $SECONDS -gt 1200 ]] \
    && { log "service did not become RUNNING in time; check console"; break; }
  sleep 20
done

SERVICE_URL=$(aws apprunner describe-service --region "$AWS_REGION" \
  --service-arn "$EXISTING_ARN" \
  --query 'Service.ServiceUrl' --output text)
cat <<EOF

────────────────────────────────────────────────────────────────────────
 App Runner service: $SERVICE_NAME
 URL:                https://$SERVICE_URL
 Health endpoint:    https://$SERVICE_URL/api/stats/
 Chat endpoint:      curl -X POST https://$SERVICE_URL/api/chat/ \\
                       -H 'Content-Type: application/json' \\
                       -d '{"message":"Toyota Camry under \$25k"}'

 Cost:  1 vCPU / 2 GB at ~\$0.064/vCPU-hr + \$0.007/GB-hr while RUNNING.
        Idle suspend reduces to ~\$0/hr after ~15 min no traffic.
────────────────────────────────────────────────────────────────────────
EOF
