import urllib.request
import json

headers = {'User-Agent': 'Mozilla/5.0'}
search_url = "https://www.arcgis.com/sharing/rest/search?q=Collier+County+FL+Parcels&f=json&num=20"

try:
    req = urllib.request.Request(search_url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read().decode('utf-8'))
        results = d.get('results', [])
        print(f"Collier search returned {len(results)} items:")
        for r in results:
            print(f"  - Title: {r.get('title')}")
            print(f"    Type: {r.get('type')}")
            print(f"    URL: {r.get('url')}")
            print(f"    Owner: {r.get('owner')}")
except Exception as e:
    print("Error:", e)
