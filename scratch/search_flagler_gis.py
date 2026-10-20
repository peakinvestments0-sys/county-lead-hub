import urllib.request
import urllib.parse
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

for q in ["Flagler County parcels", "Nassau County parcels", "City of Palm Coast"]:
    url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(q)}&num=5&f=json"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode())
        print(f"=== {q} ===")
        for item in data.get('results', []):
            print(item.get('title'), '|', item.get('owner'), '|', item.get('url'))
