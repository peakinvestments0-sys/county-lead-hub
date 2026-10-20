import urllib.request
import json

base_url = "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/EnergovCodeCasePublicView/FeatureServer"
req = urllib.request.Request(f"{base_url}?f=json", headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        meta = json.loads(r.read())
        print("Service Name:", meta.get('name'))
        for l in meta.get('layers', []):
            print(f"  Layer {l.get('id')}: {l.get('name')}")
except Exception as e:
    print("Meta error:", e)

# Query layer 0
url0 = f"{base_url}/0?f=json"
try:
    with urllib.request.urlopen(urllib.request.Request(url0, headers={'User-Agent': 'Mozilla/5.0'})) as r:
        meta0 = json.loads(r.read())
        fields = [f['name'] for f in meta0.get('fields', [])]
        print(f"Layer 0 fields ({len(fields)}):", fields)
except Exception as e:
    print("Layer 0 error:", e)

# Count and Sample
count_url = f"{base_url}/0/query?where=1=1&returnCountOnly=true&f=json"
try:
    with urllib.request.urlopen(urllib.request.Request(count_url, headers={'User-Agent': 'Mozilla/5.0'})) as r:
        res = json.loads(r.read())
        print("Palm Bay Energov Code Case count:", res.get('count'))
except Exception as e:
    print("Count error:", e)

sample_url = f"{base_url}/0/query?where=1=1&outFields=*&resultRecordCount=3&f=json"
try:
    with urllib.request.urlopen(urllib.request.Request(sample_url, headers={'User-Agent': 'Mozilla/5.0'})) as r:
        sdata = json.loads(r.read())
        for f in sdata.get('features', []):
            print("Sample record:", f.get('attributes'))
except Exception as e:
    print("Sample error:", e)
