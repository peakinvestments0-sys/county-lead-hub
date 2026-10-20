import urllib.request
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
url = "https://services1.arcgis.com/t2yugAJW83eUIFui/arcgis/rest/services?f=json"

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        services = data.get("services", [])
        print(f"StJohnsCountyGIS has {len(services)} services:")
        for s in services:
            print(f" - {s.get('name')} ({s.get('type')})")
except Exception as e:
    print(f"Error: {e}")
