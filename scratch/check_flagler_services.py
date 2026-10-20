import urllib.request
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

for url, label in [
    ("https://services1.arcgis.com/tpnsCwhQRDqwL3mq/arcgis/rest/services?f=json", "Palm Coast GIS"),
    ("https://services3.arcgis.com/hSKL9bYjhP4rHxSD/arcgis/rest/services?f=json", "Flagler County GIS")
]:
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print(f"=== {label} ({len(data.get('services', []))} services) ===")
            for s in data.get('services', []):
                print(f" - {s.get('name')} ({s.get('type')})")
    except Exception as e:
        print(f"Error {label}: {e}")
