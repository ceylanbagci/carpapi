# Daily scrape schedule (AWS)

Production alignment with [architecture.md](../architecture.md) §8:

1. **EventBridge** rule per source (rate or cron), staggering start times.  
2. Task invokes container/Lambda that runs `carapi-run-pipeline` logic (same Python package).  
3. **Metrics:** pipeline emits **Embedded Metric Format** lines (stdout) plus optional **CloudWatch** namespace via `CARAPI_CLOUDWATCH_NAMESPACE`.  
4. **Alarms:** low `RecordsNormalized`, high `RecordsRejected`, zero successful runs in 24h.  

Local cron equivalent:

```cron
0 6 * * * DATABASE_URL=... /path/to/.venv/bin/carapi-run-pipeline --sample
```

Replace `--sample` with your packaged crawl entrypoint when live scrapers ship.
