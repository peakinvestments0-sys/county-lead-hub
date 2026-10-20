import urllib.request
import json

headers = {'User-Agent': 'Mozilla/5.0'}
hub_url = "https://hub.arcgis.com/api/v3/datasets/a69c335ad6e54fc0872f7ed47208f11e"

try:
    req = urllib.request.Request(hub_url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read().decode('utf-8'))
        print("Hub dataset title:", d.get('data', {}).get('attributes', {}).get('name'))
        # Check download links
        downloads = d.get('data', {}).get('attributes', {}).get('downloads', {})
        print("Downloads:", json.dumps(downloads, indent=2))
except Exception as e:
    print("Hub API error:", e)

# Also check leepa.org or leegov.com for direct file downloads
urls = [
    "https://leegis.leegov.com/datasets/a69c335ad6e54fc0872f7ed47208f11e_0/explore",
    "https://www.leepa.org/DataServices/DataServices.aspx"
]
for u in urls:
    try:
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req) as resp:
            print(f"URL {u}: status OK ({len(resp.read())} bytes)")
    except Exception as e:
        print(f"URL {u}: failed {e}")
