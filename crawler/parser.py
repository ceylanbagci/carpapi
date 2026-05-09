import requests, json, time
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_website(profile_url):
    try:
        r = requests.get(profile_url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        # DealerRater shows the dealer's own website as an external link
        for a in soup.select("a[href^='http']"):
            href = a["href"]
            if "dealerrater" not in href and "google" not in href:
                return href
        return None
    except Exception as e:
        print(f"Failed {profile_url}: {e}")
        return None

if __name__ == "__main__":
    with open("output/dealers.json") as f:
        dealers = json.load(f)

    for d in dealers:
        d["website"] = get_website(d["profile_url"])
        print(f"{d['name']} → {d['website']}")
        time.sleep(1)

    with open("output/profiles.json", "w") as f:
        json.dump(dealers, f, indent=2)