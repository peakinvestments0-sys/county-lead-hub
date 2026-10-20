import urllib.request
import urllib.parse
import json

CADASTRAL_URL = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query"

# Florida DOR county codes:
# Flagler: 28 (or 27?)
# St. Johns: 65
# Nassau: 55
codes = {
    "Flagler": ["27", "28"],
    "St. Johns": ["65"],
    "Nassau": ["55"]
}

for name, candidates in codes.items():
    for code in candidates:
        params = {
            'where': f"CO_NO = '{code}'",
            'returnCountOnly': 'true',
            'f': 'json'
        }
        url = f"{CADASTRAL_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 FloridaLeadHub/2.0'})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                print(f"{name} (CO_NO '{code}'): count = {data.get('count')}")
        except Exception as e:
            print(f"{name} (CO_NO '{code}'): error {e}")
