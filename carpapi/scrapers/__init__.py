"""Scrapers — data collection layer.

Hard rule (context/scraper-rules.md guideline 4):
    Zero AI in the scraping layer. Approved stack: requests, BeautifulSoup4,
    Selenium, lxml. Prohibited: Claude, OpenAI, Bedrock, any LLM API,
    paid AI enrichment services, AI-driven browser automation
    (browser-use, Stagehand).

Each module here is responsible for one source. They emit raw dicts that
the ingest pipeline (carapi_pipeline.normalize) turns into canonical
CarListing records. Post-run statistical monitoring lives in
carpapi.monitor.scrape_monitor.
"""
