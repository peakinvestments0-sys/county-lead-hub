import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = 'https://gis-pinellas.hub.arcgis.com/api/v3/datasets?page[size]=25'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    res = urllib.request.urlopen(req, timeout=10, context=ctx)
    d = json.loads(res.read())
    items = d.get('data', [])
    print(f"gis-pinellas.hub.arcgis.com Datasets found: {len(items)}\n")
    for item in items:
        attrs = item.get('attributes', {})
        d_id = item.get('id')
        name = attrs.get('name')
        svc_url = attrs.get('url', '')
        print(f"[{d_id}] {name:<45} -> {svc_url}")
except Exception as e:
    print("Error:", e)
