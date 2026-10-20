import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {'User-Agent': 'Mozilla/5.0'}

for folder in ['Accela', 'Emergency_Management', 'Hosted']:
    url = f"https://gis.brevardfl.gov/gissrv/rest/services/{folder}?f=json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), context=ctx) as r:
            data = json.loads(r.read())
            print(f"=== Folder: {folder} ===")
            for s in data.get('services', []):
                print(f"  {s.get('name')} ({s.get('type')})")
    except Exception as e:
        print(f"Error {folder}: {e}")
