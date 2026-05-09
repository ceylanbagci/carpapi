import os, json
from bs4 import BeautifulSoup

def extract(html):
    soup = BeautifulSoup(html, "html.parser")
    return {
        "forms":   [f.get("action","") for f in soup.find_all("form")],
        "inputs":  list({i.get("name","") for i in soup.find_all("input") if i.get("name")}),
        "buttons": [b.get_text(strip=True) for b in soup.find_all("button")][:10],
        "links":   list({a["href"] for a in soup.find_all("a", href=True) if a["href"].startswith("http")})[:20]
    }

if __name__ == "__main__":
    results = {}
    for fname in os.listdir("output/html"):
        if not fname.endswith(".html"):
            continue
        with open(f"output/html/{fname}") as f:
            results[fname] = extract(f.read())

    with open("output/extracted.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"Extracted {len(results)} pages")