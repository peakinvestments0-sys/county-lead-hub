import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

api_candidates = [
    # 1. Orlando / Orange (Already used in orlando_code_sync.py)
    ("Orlando Socrata Code Violations", "https://data.cityoforlando.net/resource/k6e8-nw6w.json?$limit=3"),
    # 2. St. Petersburg / Pinellas (Socrata)
    ("St. Pete Code Violations", "https://stat.stpete.org/resource/4636-iicq.json?$limit=3"),
    ("St. Pete Building Permits", "https://stat.stpete.org/resource/43v4-9r5m.json?$limit=3"),
    # 3. Tampa / Hillsborough (Socrata)
    ("Tampa Open Data (Socrata)", "https://data.tampa.gov/resource/y993-z2sm.json?$limit=3"),
    # 4. Miami-Dade (Socrata)
    ("Miami-Dade Code Compliance", "https://opendata.miamidade.gov/resource/a4gu-f9w3.json?$limit=3"),
    # 5. Sarasota County ArcGIS REST
    ("Sarasota County ArcGIS REST", "https://gis.scgov.net/arcgis/rest/services?f=json"),
    # 6. Pasco County ArcGIS REST
    ("Pasco County ArcGIS REST", "https://maps.pascocountyfl.net/arcgis/rest/services?f=json"),
    # 7. Manatee County ArcGIS REST
    ("Manatee County ArcGIS REST", "https://www.mymanatee.org/arcgis/rest/services?f=json"),
    # 8. Lake County ArcGIS REST
    ("Lake County ArcGIS REST", "https://gis.lakecountyfl.gov/arcgis/rest/services?f=json"),
    # 9. Pinellas County ArcGIS REST
    ("Pinellas County ArcGIS REST", "https://egis.pinellas.gov/arcgis/rest/services?f=json"),
]

for name, url in api_candidates:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=6, context=ctx)
        data = res.read()
        print(f"[OK 200] {name}: Accessible! (Size: {len(data)} bytes)")
    except Exception as e:
        print(f"[ERR] {name}: {e}")
