import urllib.request
import urllib.parse
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

# Check Nassau PA Demolition / Permit feed
url = "https://services5.arcgis.com/F73IhFZbCCYUexxB/arcgis/rest/services/YardDebris/FeatureServer/0/query?where=demo_val>0+OR+permit_status+IS+NOT+NULL&outFields=*&f=json"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.loads(r.read().decode())
    features = data.get("features", [])
    print(f"Nassau demo/permit records: {len(features)}")
    for f in features[:5]:
        attrs = f.get("attributes", {})
        print(f"  PIN={attrs.get('PIN')}, strap={attrs.get('strap')}, Situs={attrs.get('Situs_full')}, demo_val={attrs.get('demo_val')}, permit_status={attrs.get('permit_status')}")
