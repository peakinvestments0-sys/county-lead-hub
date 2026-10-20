import urllib.request
import urllib.parse
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

params = {
    'where': "Compliance_Status LIKE '%NON-COMPLIANT%'",
    'returnCountOnly': 'true',
    'f': 'json'
}
url = f"https://services1.arcgis.com/t2yugAJW83eUIFui/arcgis/rest/services/STR_Properties/FeatureServer/0/query?{urllib.parse.urlencode(params)}"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req) as r:
    print(r.read().decode())
