import urllib.request
import json

headers = {'User-Agent': 'Mozilla/5.0'}
url = "https://www.arcgis.com/sharing/rest/search?q=orgid:zfDSLldsAGQfwUz9&start=51&num=100&f=json"

try:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
        data = json.loads(r.read())
        items = data.get('results', [])
        print(f"Page 2 items for Brevard AGOL: {len(items)}")
        for it in items:
            title = it.get('title', '')
            t = it.get('type', '')
            u = it.get('url', '')
            if any(w in title.lower() for w in ['code', 'violation', 'permit', 'damage', 'unsafe', 'lien', 'inspect', 'case', 'building', 'flood', 'planning', 'property']):
                print(f"  - {title} ({t}): {u}")
except Exception as e:
    print("Error:", e)
