import urllib.request
import urllib.parse
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

queries = [
    "Citrus County code enforcement",
    "Citrus County code violations",
    "Hernando County code enforcement",
    "Hernando County code violations",
    "Sumter County code enforcement",
    "City of Wildwood code enforcement",
    "owner:HernandoGIS",
    "owner:CitrusCountyGIS",
    "owner:SumterGIS"
]

print("Searching ArcGIS Online for Batch 4 open data layers...")
for q in queries:
    url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(q)}&num=4&f=json"
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
