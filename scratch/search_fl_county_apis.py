import urllib.request
import urllib.parse
import json

counties_to_check = ['Sarasota', 'Manatee', 'Pasco', 'Charlotte', 'Lake', 'Seminole', 'Volusia', 'Alachua']

headers = {'User-Agent': 'Mozilla/5.0'}

for c in counties_to_check:
    query = f'title:"{c}" AND (title:"Code" OR title:"Violation" OR title:"Permit" OR title:"Damage" OR title:"Parcel" OR title:"Address") AND type:"Feature Service"'
    url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(query)}&f=json&num=10"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            results = data.get('results', [])
            print(f"=== {c.upper()} COUNTY ({len(results)} services found) ===")
            for r in results[:4]:
                print(f"  - {r.get('title')} | Owner: {r.get('owner')} | URL: {r.get('url')}")
    except Exception as e:
        print(f"=== {c.upper()} ERROR: {e} ===")
