# Runbook: scrape failures

## Symptoms

- Zero records in a scheduled window  
- Spike in HTTP 4xx/5xx from a source  
- Extractor exceptions in logs (`SchemaValidationError`, parse timeouts)

## Checks

1. Confirm **EventBridge** / cron fired (last run timestamp).  
2. Inspect **CloudWatch** metrics: `RecordsFetched`, `RecordsNormalized`, `ErrorRate`.  
3. Pull **last raw artifact** from S3 for the source (HTML/JSON) — compare to fixture tests.  
4. Verify **robots.txt** and IP reputation if blocked.

## Mitigation

- Roll back extractor version (deploy previous tag).  
- Increase backoff / reduce concurrency for that source.  
- If HTML layout changed: update selectors in extractor module and add regression fixture.

## Escalation

- Schema drift affecting payment-critical fields (price, VIN): **page on-call** after 2 failed runs.
