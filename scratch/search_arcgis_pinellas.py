import urllib.request
import urllib.parse
import json

query = 'owner:"PinellasCounty_eGIS" OR title:"Pinellas"'
url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(query)}&f=json&num=25"

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        results = data.get('results', [])
        print(f"Total results: {len(results)}")
        for r in results:
            print(f"- {r.get('title')} ({r.get('type')}) | Owner: {r.get('owner')} | URL: {r.get('url')}")
except Exception as e:
    print("Error:", e)
