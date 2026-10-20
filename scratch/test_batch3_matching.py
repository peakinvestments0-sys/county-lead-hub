import urllib.request
import json
import time
import re
import pandas as pd

headers = {'User-Agent': 'FloridaLeadHub/2.0'}

# Test Flagler
flagler_centers = [
    ("Palm Coast", 29.5845, -81.2079),
    ("Flagler Beach", 29.4744, -81.1270),
    ("Bunnell", 29.4678, -81.2581)
]

for name, lat, lng in flagler_centers:
    time.sleep(1.0)
    url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=20"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read().decode())
            print(f"[{name}] {len(data.get('issues', []))} issues")
            for iss in data.get('issues', []):
                print(f"  ID={iss.get('id')} | addr={iss.get('address')} | sum={iss.get('summary')}")
    except Exception as e:
        print(f"[{name}] error: {e}")
