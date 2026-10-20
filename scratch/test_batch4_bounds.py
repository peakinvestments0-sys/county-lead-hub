import urllib.request
import urllib.parse
import json

CADASTRAL_URL = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query"
headers = {'User-Agent': 'Mozilla/5.0 FloridaLeadHub/2.0'}

# Test county candidates:
# Citrus: 19
# Hernando: 37 (or 27?)
# Sumter: 70 (or 60?)
candidates = {
    "Citrus": ["19"],
    "Hernando": ["37", "27"],
    "Sumter": ["70", "60"]
}

for name, codes in candidates.items():
    for c in codes:
        params = {
            'where': f"CO_NO = '{c}'",
            'returnCountOnly': 'true',
            'f': 'json'
        }
        url = f"{CADASTRAL_URL}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read().decode())
                cnt = d.get('count')
                if cnt and cnt > 0:
                    # check sample city
                    p_sample = {
                        'where': f"CO_NO = '{c}' AND PHY_CITY IS NOT NULL",
                        'outFields': 'PHY_CITY',
                        'resultRecordCount': '3',
                        'f': 'json'
                    }
                    with urllib.request.urlopen(urllib.request.Request(f"{CADASTRAL_URL}?{urllib.parse.urlencode(p_sample)}", headers=headers)) as r_s:
                        d_s = json.loads(r_s.read().decode())
                        cities = [f['attributes'].get('PHY_CITY') for f in d_s.get('features', [])]
                    print(f"[{name}] CO_NO '{c}': count={cnt:,}, cities={cities}")
        except Exception as e:
            print(f"[{name}] CO_NO '{c}' error: {e}")
