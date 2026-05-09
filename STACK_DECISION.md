# Stack decision: listings + vectors

## Decision

Use **Amazon Aurora PostgreSQL** (or plain RDS Postgres in dev) with the **pgvector** extension as the **single system of record** for structured listings **and** embedding search.

**Do not** run dual indexing in OpenSearch + Postgres for MVP.

## Rationale

| Criterion | Aurora Postgres + pgvector | OpenSearch (k-NN) + separate SQL |
|-----------|------------------------------|-----------------------------------|
| Dedupe + transactional upserts | Strong (constraints, unique indexes) | Weaker; often needs second store anyway |
| SQL / NL → structured filters | Native | DSL learning curve; cross-stack joins painful |
| Vector similarity | Good enough at moderate scale via pgvector IVFFlat/HNSW | Excellent at huge scale |
| Ops surface | One engine, backups, IAM DB auth | Cluster sizing + JVM + index tuning |

CarPapi needs **correct merges**, **price freshness**, and **validated queries** first; vector search is an **add-on** on the same rows (title/description embedding).

## When to reconsider OpenSearch

- **Multi-million** listings with **strict** sub-50ms kNN at high QPS.  
- Heavy **full-text** requirements beyond Postgres `tsvector` + trigram.  

Migration path: replicate listing IDs + vectors to OpenSearch; keep Postgres authoritative.

## AWS wiring (production sketch)

- **Aurora Serverless v2** Postgres 15+ with `pgvector`.  
- App users: **read-only** for chat API; **writer** role for pipeline only.  
- Optional **S3** for raw scrape payloads; **EventBridge** schedules pipeline tasks.

## Local dev

Docker Compose provides Postgres + pgvector (see repo root `docker-compose.yml`).
