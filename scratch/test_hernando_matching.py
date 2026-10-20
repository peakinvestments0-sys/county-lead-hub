import urllib.request
import urllib.parse
import json
import pandas as pd

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

p = {
    'where': "Degree_of IN ('Destroyed', 'Major', 'Minor', 'Affected')",
    'outFields': 'FID,Address,Parcel_ID,Degree_of,Event_Name,Add_photos,Descriptio,Property_U',
    'resultRecordCount': '2000',
    'f': 'json'
}
url = f"https://services2.arcgis.com/x5zvhhxfUuRDntRe/arcgis/rest/services/2024_HurricanesMiltonAndHeleneDamageAssessementData/FeatureServer/0/query?{urllib.parse.urlencode(p)}"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req) as r:
    data = json.loads(r.read().decode())
    features = data.get('features', [])

print(f"Total damage features: {len(features)}")
df_master = pd.read_parquet("data/FL/hernando/RP_PROPERTY_INFO.parquet")
pids = set(df_master["PARCEL_NUMBER"].astype(str).str.strip())
print(f"Master parcel count: {len(df_master):,}")
print("Sample master PIDs:", list(pids)[:5])

matched = 0
for f in features:
    attrs = f.get('attributes', {})
    pid = str(attrs.get('Parcel_ID') or '').strip()
    if pid in pids:
        matched += 1

print(f"Direct PID matches: {matched} / {len(features)} ({matched/len(features)*100:.1f}%)")
