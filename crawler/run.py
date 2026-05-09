import os
os.makedirs("output/html", exist_ok=True)

import crawler, parser, fetcher, extractor

crawler.__dict__  # triggers __main__ block via import won't work — just run directly: