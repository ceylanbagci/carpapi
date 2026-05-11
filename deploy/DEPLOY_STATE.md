> # 🟢 LIVE
> **Frontend (React):** https://d372ww3313y553.cloudfront.net (S3 + CloudFront, OAC-protected)
> **API (Django + RAG):** https://gt3mapscrz.us-east-1.awsapprunner.com
> **Chat:**     `POST /api/chat/` `{"message":"…"}` — 4/4 smoke queries pass with real Bedrock synthesis (skip 2.4s, haiku 2.3s, sonnet 5.7s cold).
> **Stats:**    `GET /api/stats/` — returns 4391 listings / 385 dealers / 42 makes from RDS.

# CarPapi — live AWS state (snapshot)

This document is the source of truth for "what's actually running in AWS
right now." Updated on every successful deploy. If the contents are
stale, run:

```bash
./deploy/aws_teardown.sh   # nuke everything below
./deploy/aws_bootstrap.sh  # start over
```

…and re-record the new IDs here.

---

## Account

| Field | Value |
|---|---|
| AWS account | `183617081338` |
| IAM user | `arn:aws:iam::183617081338:user/car-papi` |
| Region | `us-east-1` |

> ⚠️ **Credential rotation pending.** `AKIASVQDOJ75MIZDS7JG` was pasted in chat on 2026-05-10 and should be disabled + replaced ASAP (IAM Console → Users → car-papi → Security credentials).

## Network

| Resource | ID | Purpose |
|---|---|---|
| Default VPC | `vpc-0236207b03c4d4be4` (172.31.0.0/16) | reused — not project-owned |
| RDS security group | `sg-076ab63563873b45a` (`carpapi-rds-sg`) | guards `:5432`; ingress = home IP + App Runner egress SG |
| App Runner egress SG | `sg-0897cabb71dc01061` (`carpapi-apprunner-egress`) | egress for the VPC connector; default outbound rules |
| App Runner VPC Connector | `arn:aws:apprunner:us-east-1:183617081338:vpcconnector/carpapi-vpc-connector/1/45e44ec480ee441db60d733299b0ac03` | wires App Runner egress through default VPC subnets (1a/1b/1c) |
| Bedrock interface VPC endpoint | `vpce-042d375f94206d022` (`bedrock-runtime`) | so the container can reach Bedrock from VPC egress without NAT; ENIs in 3 AZs, ~$22/mo |

**RDS ingress rules:**
- `:5432` ← `69.124.101.33/32` (home IP, for `psql` ops from laptop)
- `:5432` ← `sg-0897cabb71dc01061` (App Runner egress only — narrow)
- **NOT open to `0.0.0.0/0`** — RDS is unreachable from the public internet.

**App Runner egress SG self-ingress:**
- `:443` ← `sg-0897cabb71dc01061` (self) — required for the container ENIs to reach the Bedrock interface VPC endpoint ENIs (same SG).

## Database

| Field | Value |
|---|---|
| Instance | `carpapi-db` (`db.t4g.micro`, 20 GB gp3, single-AZ) |
| Engine | PostgreSQL `16.13` + pgvector `0.8.1` |
| Endpoint | `carpapi-db.c7oasmx9kbh5.us-east-1.rds.amazonaws.com:5432` |
| Master user | `carpapi` |
| Master password | `data/secrets/rds_master_password.txt` (chmod 600, gitignored) |
| Cost | ~$0.018/hr ≈ $13/month |

**Data loaded (matches local Postgres 17.9 source):**

| Table | Rows |
|---|---|
| `sources` | 171 |
| `dealers` | 385 |
| `makes` | 46 |
| `listings` | 4,391 (all with 1024-dim embeddings) |
| `listing_price_history` | 4,749 |
| `listing_groups` | 0 |

HNSW index `ix_listings_embedding_hnsw` on `(embedding vector_cosine_ops)` carried over from local schema.

## Container registry

| Field | Value |
|---|---|
| ECR repo | `183617081338.dkr.ecr.us-east-1.amazonaws.com/carpapi-api` |
| Pushed tags | `latest`, `<12-char-git-sha>` |

## Frontend (React, S3 + CloudFront)

| Field | Value |
|---|---|
| S3 bucket | `carpapi-frontend-183617081338` (private, block-public-access on) |
| CloudFront distribution ID | `E1UCY9STI5VCUF` |
| CloudFront domain | `d372ww3313y553.cloudfront.net` |
| Origin Access Control | `E1QS4DFOX5F4D1` (sigv4, s3) |
| Cache behaviour | `index.html`: no-cache; assets: `max-age=31536000 immutable` |
| SPA fallback | `403/404 → /index.html` (custom error responses) so React Router works |
| Build-time API base | `VITE_API_BASE=https://gt3mapscrz.us-east-1.awsapprunner.com/api` (in `web/frontend/.env.production`) |
| Cost | ~$1/mo at low traffic (storage <$0.10/mo, CF requests + 100GB egress free tier covers it) |

