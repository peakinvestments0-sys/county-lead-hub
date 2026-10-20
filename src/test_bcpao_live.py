import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {'User-Agent': 'Mozilla/5.0'}

url = "https://gis.brevardfl.gov/gissrv/rest/services/Base_Map/Parcel_New_WKID2881/MapServer/5?f=json"
try:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), context=ctx, timeout=10) as r:
        meta = json.loads(r.read())
        print("BCPAO Live Parcels Layer Name:", meta.get('name'))
        fields = [f['name'] for f in meta.get('fields', [])]
        print(f"Total fields: {len(fields)}")
        print("Fields:", fields)
except Exception as e:
    print("Error:", e)
