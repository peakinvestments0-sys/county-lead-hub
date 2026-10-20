import urllib.request
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

for service in ["General_Services_Requests_Public_View", "TowRepoReports_public"]:
    url = f"https://services3.arcgis.com/hSKL9bYjhP4rHxSD/arcgis/rest/services/{service}/FeatureServer/0/query?where=1=1&resultRecordCount=3&f=json"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print(f"=== {service} ===")
            print(f"Count returned: {len(data.get('features', []))}")
            for f in data.get('features', []):
                print(f.get('attributes'))
    except Exception as e:
        print(f"Error {service}: {e}")
