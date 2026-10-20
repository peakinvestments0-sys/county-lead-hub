import urllib.request
import urllib.parse
import json

headers = {'User-Agent': 'Mozilla/5.0'}

for org, name in [('8Pc9XBTAsYuxx9Ny', 'City of Palm Bay'), ('Tex1uhbqnOZPx6qT', 'City of Cocoa')]:
    url = f"https://www.arcgis.com/sharing/rest/search?q=orgid:{org}&f=json&num=50"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
            data = json.loads(r.read())
            results = data.get('results', [])
            print(f"\n=== {name} (Org: {org}) Items: {len(results)} ===")
            for it in results:
                print(f"  - {it.get('title')} ({it.get('type')}): {it.get('url')}")
    except Exception as e:
        print(f"Error {org}: {e}")
