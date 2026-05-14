# CarPapi operational agent fleet

14 agents organized into 5 tiers. Each agent has a markdown spec
under `.claude/agents/<name>.md` that Claude Code loads as a
sub-agent. The same spec is the prompt for the autonomous Lambda
variants (where applicable).

## Quick index

| Tier | Agent | Type | Cadence | When to summon |
|---|---|---|---|---|
| INGEST | [`scraper-dispatcher`](scraper-dispatcher.md) | dual | daily 04:00 UTC | "rescrape X", "rerun the daily scrape" |
| INGEST | [`listing-validator`](listing-validator.md) | autonomous | per scrape batch | "reprocess quarantined", "why is listing X missing?" |
| INGEST | [`dedupe-sweeper`](dedupe-sweeper.md) | autonomous | daily 06:00 UTC | "this car shows up twice", "why didn't dedup catch X?" |
| INGEST | [`dealer-prospector`](dealer-prospector.md) | interactive | weekly | "find Toyota dealers in NJ", "expand to PA" |
| ENRICH | [`maker-enricher`](maker-enricher.md) | dual | daily 05:00 UTC | "enrich VIN X", "what's the enrichment backlog?" |
| ENRICH | [`maker-site-doctor`](maker-site-doctor.md) | autonomous | daily 03:00 UTC | "is Ford's site stable?", "why did Honda enrichment stop?" |
| QUALITY | [`scrape-watchdog`](scrape-watchdog.md) | autonomous | per scrape + hourly | "is scraping healthy today?", "what alarms fired?" |
| QUALITY | [`data-quality-auditor`](data-quality-auditor.md) | interactive | weekly | "audit the data", "are there orphans?" |
| QUALITY | [`price-anomaly-detector`](price-anomaly-detector.md) | autonomous | daily 07:00 UTC | "any pricing weirdness?", "did Ford prices collapse?" |
| CLOUD-OPS | [`carpapi-deployer`](carpapi-deployer.md) | interactive | n/a | "deploy", "tear down", "roll back" |
| CLOUD-OPS | [`rds-steward`](rds-steward.md) | dual | daily | "how's the DB?", "I need a pre-migration snapshot" |
| CLOUD-OPS | [`aws-cost-sentinel`](aws-cost-sentinel.md) | autonomous | daily 09:00 UTC | "what did we spend?", "Bedrock too expensive?" |
| DELIVERY | [`ci-cd-doctor`](ci-cd-doctor.md) | interactive | reactive | "why is CI red?", "fix the workflow" |
| DELIVERY | [`chat-quality-evaluator`](chat-quality-evaluator.md) | dual | per PR + nightly 02:00 | "did the chat regress?", "add a test case" |

## Daily timeline (UTC)

```
02:00  chat-quality-evaluator    (smoke + latency vs prod)
03:00  maker-site-doctor         (canary per make adapter)
04:00  scraper-dispatcher        (daily inventory scrape)
05:00  maker-enricher            (cold-loop specs backfill)
06:00  dedupe-sweeper            (cross-source clustering)
07:00  price-anomaly-detector    (flag bugs vs flash deals)
09:00  aws-cost-sentinel         (cost digest + budget alerts)
       + scrape-watchdog runs reactively on metric breach
       + listing-validator runs per scrape batch
       + ci-cd-doctor + rds-steward + data-quality-auditor on demand
```

## Type glossary

- **interactive** — invoked by a developer from Claude Code. Lives
  only as a markdown spec.
- **autonomous** — wrapped in a Lambda (or ECS task) and fired by
  EventBridge Scheduler on the cadence above.
- **dual** — both modes. Developer summons OR scheduler fires.

## How to add a new agent

1. Draft `.claude/agents/<name>.md` following the house style
   (YAML frontmatter: name/description/model/tools; markdown body
   with "What CarPapi runs on", playbook, safety boundaries,
   reporting format, references).
2. Add a row to the table above.
3. If autonomous, add an entry to `deploy/eventbridge_schedules.sh`
   and write the corresponding Lambda function.
4. Document the trigger phrases in the agent's `description:` field —
   that's what tells Claude when to dispatch to it.

## Safety pattern (every agent honors)

Every spec has a **"Safety boundaries — things you NEVER do without
explicit user authorization"** section. The pattern is identical to
`carpapi-deployer.md`: enumerate the destructive / irreversible /
high-cost actions and refuse to take them unilaterally. If a
deployer-class agent is ever overpermissive, that's a bug in the
spec, not in the user's request.

## References

- `.claude/plans/analyze-this-and-update-peppy-ullman.md` — the
  plan this roster implements.
- `architecture.md §12` — the RAG pipeline these agents protect.
- `deploy/DEPLOY_STATE.md` — live AWS state every cloud-ops agent
  must memorize.
- `context/`, `skills/`, `runbooks/` — the rule/skill/runbook
  surface every agent leans on.
