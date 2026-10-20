import urllib.request
import json

url = "https://services2.arcgis.com/zfDSLldsAGQfwUz9/arcgis/rest/services/service_e7f9a2e6f65b418189acf291bd87bc98/FeatureServer/0/query?where=1=1&outFields=*&resultRecordCount=3&f=json"
headers = {'User-Agent': 'Mozilla/5.0'}

with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as r:
    data = json.loads(r.read())
    for f in data.get('features', []):
        print("Sample:", f.get('attributes'))
