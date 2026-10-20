import urllib.request
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

url = "https://services2.arcgis.com/x5zvhhxfUuRDntRe/arcgis/rest/services/Parcels_Comcate/FeatureServer/0/query?where=1=1&resultRecordCount=3&outFields=*&f=json"
try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
        print(f"Features returned: {len(data.get('features', []))}")
        for f in data.get('features', []):
            print(f.get('attributes'))
except Exception as e:
    print(f"Error: {e}")
