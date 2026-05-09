import requests, json, time, os
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
PATHS   = ["/", "/contact", "/finance", "/service", "/trade"]

os.makedirs("output/html", exist_ok=True)

def fetch_site(dealer):
    name   = dealer["name"].replace(" ", "_")[:30]
    site   = dealer.get("website", "").rstrip("/")
    if not site:
        return

    for path in PATHS:
        try:
            r = requests.get(site + path, headers=HEADERS, timeout=10)
            slug = path.strip("/") or "home"
            with open(f"output/html/{name}_{slug}.html", "w") as f:
                f.write(r.text)
            time.sleep(0.5)
        except Exception as e:
            print(f"  skip {site+path}: {e}")

if __name__ == "__main__":
    with open("output/profiles.json") as f:
        dealers = json.load(f)

    for d in dealers:
        print(f"Fetching {d['name']}...")
        fetch_site(d)