#!/usr/bin/env bash
#
# CarPapi — one-time setup for GitHub Actions → AWS via OIDC.
#
# What you get:
#   - GitHub OIDC provider in the AWS account (idempotent)
#   - IAM role `CarPapiGitHubDeployer` trusted only by the specific
#     repo+branch combinations you whitelist
#   - Inline policy on that role allowing exactly what deploy.yml does:
#       * ECR: GetAuthorizationToken + push to carpapi-api repo
#       * App Runner: describe/start-deployment on carpapi-api service
#       * IAM: read-only describe (for sanity checks)
#   - The role ARN printed to stdout — paste it into GitHub repo
#     Settings → Secrets and variables → Actions → Variables →
#     `AWS_DEPLOY_ROLE_ARN`.
#
# This removes the need for AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
# as long-lived secrets in GitHub. The role is assumed per-run with a
# 1-hour session.
#
# Usage:
#   GITHUB_OWNER=ceylanbagci GITHUB_REPO=carpapi ./deploy/github_oidc_setup.sh
#
# Re-run safe.

set -euo pipefail

: "${AWS_REGION:=us-east-1}"
: "${GITHUB_OWNER:?set GITHUB_OWNER (e.g. ceylanbagci)}"
: "${GITHUB_REPO:?set GITHUB_REPO (e.g. carpapi)}"
: "${ROLE_NAME:=CarPapiGitHubDeployer}"
# Branches allowed to assume this role:
: "${ALLOWED_REF:=refs/heads/main}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
log() { printf '\033[1;36m[oidc]\033[0m %s\n' "$*"; }

# --------------------------------------------------------------------- #
# 1. OIDC provider
# --------------------------------------------------------------------- #
OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
if ! aws iam get-open-id-connect-provider --open-id-connect-provider-arn "$OIDC_ARN" >/dev/null 2>&1; then
  log "Creating GitHub OIDC provider ..."
  aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
    >/dev/null
else
  log "GitHub OIDC provider already present"
fi

# --------------------------------------------------------------------- #
# 2. Trust policy — scoped to repo + branch
# --------------------------------------------------------------------- #
TRUST_DOC=$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Federated": "${OIDC_ARN}" },
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {
      "StringEquals": {
        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
      },
      "StringLike": {
        "token.actions.githubusercontent.com:sub": "repo:${GITHUB_OWNER}/${GITHUB_REPO}:ref:${ALLOWED_REF}"
      }
    }
  }]
}
JSON
)

if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  log "Updating trust policy on existing role $ROLE_NAME"
  aws iam update-assume-role-policy --role-name "$ROLE_NAME" \
    --policy-document "$TRUST_DOC"
else
  log "Creating role $ROLE_NAME"
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document "$TRUST_DOC" \
    --description "GitHub Actions deploy role (CarPapi)" >/dev/null
fi

# --------------------------------------------------------------------- #
# 3. Inline permissions — exactly what deploy.yml does
# --------------------------------------------------------------------- #
INLINE_DOC=$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:DescribeRepositories",
        "ecr:DescribeImages",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AppRunnerDeploy",
      "Effect": "Allow",
      "Action": [
        "apprunner:DescribeService",
        "apprunner:ListServices",
        "apprunner:ListOperations",
        "apprunner:StartDeployment"
      ],
      "Resource": "*"
    },
    {
      "Sid": "StsRead",
      "Effect": "Allow",
      "Action": ["sts:GetCallerIdentity"],
      "Resource": "*"
    }
  ]
}
JSON
)

aws iam put-role-policy --role-name "$ROLE_NAME" \
  --policy-name "CarPapiDeployInline" \
  --policy-document "$INLINE_DOC"

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
cat <<EOF

────────────────────────────────────────────────────────────────────────
 OIDC set up. Paste this into your GitHub repo:

   Settings → Secrets and variables → Actions → Variables → New variable
   Name:   AWS_DEPLOY_ROLE_ARN
   Value:  ${ROLE_ARN}

 Trust policy scope:
   repo:${GITHUB_OWNER}/${GITHUB_REPO} on ${ALLOWED_REF}

 To widen to PR previews later, re-run with:
   ALLOWED_REF='refs/heads/main' ./deploy/github_oidc_setup.sh
   ALLOWED_REF='refs/pull/*'     ./deploy/github_oidc_setup.sh
────────────────────────────────────────────────────────────────────────
EOF
