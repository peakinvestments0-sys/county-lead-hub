import urllib.request
import urllib.parse
import json

CADASTRAL_URL = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query"

for code in ['27', '28']:
    params = {
        'where': f"CO_NO = '{code}'",
        'outFields': 'PHY_ADDR1,PHY_CITY,PHY_ZIPCD',
        'resultRecordCount': '3',
        'f': 'json'
    }
    url = f"{CADASTRAL_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 FloridaLeadHub/2.0'})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        print(f"--- Sample for CO_NO {code} ---")
        for f in data.get('features', []):
            print(f.get('attributes'))
