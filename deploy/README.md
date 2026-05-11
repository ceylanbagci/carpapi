# CarPapi — AWS deployment (MVP shape)

End-to-end deployment of the chat pipeline from `architecture.md §12` to AWS.

> **Going to production?** Read [`PRODUCTION.md`](PRODUCTION.md) — it covers serving choice (App Runner vs ECS vs Lambda vs EC2), CI/CD pipeline via GitHub Actions + OIDC, hardening checklist, cost projections, and the one-time rollout sequence.

```
Local Postgres :5433  ──► RDS Postgres 16 + pgvector (db.t4g.micro)
                           │
                           ▼
                  App Runner (Django + RAG container, 1 vCPU / 2 GB)
                           │
                           ▼
                      Bedrock (Titan v2, Haiku 4.5, Sonnet 4.5)
```

Frontend hosting (S3 + CloudFront) is intentionally out of scope here —
the React app already builds locally and any static host works. The piece
that needs AWS specifically is the API + DB.

## What this directory contains

| File | Purpose |
|---|---|
| `aws_bootstrap.sh` | Creates security group, RDS Postgres 16 instance with pgvector, generates master password. Idempotent. |
| `migrate_to_rds.sh` | Dumps schema + data from local Postgres :5433, restores into RDS, resets the embedding column. |
| `Dockerfile` | Builds the Django+RAG image. Build context = repo root. |
| `apprunner.yaml` | Optional source-config for App Runner "deploy from source" path. |
| `iam_bedrock_policy.json` | Least-privilege policy for the App Runner instance role to invoke Bedrock. |
| `deploy_apprunner.sh` | Creates ECR repo, builds + pushes image, creates IAM roles, creates/updates the App Runner service. |
| `aws_teardown.sh` | Destroys everything created by the two scripts above. Idempotent. |
| `github_oidc_setup.sh` | One-time AWS-side: creates the GitHub OIDC provider + `CarPapiGitHubDeployer` IAM role so GitHub Actions can deploy without long-lived access keys. |
| `PRODUCTION.md` | Serving comparison, CI/CD architecture, production hardening, cost projections. Read before going live. |
| `../.github/workflows/ci.yml` | PR-time lint + Postgres+pgvector tests + Docker build smoke. |
| `../.github/workflows/deploy.yml` | On-merge-to-main: OIDC auth → ECR push → App Runner deploy → smoke test. |

## Prereqs

- `aws` CLI v2 + valid creds (admin perms ideal for first deploy; tighten later)
- `psql` (libpq) — `brew install libpq && brew link --force libpq`
- `docker` running locally (App Runner image build)
- `pg_dump` matching the local Postgres version
- Bedrock model access already approved in `us-east-1` (already done for this account per the use-case-form submission)

## Run order

```bash
cd /Users/ahu/Documents/CarPapi   # repo root

# 1) RDS + pgvector. ~10-15 min, ~$15/month idle.
./deploy/aws_bootstrap.sh

# 2) Schema + data migration. ~2-5 min for 4.4k listings.
source data/secrets/rds.env
./deploy/migrate_to_rds.sh

# 3) Re-embed listings against RDS (Titan v2, ~$0.02 per 1k embeds).
python -m carpapi.rag.embed --limit 5000

# 4) Sanity-check the cloud DB locally.
python tools/smoke_rag_accuracy.py
python tools/profile_rag_latency.py

# 5) Build, push, deploy the API to App Runner. ~5-8 min.
source data/secrets/rds.env
./deploy/deploy_apprunner.sh
```

Output of step 5 prints the public URL. Smoke from the laptop:

```bash
curl -s -X POST https://<service>.awsapprunner.com/api/chat/ \
  -H 'Content-Type: application/json' \
  -d '{"message":"Toyota Camry under $25k"}' | jq .
```

## Costs (rough, `us-east-1`, May 2026)

| Resource | Monthly idle | Monthly active (12h/day) |
|---|---|---|
| RDS Postgres `db.t4g.micro` + 20 GB gp3 | ~$15 | ~$15 |
| App Runner 1 vCPU / 2 GB | ~$0 (suspends) | ~$25 |
| ECR repo (storage only) | <$1 | <$1 |
| Bedrock calls | $0 | ~$5-50 (depends on traffic; see `architecture.md §12.5`) |
| Data transfer + CloudWatch | <$5 | <$10 |
| **Total** | **~$20** | **~$45-100** |

The expensive surprise on most AWS deployments is a NAT gateway (~$32/month idle). We avoid it here because App Runner runs outside any VPC and RDS is public-with-SG-lockdown.

## Security model

- The RDS instance is publicly accessible **only from the IP that ran `aws_bootstrap.sh`** (the security group rule is `:5432 ← <your-ip>/32`). App Runner reaches it over the public endpoint as well; add an App Runner egress rule to the SG once the service is up if you want to tighten further.
- The master password lives in `data/secrets/rds_master_password.txt` (chmod 600, gitignored). It is also baked into App Runner's runtime env vars. Move to **Secrets Manager** before this thing has users — `deploy_apprunner.sh` is wired to read the secret directly when you swap that env-var block for a `Secret:` reference.
- The App Runner **instance role** holds the only Bedrock permissions. The container has no AWS access keys baked in; `boto3` picks up the role via IMDSv2.
- The `DJANGO_SECRET_KEY` is generated fresh on each `deploy_apprunner.sh` run unless one is exported. For real production, generate once and store in Secrets Manager.

## Rollback

```bash
./deploy/aws_teardown.sh
```

Prompts for `destroy` to confirm; then deletes App Runner → IAM → ECR → RDS → SG, in that order. Total cleanup time ~10 min.

## Common gotchas

1. **`pg_dump: server version mismatch`** — RDS is Postgres 16; install matching client. `brew install postgresql@16` then `brew link --force postgresql@16`.
2. **`InvalidParameterValue: pgvector not enabled`** — `aws_bootstrap.sh` runs `CREATE EXTENSION vector` against the RDS instance; if you set up RDS by hand, do that first.
3. **App Runner stuck in `OPERATION_IN_PROGRESS`** — first deploy can take 8-10 min. After 15 min, check `aws apprunner describe-service --service-arn ...` for `EventStream` errors.
4. **Bedrock `ValidationException: on-demand throughput isn't supported`** — you used a bare model ID instead of the `us.anthropic.claude-...` inference profile. The code uses profile IDs already; check `carpapi/cache/bedrock_client.py::MODEL_ALIASES`.
5. **Chat returns 500 with `pii_in_prompt`** — `TokenCache.PIIInPromptError`; this is the PII guard catching a phone/email/SSN in the inbound message. Surface as a 400 to the user.

## Where the secrets live (and where they don't)

```
data/secrets/                    chmod 600, gitignored
├── rds_master_password.txt      generated by aws_bootstrap.sh
└── rds.env                      DSN + creds for migrate_to_rds.sh / re-embed

App Runner service env vars      runtime only; never on disk
├── CARPAPI_DB_*                 from rds.env
├── DJANGO_SECRET_KEY            generated per-deploy
└── AWS credentials              NOT SET — picked up via instance role
```

Nothing under `data/secrets/` is committed to git. The `.gitignore` rule is `data/secrets/`.
