import urllib.request
import urllib.parse
import json

base = "https://services.arcgis.com/f5HgUpxURgEzTccH/arcgis/rest/services/SD_Parcels_for_Accela_view/FeatureServer/0/query"
headers = {'User-Agent': 'Mozilla/5.0'}

for where_clause in ['1=1', 'DeterminedSD=1', 'PotentialSD=1', 'DamagePct > 0', 'DamagePct >= 50']:
    encoded = urllib.parse.quote(where_clause)
    url = f"{base}?where={encoded}&returnCountOnly=true&f=json"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        d = json.loads(resp.read().decode())
        cnt = d.get("count")
        print(f"{where_clause:20} -> {cnt} parcels")
