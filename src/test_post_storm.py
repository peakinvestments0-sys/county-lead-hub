import urllib.request
import json

url = "https://services2.arcgis.com/zfDSLldsAGQfwUz9/arcgis/rest/services/service_e7f9a2e6f65b418189acf291bd87bc98/FeatureServer/0?f=json"
headers = {'User-Agent': 'Mozilla/5.0'}

try:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
        meta = json.loads(r.read())
        print("Post Storm Survey fields:", [f['name'] for f in meta.get('fields', [])])
        
    count_url = "https://services2.arcgis.com/zfDSLldsAGQfwUz9/arcgis/rest/services/service_e7f9a2e6f65b418189acf291bd87bc98/FeatureServer/0/query?where=1=1&returnCountOnly=true&f=json"
    with urllib.request.urlopen(urllib.request.Request(count_url, headers=headers), timeout=10) as r:
        res = json.loads(r.read())
        print("Post Storm Survey count:", res.get('count'))
except Exception as e:
    print("Error:", e)
