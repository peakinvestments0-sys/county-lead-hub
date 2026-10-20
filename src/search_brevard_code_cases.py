import urllib.request
import urllib.parse
import json

headers = {'User-Agent': 'Mozilla/5.0'}

queries = [
    "Brevard County Code Cases",
    "Brevard County Code Violations",
    "City of Melbourne Code Enforcement",
    "City of Melbourne FL Code",
    "City of Palm Bay Code Enforcement",
    "Palm Bay Code Compliance",
    "Brevard County Nuisance",
    "Brevard County Liens",
    "Brevard Building Enforcement"
]

for q in queries:
    url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(q)}&f=json&num=5"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
            data = json.loads(r.read())
            results = data.get('results', [])
            print(f"\nQuery '{q}': {len(results)} results")
            for item in results:
                print(f"  - {item.get('title')} ({item.get('type')}): {item.get('url')} [Org: {item.get('orgId')}]")
    except Exception as e:
        print(f"Error {q}: {e}")
