import urllib.request
import urllib.parse
import json
import re
import pandas as pd

def norm_addr(a):
    if not a: return ""
    a = str(a).upper().strip()
    a = re.sub(r'[^\w\s]', ' ', a)
    a = re.sub(r'\s+', ' ', a).strip()
    replacements = {
        ' STREET': ' ST', ' AVENUE': ' AVE', ' ROAD': ' RD', ' BOULEVARD': ' BLVD',
        ' DRIVE': ' DR', ' COURT': ' CT', ' LANE': ' LN', ' CIRCLE': ' CIR',
        ' NORTH': ' N', ' SOUTH': ' S', ' EAST': ' E', ' WEST': ' W',
        ' PARKWAY': ' PKWY', ' HIGHWAY': ' HWY', ' PLACE': ' PL', ' TERRACE': ' TER',
        ' TRAIL': ' TRL', ' WAY': ' WAY'
    }
    for k, v in replacements.items():
        a = a.replace(k, v)
    return a.strip()

def clean_damage_addr(raw):
    if not raw: return ""
    # Strip city, zip, state
    clean = re.sub(r',\s*FL\b.*$', '', raw, flags=re.IGNORECASE)
    clean = re.sub(r'\b3\d{4}\b', '', clean)
    clean = clean.split(',')[0].strip()
    return clean

p = {
    'where': "Degree_of IN ('Destroyed', 'Major', 'Minor', 'Affected')",
    'outFields': 'FID,Address,Parcel_ID,Degree_of,Event_Name,Add_photos,Descriptio',
    'resultRecordCount': '2000',
    'f': 'json'
}
url = f"https://services2.arcgis.com/x5zvhhxfUuRDntRe/arcgis/rest/services/2024_HurricanesMiltonAndHeleneDamageAssessementData/FeatureServer/0/query?{urllib.parse.urlencode(p)}"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as r:
    features = json.loads(r.read().decode()).get('features', [])

df_master = pd.read_parquet("data/FL/hernando/RP_PROPERTY_INFO.parquet")
df_master["NORM_ADDR"] = df_master["SITE_ADDRESS"].apply(norm_addr)
addr_set = set(df_master["NORM_ADDR"])

matched = 0
for f in features:
    raw_addr = f.get('attributes', {}).get('Address')
    c_addr = clean_damage_addr(raw_addr)
    na = norm_addr(c_addr)
    if na in addr_set:
        matched += 1

print(f"Address matches: {matched} / {len(features)} ({matched/len(features)*100:.1f}%)")
