import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {'User-Agent': 'Mozilla/5.0'}

count_url = "https://gis.brevardfl.gov/gissrv/rest/services/Base_Map/Parcel_New_WKID2881/MapServer/5/query?where=1=1&returnCountOnly=true&f=json"
with urllib.request.urlopen(urllib.request.Request(count_url, headers=headers), context=ctx, timeout=10) as r:
    data = json.loads(r.read())
    print("BCPAO Live Parcels count:", data.get('count'))

sample_url = "https://gis.brevardfl.gov/gissrv/rest/services/Base_Map/Parcel_New_WKID2881/MapServer/5/query?where=1=1&outFields=*&resultRecordCount=2&f=json"
with urllib.request.urlopen(urllib.request.Request(sample_url, headers=headers), context=ctx, timeout=10) as r:
    sdata = json.loads(r.read())
    for f in sdata.get('features', []):
        print("\nSample Parcel:", f.get('attributes'))
