import urllib.request
import json

headers = {'User-Agent': 'Mozilla/5.0'}
search_url = "https://www.arcgis.com/sharing/rest/search?q=owner:CollierCountyAGOL&f=json&num=50"

try:
    req = urllib.request.Request(search_url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read().decode('utf-8'))
        results = d.get('results', [])
        print(f"CollierCountyAGOL has {len(results)} items:")
        for r in results:
            print(f"  - {r.get('title')} ({r.get('type')}): {r.get('url')}")
except Exception as e:
    print("Error:", e)
