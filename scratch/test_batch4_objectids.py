import urllib.request
import urllib.parse
import json

CADASTRAL_URL = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query"
headers = {'User-Agent': 'Mozilla/5.0 FloridaLeadHub/2.0'}

targets = {
    "citrus": "19",
    "hernando": "37",
    "sumter": "70"
}

for name, co_no in targets.items():
    p_min = {
        'where': f"CO_NO = '{co_no}'",
        'outFields': 'OBJECTID',
        'orderByFields': 'OBJECTID ASC',
        'resultRecordCount': '1',
        'f': 'json'
    }
    p_max = {
        'where': f"CO_NO = '{co_no}'",
        'outFields': 'OBJECTID',
        'orderByFields': 'OBJECTID DESC',
        'resultRecordCount': '1',
        'f': 'json'
    }

    url_min = f"{CADASTRAL_URL}?{urllib.parse.urlencode(p_min)}"
    url_max = f"{CADASTRAL_URL}?{urllib.parse.urlencode(p_max)}"

    with urllib.request.urlopen(urllib.request.Request(url_min, headers=headers)) as resp:
        d_min = json.loads(resp.read().decode())
        min_id = d_min['features'][0]['attributes']['OBJECTID']

    with urllib.request.urlopen(urllib.request.Request(url_max, headers=headers)) as resp:
        d_max = json.loads(resp.read().decode())
        max_id = d_max['features'][0]['attributes']['OBJECTID']

    print(f"{name.upper()} (CO_NO '{co_no}'): MIN={min_id}, MAX={max_id}, SPAN={max_id - min_id + 1:,}")
