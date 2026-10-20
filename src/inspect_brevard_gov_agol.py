import urllib.request
import json

url = "https://www.arcgis.com/sharing/rest/search?q=orgid:zfDSLldsAGQfwUz9&f=json&num=100"
headers = {'User-Agent': 'Mozilla/5.0'}

try:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
        data = json.loads(r.read())
        items = data.get('results', [])
        print(f"Brevard County AGOL Items: {len(items)}")
        for it in items:
            title = it.get('title', '')
            t = it.get('type', '')
            u = it.get('url', '')
            print(f"  - {title} ({t}): {u}")
except Exception as e:
    print("Error:", e)
