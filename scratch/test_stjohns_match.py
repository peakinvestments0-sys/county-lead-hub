import urllib.request
import urllib.parse
import json
import pandas as pd

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

params = {
    'where': "Compliance_Status LIKE '%NON-COMPLIANT%'",
    'outFields': '*',
    'resultRecordCount': '1000',
    'f': 'json'
}
url = f"https://services1.arcgis.com/t2yugAJW83eUIFui/arcgis/rest/services/STR_Properties/FeatureServer/0/query?{urllib.parse.urlencode(params)}"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req) as r:
    data = json.loads(r.read().decode())
    features = data.get('features', [])

df_master = pd.read_parquet("data/FL/st._johns/RP_PROPERTY_INFO.parquet")
pids = set(df_master["PARCEL_NUMBER"].astype(str).str.strip())
pids_clean = {p.lstrip('0'): p for p in pids}

matched = 0
for f in features:
    attrs = f.get('attributes', {})
    raw_pn = str(attrs.get('Parcel_Number') or '').strip()
    clean_pn = raw_pn.lstrip('0')
    if raw_pn in pids or clean_pn in pids_clean:
        matched += 1

print(f"Total non-compliant records: {len(features)}, Matched by parcel number: {matched}")
