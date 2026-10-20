import urllib.request
import urllib.parse
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
url = "https://services3.arcgis.com/hSKL9bYjhP4rHxSD/arcgis/rest/services/General_Services_Requests_Public_View/FeatureServer/0/query?where=1=1&outFields=OBJECTID,reqcategory,reqtype,details,location,locdesc,building,status,CreationDate_1&resultRecordCount=20&orderByFields=OBJECTID%20DESC&f=json"

req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=15) as r:
    data = json.loads(r.read().decode())
    for f in data.get("features", []):
        attrs = f.get("attributes", {})
        print(f"ID={attrs.get('OBJECTID')}, Cat={attrs.get('reqcategory')}, Type={attrs.get('reqtype')}, Loc={attrs.get('location')}, Desc={attrs.get('details')[:60] if attrs.get('details') else ''}")