**Deploy frontend updates:**
```bash
cd web/frontend
npm run build
aws s3 sync dist/ s3://carpapi-frontend-183617081338/ --delete \
  --cache-control "public, max-age=31536000, immutable" \
  --exclude "index.html" --exclude "landing.html"
aws s3 cp dist/index.html s3://carpapi-frontend-183617081338/ \
  --cache-control "public, max-age=0, must-revalidate" --content-type "text/html"
aws s3 cp dist/landing.html s3://carpapi-frontend-183617081338/ \
  --cache-control "public, max-age=0, must-revalidate" --content-type "text/html"
aws cloudfront create-invalidation \
  --distribution-id E1UCY9STI5VCUF --paths "/index.html" "/landing.html"
```

## App Runner service

| Field | Value |
|---|---|
| Service name | `carpapi-api` |
| Service ARN | `arn:aws:apprunner:us-east-1:183617081338:service/carpapi-api/367498f87d9e45bf976fa92b20573149` |
| Public URL | `https://gt3mapscrz.us-east-1.awsapprunner.com` |
| Instance | 1 vCPU / 2 GB |
| Egress | VPC (via connector above) — RDS reach only |
| Health check | `HTTP GET /api/stats/` on port 8000 |
| Cost (active) | ~$0.064/vCPU-hr + $0.007/GB-hr ≈ $0.078/hr ≈ $25/mo at 12h/day |
| Cost (idle-suspended) | ~$0/hr after 15 min of no traffic |

**Runtime env vars** (no secrets in source — set on the service):
- `AWS_REGION=us-east-1`
- `DJANGO_SETTINGS_MODULE=carpapi_web.settings`
- `DJANGO_ALLOWED_HOSTS=*`
- `DJANGO_SECRET_KEY=<runtime-generated>` (move to Secrets Manager pre-prod)
- `CARPAPI_DB_HOST/PORT/NAME/USER/PASSWORD` (from `data/secrets/rds.env`)

**Auth model**: container has no AWS access keys baked in. It calls Bedrock via the App Runner instance role.

## IAM roles

| Role | Purpose | Attached policies |
|---|---|---|
| `CarPapiAppRunnerInstanceRole` | App Runner task identity | `CarPapiBedrockInvoke` (Titan v2 + Haiku 4.5 + Sonnet 4.5 invoke; profile + bare model ARNs) |
| `CarPapiAppRunnerEcrAccessRole` | App Runner ECR pull | `AWSAppRunnerServicePolicyForECRAccess` |
| `CarPapiGitHubDeployer` | GitHub Actions OIDC deploy role | inline `CarPapiDeployInline` (ECR push/pull + App Runner describe/start-deployment) |

GitHub OIDC provider: `arn:aws:iam::183617081338:oidc-provider/token.actions.githubusercontent.com`
Trust policy: only `repo:ceylanbagci/carpapi on refs/heads/main` can assume `CarPapiGitHubDeployer`.

## CI/CD wiring

| Workflow | Trigger | Action |
|---|---|---|
| `.github/workflows/ci.yml` | PR / `feature/*` push | lint + Postgres+pgvector tests + docker build smoke |
| `.github/workflows/deploy.yml` | push to `main` + workflow_dispatch | OIDC → ECR push → `aws apprunner start-deployment` → wait for RUNNING → smoke /api/chat/ |

**Pending one-time setup on your side** (browser only):
1. Go to https://github.com/ceylanbagci/carpapi → **Settings → Secrets and variables → Actions → Variables → New variable**
2. Name: `AWS_DEPLOY_ROLE_ARN`
3. Value: `arn:aws:iam::183617081338:role/CarPapiGitHubDeployer`
4. (Optional) Settings → **Environments → New environment → `production`** with required reviewers if you want a human gate on every prod deploy.

After that, `deploy.yml` runs automatically on merge to `main`. The first auto-deploy will hit the same App Runner service `carpapi-api`.

## Lessons learned during initial deploy

The path from "scripts exist" to "live endpoint serving real RAG
responses" required fixing six distinct issues. The deployer agent
docs them so the next pass is faster.

1. **PG-version mismatch (local PG 17 → RDS PG 16).** pg_dump 16 hard-
   refuses to connect to a PG 17 server. Use PG 17 client binaries
   for pg_dump, but **sanitize** the dump by stripping
   `SET transaction_timeout = 0` lines before applying to RDS
   (PG 17–only setting, unrecognized by 16). Now baked into
   `migrate_to_rds.sh` via `sed -i.bak`.
