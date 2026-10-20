import urllib.request
import urllib.parse
import json
import pandas as pd

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

params = {
    'where': "Compliance_Status LIKE '%NON-COMPLIANT%'",
    'outFields': '*',
    'resultRecordCount': '5',
    'f': 'json'
}
url = f"https://services1.arcgis.com/t2yugAJW83eUIFui/arcgis/rest/services/STR_Properties/FeatureServer/0/query?{urllib.parse.urlencode(params)}"
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req) as r:
    data = json.loads(r.read().decode())
    features = data.get('features', [])
    for f in features:
        attrs = f.get('attributes', {})
        print("Record:", attrs.get('Parcel_Number'), attrs.get('Address'), attrs.get('Compliance_Status'), attrs.get('Comments'))

# Check master parquet parcel IDs
df_master = pd.read_parquet("data/FL/st._johns/RP_PROPERTY_INFO.parquet", columns=["PARCEL_NUMBER", "SITE_ADDRESS"])
print("Sample Master Parcel Numbers:", df_master["PARCEL_NUMBER"].head(5).tolist())
