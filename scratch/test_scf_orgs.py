import urllib.request
import urllib.parse
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

places = [
    "Palm Coast", "Flagler Beach", "Bunnell", "Flagler",
    "St. Augustine", "St Johns",
    "Fernandina Beach", "Nassau"
]

for p in places:
    url = f"https://seeclickfix.com/api/v2/organizations?search={urllib.parse.quote(p)}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            orgs = data.get("organizations", [])
            print(f"[{p}] -> {len(orgs)} organizations found:")
            for o in orgs:
                print(f"   ID: {o.get('id')}, Name: {o.get('name')}, URL: {o.get('url_name')}")
    except Exception as e:
        print(f"[{p}] error: {e}")
