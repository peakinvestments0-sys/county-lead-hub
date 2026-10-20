import urllib.request
import urllib.parse
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

queries = [
    "St Johns County code enforcement",
    "St Johns County code violations",
    "City of St Augustine code enforcement",
    "Flagler County code enforcement",
    "Palm Coast code enforcement",
    "Palm Coast code violations",
    "Nassau County code enforcement",
    "Fernandina Beach code enforcement"
]

print("Searching ArcGIS Online for Batch 3 open data layers...")
for q in queries:
    url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(q)}&num=5&f=json"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            results = data.get("results", [])
            for r in results:
                title = r.get("title")
                type_ = r.get("type")
                url_layer = r.get("url")
                owner = r.get("owner")
                if "Feature" in type_ or "Map" in type_:
                    print(f"[{q}] -> {title} ({type_}) | Owner: {owner} | URL: {url_layer}")
    except Exception as e:
        print(f"Error for {q}: {e}")
