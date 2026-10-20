import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {'User-Agent': 'Mozilla/5.0'}

for s in ['Accela/AccelaGIS_External_WKID2881_AMMS', 'Accela/AccelaGIS_Layers_WKID2881']:
    url = f"https://gis.brevardfl.gov/gissrv/rest/services/{s}/MapServer?f=json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), context=ctx) as r:
            data = json.loads(r.read())
            print(f"=== {s} ===")
            for l in data.get('layers', []):
                print(f"  Layer {l.get('id')}: {l.get('name')}")
    except Exception as e:
        print(f"Error {s}: {e}")
