import urllib.request
import json

base = "https://services.arcgis.com/f5HgUpxURgEzTccH/arcgis/rest/services"

services_to_check = [
    "SubstantialDamage_Parcel_Accela",
    "Substantial_Damage_STR_view",
    "WebEOC_Damage_Assessment_Property_Evaluation",
    "SD_Parcels_for_Accela_view",
    "SouthPasadenaPermits_21661b16",
    "AccelaDataTesting"
]

headers = {'User-Agent': 'Mozilla/5.0'}

for s in services_to_check:
    info_url = f"{base}/{s}/FeatureServer/0?f=json"
    count_url = f"{base}/{s}/FeatureServer/0/query?where=1%3D1&returnCountOnly=true&f=json"
    try:
        req = urllib.request.Request(count_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            cnt_data = json.loads(resp.read().decode())
            cnt = cnt_data.get('count', 'N/A')
            print(f"Service: {s:45} | Count: {cnt}")
            if cnt != 'N/A' and cnt > 0:
                # get sample
                sample_url = f"{base}/{s}/FeatureServer/0/query?where=1%3D1&resultRecordCount=1&outFields=*&f=json"
                req2 = urllib.request.Request(sample_url, headers=headers)
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    s_data = json.loads(resp2.read().decode())
                    feats = s_data.get('features', [])
                    if feats:
                        print(f"   Fields: {list(feats[0].get('attributes', {}).keys())[:10]}")
                        print(f"   Sample: {feats[0].get('attributes')}")
    except Exception as e:
        print(f"Service: {s:45} | Error: {e}")