2. **Dynamic table list.** Hard-coded `TABLES=()` in the migrate
   script referenced `public.maker_models` (doesn't exist) and missed
   `public.sources` + `public.listing_groups`. Now the script
   intersects an `ORDERED_PREFERENCE` array (for FK ordering) with
   the actual `pg_tables` output at runtime.
3. **`collectstatic` crashed** because `settings.py` has `STATIC_URL`
   but no `STATIC_ROOT`. Fixed by removing the step from `Dockerfile`
   (the API is JSON-only). If the Django admin or DRF browsable API
   is wanted in production later, add `STATIC_ROOT = BASE_DIR /
   "staticfiles"` and restore the step.
4. **RDS SG was too narrow for App Runner.** Solved properly with the
   VPC Connector route + an SG-to-SG ingress rule (not by widening
   `:5432` to `0.0.0.0/0`).
5. ⚠️ **Image architecture mismatch.** Docker on Apple Silicon
   defaulted to `linux/arm64`. App Runner runs `linux/amd64`. The
   container exec-format-errored before gunicorn ever started, hence
   no application log group ever appeared. The error message
   "Check your configured port number" sent us on three wild-goose
   chases. **`deploy_apprunner.sh` now hard-codes
   `docker buildx --platform linux/amd64`.**

   If you see another mysterious "health check failed" with no
   application logs in CloudWatch, **check the image arch first**:
   ```bash
   docker buildx imagetools inspect <ECR_URI>:latest | head -10
   ```
   `Platform: linux/arm64` only → rebuild with `--platform linux/amd64`.
6. **Bedrock unreachable from VPC connector.** App Runner ENIs in
   "public" default subnets cannot actually reach the internet without
   either a public IP attached or a NAT Gateway. Fixed with a VPC
   **interface endpoint** for `bedrock-runtime` (3 ENIs across AZs,
   ~$22/mo, cheaper than $32/mo NAT). The container's SG needs a
   self-referencing `:443` ingress rule so its ENIs can connect to
   the endpoint ENIs.
7. **IAM policy too region-narrow.** Inference profile `us.anthropic.*`
   is *registered* in us-east-1 but cross-region invocation routes the
   actual `InvokeModel` to whichever AZ has capacity (often us-east-2
   or us-west-2). The IAM policy must list foundation-model ARNs with
   region `*`, not `us-east-1` only. `deploy/iam_bedrock_policy.json`
   now uses `arn:aws:bedrock:*::foundation-model/...`.

## Smoke commands

```bash
# Live service URL
curl -fsS https://edb6qkw9pa.us-east-1.awsapprunner.com/api/stats/

# Chat endpoint
curl -fsS -X POST https://edb6qkw9pa.us-east-1.awsapprunner.com/api/chat/ \
  -H 'Content-Type: application/json' \
  -d '{"message":"Toyota Camry under $25k"}' | jq .

# Local pipeline against the same RDS
source data/secrets/rds.env
python tools/smoke_rag_accuracy.py
python tools/profile_rag_latency.py
```

## Cost as of this snapshot

| Resource | Idle | Active (12h/day) |
|---|---|---|
| RDS `db.t4g.micro` + 20 GB | $13/mo | $13/mo |
| App Runner 1 vCPU / 2 GB | $0 | $25/mo |
| ECR storage (~600 MB) | $1/mo | $1/mo |
| VPC connector | $0 | $0 |
| Bedrock (per token, see arch §12.5) | $0 | $5-50/mo |
| CloudWatch logs (5 GB) | $3/mo | $3/mo |
| Data transfer | <$1/mo | <$5/mo |
| **Total** | **~$17/mo** | **~$45-100/mo** |

## Production hardening still TODO

These are documented in `PRODUCTION.md §4` and are NOT done yet:

- [ ] Move RDS password + Django secret key to **Secrets Manager** (~$1/mo for 2 secrets)
- [ ] Custom domain + ACM cert (Route 53)
- [ ] Multi-AZ RDS + 7-day backups + deletion protection
- [ ] DRF rate limiting on `/api/chat/` + AWS WAF in front
- [ ] CloudWatch alarms: 5xx rate, p95 latency, RDS CPU, RDS connections, Bedrock 4xx, $$$ budget
- [ ] Pre-prod environment (mirror in `staging` account or canary on prod)
- [ ] Rotate the IAM access key from chat history

## Teardown

```bash
./deploy/aws_teardown.sh
```

Order: App Runner service → IAM roles + policies → ECR repo + images → RDS instance → SGs → VPC connector. Prompts for `destroy`. Total cleanup ~10 min.
