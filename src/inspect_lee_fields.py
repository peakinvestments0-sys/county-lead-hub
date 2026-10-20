import urllib.request
import json

headers = {'User-Agent': 'Mozilla/5.0'}
layer_url = "https://services2.arcgis.com/LvWGAAhHwbCJ2GMP/arcgis/rest/services/Lee_County_Parcels/FeatureServer/0"

# 1. Fields
req = urllib.request.Request(f"{layer_url}?f=json", headers=headers)
with urllib.request.urlopen(req) as resp:
    d = json.loads(resp.read().decode('utf-8'))
    fields = [f.get('name') for f in d.get('fields', [])]
    print(f"Layer 0 Fields ({len(fields)}):", fields)

# 2. Count
req_c = urllib.request.Request(f"{layer_url}/query?where=1%3D1&returnCountOnly=true&f=json", headers=headers)
with urllib.request.urlopen(req_c) as resp:
    dc = json.loads(resp.read().decode('utf-8'))
    print("Total Parcels Count:", dc.get('count'))

# 3. Sample 2 features
req_s = urllib.request.Request(f"{layer_url}/query?where=1%3D1&outFields=*&resultRecordCount=2&f=json", headers=headers)
with urllib.request.urlopen(req_s) as resp:
    ds = json.loads(resp.read().decode('utf-8'))
    for f in ds.get('features', []):
        print("\nSample Feature:", f.get('attributes'))
