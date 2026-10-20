import urllib.request
import urllib.parse
import json

headers = {'User-Agent': 'Mozilla/5.0'}

queries = [
    "Palm Bay Code Enforcement",
    "Palm Bay Code Cases",
    "City of Palm Bay",
    "Melbourne Code Compliance",
    "City of Melbourne FL",
    "Cocoa Code Enforcement",
    "City of Cocoa FL",
    "Titusville Code Enforcement",
    "Brevard County Code Compliance"
]

for q in queries:
    url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(q)}&f=json&num=10"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
            data = json.loads(r.read())
            results = data.get('results', [])
            orgs = set(it.get('orgId') for it in results if it.get('orgId'))
            print(f"\nQuery '{q}': {len(results)} items, Orgs: {orgs}")
            for it in results[:4]:
                if any(w in it.get('title', '').lower() for w in ['code', 'violation', 'parcel', 'permit', 'case', 'distress', 'damage', 'address', 'planning']):
                    print(f"  - {it.get('title')} ({it.get('type')}): {it.get('url')} [Org: {it.get('orgId')}]")
    except Exception as e:
        print(f"Error {q}: {e}")
