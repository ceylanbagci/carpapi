# CarPapi — Production deployment plan

This is the "how do I take CarPapi from a feature branch on one laptop to a thing real users can hit" doc. It answers the two questions you asked:

1. **EC2 vs Lambda — which is right for CarPapi?** TL;DR: **neither for MVP**. App Runner (already wired in `deploy/`) is the right MVP host. Migrate to **ECS Fargate** at scale. **Lambda is the wrong fit** for the chat endpoint — explained below.
2. **What does the CI/CD pipeline look like?** GitHub Actions + OIDC + ECR + App Runner. The two workflow files (`.github/workflows/ci.yml` and `.github/workflows/deploy.yml`) plus `deploy/github_oidc_setup.sh` make it real.

---

## 1. Serving choice: App Runner vs ECS Fargate vs Lambda vs EC2

| | **Lambda** | **App Runner** (MVP) | **ECS Fargate** (scale) | **EC2** |
|---|---|---|---|---|
| Cold start | 2-5s on Python+Django+psycopg | 5-10s when suspended, ~0 when warm | ~0 (always running) | ~0 |
| Idle cost | $0 | $0 (idle-suspend) | $25-40/mo per task | $15-30/mo per instance |
| Active cost | per-invoke (cheap at low vol) | $0.064/vCPU-hr + $0.007/GB-hr | $0.04/vCPU-hr + $0.004/GB-hr | flat instance price |
| Connection pooling | needs RDS Proxy (+$15/mo) | works directly | works directly | works directly |
| Bedrock streaming | needs Function URL + RESPONSE_STREAM | works | works | works |
| Auto-scaling | per request | 1-25 instances | 1-N via ASG | manual or ASG |
| VPC required | yes, for RDS | no | yes | yes |
| Image size limit | 10 GB (container) | none meaningful | none | none |
| Ops surface | functions + perms | service + env vars | task def + service + ALB + SG + ASG | AMI + IAM + ALB + SG + ASG |
| Best for | spiky background jobs | small-medium API | large-traffic API | special hw / legacy / total control |

**Why Lambda is wrong for the `/api/chat/` endpoint specifically:**

We worked hard to drive p95 latency under **2 seconds** (see `architecture.md §12.3`). Lambda adds **2-5 seconds of cold start** on top of that for a Django + boto3 + psycopg + carpapi container. Even with provisioned concurrency you pay full instance hours (~same as App Runner), losing the only Lambda advantage. The connection pool problem makes it worse — every cold start opens a new psycopg connection, and pgvector queries hold them long enough that you need RDS Proxy or you exhaust the 87-connection limit on `db.t4g.micro`.

**Lambda IS right for**:
- Daily scrape orchestration (`carpapi/scrape/*` adapters via EventBridge cron)
- Webhook receivers (dealer-side inventory updates)
- Image preprocessing (when we add photos)
- One-shot maintenance (re-embed-all, dedupe sweep)

**When to move from App Runner to ECS Fargate:**

| Signal | Fix |
|---|---|
| Sustained traffic > 8 hours/day | Fargate cheaper than App Runner when always-on |
| Need private RDS (no public endpoint) | Fargate in VPC subnet with RDS Proxy |
| App Runner cold-start p99 > 3s | Fargate (no cold starts) |
| >25 concurrent instances needed | App Runner ceiling; Fargate scales further |
| Need custom ALB rules / WAF in front | Fargate + ALB is more flexible |

**When NOT to move to EC2:**

