import json, time, html, requests
from bs4 import BeautifulSoup

BASE    = "https://www.dealerrater.com"
START   = "/directory/new-jersey/Ford/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_soup(path):
    r = requests.get(BASE + path, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")

def extract_dealers(soup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw  = html.unescape(script.string or "")
            data = json.loads(raw)
            if data.get("@type") == "ItemList":
                return [
                    {"name": item["name"], "profile_url": item["url"]}
                    for item in data.get("itemListElement", [])
                ]
        except Exception as e:
            print(f"  parse error: {e}")
            continue
    return []

def next_page(soup):
    tag = soup.find("link", rel="next")
    if tag:
        href = tag.get("href", "").replace(BASE, "")
        return href or None
    return None

def crawl():
    all_dealers, path = [], START

    while path:
        print(f"Fetching: {BASE + path}")
        soup    = get_soup(path)
        dealers = extract_dealers(soup)
        print(f"  → found {len(dealers)} dealers")
        all_dealers.extend(dealers)
        path = next_page(soup)
        if path:
            time.sleep(1.5)

    return all_dealers

if __name__ == "__main__":
    dealers = crawl()
    with open("../output/dealers.json", "w") as f:
        json.dump(dealers, f, indent=2)
    print(f"\nDone. {len(dealers)} dealers saved to output/dealers.json")