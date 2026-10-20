import urllib.request
import json
import ssl
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {'User-Agent': 'Mozilla/5.0'}

base_url = "https://gis.brevardfl.gov/gissrv/rest/services/Base_Map/Parcel_New_WKID2881/MapServer/5/query"

# Test batch fetch
params = {
    'where': 'OBJECTID >= 1 AND OBJECTID < 2001',
    'outFields': 'OBJECTID,TaxAcct,PARCEL_ID,LEGAL_DESC,USE_CODE_DESCRIPTION,BLDG_VALUE,LAND_VALUE,LIV_AREA,STREET_NUMBER,STREET_DIRECTION_PREFIX,STREET_NAME,STREET_TYPE,CITY,ZIP_CODE,OWNER_NAME1,OWNER_STREET_NAME,OWNER_ADDRESS2,OWNER_CITY,OWNER_STATE,OWNER_ZIP5',
    'returnGeometry': 'false',
    'resultRecordCount': '2000',
    'f': 'json'
}
url = f"{base_url}?{urllib.parse.urlencode(params)}"
t0 = time.time()
with urllib.request.urlopen(urllib.request.Request(url, headers=headers), context=ctx) as r:
    data = json.loads(r.read())
    feats = data.get('features', [])
    print(f"Fetched {len(feats)} parcels in {time.time()-t0:.2f}s")