Almost never. EC2 makes sense only for GPU inference (we don't self-host models), special hardware, or licensed software with per-VM pricing. For container workloads, EC2 is just Fargate with extra ops work.

---

## 2. CI/CD architecture

```
┌────────────────┐         ┌──────────────────────┐
│   developer    │ push    │      GitHub          │
│  local branch  │────────▶│  feature/* or PR     │
└────────────────┘         └──────────┬───────────┘
                                      │ triggers
                                      ▼
                           ┌──────────────────────┐
                           │  ci.yml              │
                           │  ─ ruff + mypy       │
                           │  ─ Postgres+pgvector │
                           │    service container │
                           │  ─ eval harnesses    │
                           │  ─ docker build      │
                           │    smoke (no push)   │
                           └──────────┬───────────┘
                                      │ green required
                                      ▼
                           ┌──────────────────────┐
                           │     merge to main    │
                           └──────────┬───────────┘
                                      │
                                      ▼
                           ┌──────────────────────┐
                           │  deploy.yml          │
                           │  ─ OIDC → AWS role   │   (no static keys)
                           │  ─ ECR push          │
                           │  ─ App Runner        │
                           │    start-deployment  │
                           │  ─ wait for RUNNING  │
                           │  ─ smoke /api/chat/  │
                           └──────────┬───────────┘
                                      │
                                      ▼
                              live on App Runner
```

**Why OIDC, not access keys:**
GitHub Actions's `id-token` permission lets the workflow request a short-lived (1h) STS session by proving it's running inside this repo on a whitelisted branch. The IAM role's trust policy refuses everything else. No long-lived secret to leak, no rotation chore, no chat-pasted access keys to revoke.

**What the workflows do:**

`.github/workflows/ci.yml` — runs on every PR and `feature/*` push:
- ruff lint + format check on `carpapi/`, `tools/`, `web/backend/api/`, `services/api/`
- mypy on the RAG layer (warnings only — gradually enforced)
- Spin up Postgres 16 + pgvector as a service container; run `eval/run_planner_eval.py`, `eval/run_pii_redaction_eval.py`, `eval/run_token_cache_eval.py`, `eval/run_relaxation_eval.py` in `--offline` mode (Bedrock mocked)
- `docker build` the deploy image and boot it briefly to confirm it doesn't blow up at import time

`.github/workflows/deploy.yml` — runs on push to `main` and via `workflow_dispatch`:
- OIDC assume the `CarPapiGitHubDeployer` role
- Build the image, tag with the 12-char git SHA + `latest`, push to ECR
- Call `apprunner:StartDeployment` (App Runner has AutoDeploymentsEnabled but we poke explicitly for timing)
- Wait up to 15 min for the service to reach `RUNNING`
- Smoke `/api/stats/` and `/api/chat/` against the live URL; fail the run if either non-200s

**Concurrency**: only one production deploy at a time (`concurrency: deploy-production`). PR builds are cancelled when a newer push comes in (`cancel-in-progress: true`).

**Environment gate**: `deploy` runs in the `production` GitHub Environment. Turn on "Required reviewers" in repo settings to require a human approve before main → live.

---

## 3. One-time setup checklist

Order matters — RDS first so the App Runner service has somewhere to connect.

1. **Bootstrap RDS + data** (one-time, you already have the scripts):
   ```bash
   ./deploy/aws_bootstrap.sh
   source data/secrets/rds.env
   ./deploy/migrate_to_rds.sh
   python -m carpapi.rag.embed --limit 5000
   ```
2. **First App Runner deploy from your laptop** — needs to exist before the GitHub workflow can update it:
   ```bash
   source data/secrets/rds.env
   ./deploy/deploy_apprunner.sh
   ```
3. **OIDC role for GitHub Actions:**
   ```bash
   GITHUB_OWNER=ceylanbagci GITHUB_REPO=carpapi ./deploy/github_oidc_setup.sh
   ```
   Paste the printed role ARN into GitHub: Settings → Secrets and variables → Actions → **Variables** → `AWS_DEPLOY_ROLE_ARN`.
4. **Set up the `production` environment in GitHub** (optional but recommended):
   - Settings → Environments → New environment → `production`
   - Required reviewers: yourself + anyone else who should sign off
   - Wait timer: 0 min (or 5 min if you want a "panic abort" window)
5. **Merge `feature/rag-pipeline` → `main`** to trigger the first deploy.

---

## 4. Production hardening — what's missing vs MVP

The MVP shape we wired (`./deploy/`) gets you to "the chat works from a public URL." This is the gap list before real users.

### 4.1 Secrets

Right now `aws_bootstrap.sh` puts the RDS password in `data/secrets/rds_master_password.txt` and `deploy_apprunner.sh` injects it as an App Runner env var. For prod:

```bash
# One-time: store in Secrets Manager
aws secretsmanager create-secret \
  --name carpapi/rds/master \
  --secret-string "$(cat data/secrets/rds_master_password.txt)"
# Then change App Runner to reference it via Secret: instead of plain env.
```

App Runner supports `Secret:` references in `RuntimeEnvironmentVariables`. Same for `DJANGO_SECRET_KEY`. Cost: $0.40/secret/month, irrelevant at MVP.

### 4.2 Custom domain + TLS

App Runner gives you `<service>.awsapprunner.com`. For a branded URL:
1. Own `carpapi.app` (Route 53 register).
2. App Runner → service → Custom domains → Add `carpapi.app`.
3. App Runner provisions an ACM cert; you add the verification CNAME to Route 53.
4. Point `api.carpapi.app` ALIAS at the App Runner service.

ACM cert is free. Route 53 hosted zone: $0.50/month.

### 4.3 Frontend hosting

React app → S3 + CloudFront + Route 53:
```bash
cd web/frontend && npm run build
aws s3 sync dist/ s3://carpapi-app-static/ --delete
aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"
```
Add a `frontend.yml` workflow that runs on push to main, paths-filter on `web/frontend/**`. ~$1-5/month.

### 4.4 RDS production posture

| Setting | MVP | Production |
|---|---|---|
| Instance class | `db.t4g.micro` | `db.t4g.small` or `db.r7g.large` if vector queries are slow |
| Multi-AZ | off | **on** (~doubles cost; gives HA + faster restore) |
| Backup retention | 0 days | **7 days** |
| Deletion protection | off | **on** |
| Performance Insights | off | **on** (free for 7-day retention) |
| Public access | yes (IP-locked) | **no** — put RDS in private subnet, App Runner reaches it via VPC Connector |

Switching to private RDS adds: VPC, two private subnets, App Runner VPC Connector (+$0.01/hr ≈ $7/month), and either NAT for outbound Bedrock or VPC endpoints (`com.amazonaws.us-east-1.bedrock-runtime` interface endpoint, ~$7/month per AZ).

### 4.5 Rate limiting on `/api/chat/`

Bedrock costs are per-token; an abusive caller can run up a bill fast. Add DRF throttling in `web/backend/api/views.py`:

```python
class ChatThrottle(UserRateThrottle):
    rate = "20/min"
    scope = "chat"

@api_view(["POST"])
@throttle_classes([ChatThrottle])
def chat(request):
    ...
```

For unauthenticated users, key the throttle by IP. For real signups, key by user ID.

### 4.6 WAF in front of App Runner

App Runner supports AWS WAF natively (May 2024 GA). One-time:

```bash
aws wafv2 create-web-acl ...  # AWS managed rule set: Bot Control + Core
aws apprunner associate-web-acl --resource-arn <service-arn> --web-acl-arn <waf-arn>
```

~$5/month base + $1/rule. Worth it for `bot-control` alone.

### 4.7 Observability

App Runner ships logs + metrics to CloudWatch automatically. Add:

| Alarm | Threshold | Action |
|---|---|---|
| 5xx rate on App Runner service | > 1% over 5 min | SNS → email/Slack |
| p95 request latency | > 3000 ms over 5 min | SNS |
| RDS CPU | > 80% over 10 min | SNS |
| RDS free storage | < 5 GB | SNS |
| RDS connections | > 70 (limit is 87 on micro) | SNS |
| Bedrock invocation 4xx | > 0.5% over 5 min | SNS (use-case form revoked? throttle?) |
| Monthly cost | $100 budget breach | AWS Budgets → SNS |

Optional but high-value: ship logs to a hosted destination (Datadog / Honeycomb / Grafana Cloud) so you can query structured fields like `synth_model`, `retrieval_path`, `hits` from the chat response.

### 4.8 Schema migrations

CarPapi maintains schema across two ORMs (Django for `web/backend/api/`, SQLAlchemy for `pipeline/carapi_pipeline/`). For prod migrations:

1. Develop the migration locally against the local Postgres.
2. Dump the schema diff: `pg_dump --schema-only -t <table> > migrations/0042_*.sql`.
3. Add `python deploy/apply_migration.py 0042_*.sql` step to `deploy.yml`, gated on the path filter `migrations/**`.
4. The migration step should run **before** the App Runner deployment (so new code never reads old schema). Add a `migrate` job and have `deploy` need it.

For now, schema changes are rare enough to apply manually via `psql`.

### 4.9 Disaster recovery posture

| Failure | Recovery |
|---|---|
| App Runner service broken | `aws apprunner update-service --source-configuration ImageIdentifier=<prior-sha-tag>` |
| RDS instance corrupted | Restore from automated backup (need ≥1-day retention; off by default in MVP) |
| AZ failure | Multi-AZ RDS handles it; App Runner is regional/multi-AZ already |
| Region failure | Out of scope for MVP; for HA, replicate RDS to a second region + run App Runner there + Route 53 health-checked DNS failover |
| Account compromise | The car-papi user with AdministratorAccess is overscoped. After MVP, create a separate `carpapi-deploy` role and remove admin from the human user. |

### 4.10 Cost guardrails

Hard ceiling via AWS Budgets:
```bash
aws budgets create-budget --account-id $(aws sts get-caller-identity --query Account --output text) \
  --budget '{"BudgetName":"CarPapiMonthly","BudgetLimit":{"Amount":"150","Unit":"USD"},"TimeUnit":"MONTHLY","BudgetType":"COST"}' \
  --notifications-with-subscribers file://deploy/budget_alert.json
```

Bedrock-specific: turn on **Bedrock model invocation logging** to S3 + CloudWatch so you can see per-prompt token counts. Set a Budgets alarm at 50% / 80% / 100% of your monthly Bedrock allowance.

---

## 5. Rollout sequence

| Step | Trigger | Owner | Reversible? |
|---|---|---|---|
| 1. Merge `feature/rag-pipeline` → `main` | manual | you | yes — revert commit |
| 2. CI runs (ci.yml) | auto | GH Actions | n/a |
| 3. Deploy workflow runs (deploy.yml) | auto on main | GH Actions | yes — re-deploy prior SHA tag |
| 4. App Runner pulls new image, deploys | auto | App Runner | yes — `update-service` to prior tag |
| 5. Smoke test passes | auto | deploy.yml | n/a — failure rolls back via App Runner's auto-rollback on `CREATE_FAILED` |
| 6. Watch CloudWatch dashboards for 30 min | manual | you | n/a |
| 7. (later) Custom domain + WAF + Secrets Manager | one-time | you | yes |

**First-deploy gotchas (call these out in the postmortem template):**

- App Runner instance role needs the Bedrock policy attached *before* the first chat request — `deploy_apprunner.sh` handles this, but verify with `aws iam list-attached-role-policies --role-name CarPapiAppRunnerInstanceRole`.
- The RDS SG initially allows `:5432` only from the bootstrap-time public IP. App Runner reaches RDS over the public endpoint with a different egress IP. Either:
  - Add `0.0.0.0/0` for `:5432` on the SG (acceptable since the master password is strong, but lazy), OR
  - Move RDS to a private subnet + VPC Connector (production-correct).
- Bedrock use-case-form: already submitted against `architecture.md`. If you ever see `ResourceNotFoundException: Model use case details have not been submitted` it means the account scoping changed — re-submit via `PutUseCaseForModelAccess`.

---

## 6. Cost projection at three scales

| | Cold MVP | 50 chats/day | 5000 chats/day |
|---|---|---|---|
| RDS `db.t4g.micro`/`small` | $15 | $15 | $30 |
| App Runner runtime | $0 idle | $5 | $50 |
| Bedrock (per `architecture.md §12.5`) | $0 | $1 | $50 |
| ECR storage + transfer | $1 | $1 | $5 |
| CloudWatch logs/metrics | $1 | $3 | $10 |
| Route 53 + ACM | $1 | $1 | $1 |
| WAF (when added) | $0 | $6 | $6 |
| Secrets Manager (3 secrets) | $0 | $2 | $2 |
| **Total** | **~$18** | **~$34** | **~$154** |

At 5k chats/day you'll want to look at:
- TokenCache hit rate — Redis-backed instead of SQLite to share across App Runner instances (one ElastiCache `t4g.micro` ~$12/month, can cut Bedrock spend 30-50%)
- pgvector index tuning (HNSW `m`, `ef_construction`) once retrieval p95 climbs
- Consider switching `chat` to ECS Fargate at sustained high traffic for cheaper steady-state

---

## 7. Open production decisions for you

These are choices I cannot make for you — they depend on business context:

1. **Authentication.** Right now `/api/chat/` is public. Options: Cognito (AWS-native, $0/MAU under 50k), Clerk/Auth0 (better UX, $25/mo small plan), keep public + rely on rate limit + WAF only.
2. **Domain.** Are we shipping at `carpapi.app`, a subdomain of an existing site, or only `*.awsapprunner.com` for the MVP?
3. **Region.** Stay in `us-east-1` (cheapest Bedrock, lowest latency to NJ test data)? Or replicate to `us-west-2` for HA?
4. **Telemetry destination.** CloudWatch only, or add Datadog/Honeycomb? CloudWatch is fine for MVP; structured logging shines elsewhere.
5. **Pre-prod environment.** Mirror app runner + RDS in a second account for `staging`, or trust CI + canary deploys?
6. **On-call.** PagerDuty (~$15/user/month) or just SNS → email/Slack?

Tell me what you want for any of these and I'll wire it in.

---

## 8. What to do this week

If "ship it" is the goal, the minimum production deploy is:

1. ✅ Branch is ready (`feature/rag-pipeline`)
2. ☐ Run `./deploy/aws_bootstrap.sh` (you, ~15 min wait)
3. ☐ Run `./deploy/migrate_to_rds.sh` (~5 min)
4. ☐ Run `python -m carpapi.rag.embed --limit 5000` (~2 min)
5. ☐ Run `./deploy/deploy_apprunner.sh` (~10 min)
6. ☐ Smoke `curl https://<service>.awsapprunner.com/api/chat/`
7. ☐ Run `./deploy/github_oidc_setup.sh` once
8. ☐ Set the `AWS_DEPLOY_ROLE_ARN` repo variable in GitHub
9. ☐ Merge `feature/rag-pipeline` → `main` — first auto-deploy happens
10. ☐ Watch the deploy workflow finish; click the URL it prints

That's the path to "real users can hit it." Steps 4.1-4.10 in this doc are the path to "I'd ship this at a real company."
