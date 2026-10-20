import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {'User-Agent': 'Mozilla/5.0'}

# Test 1: Socrata catalog https
try:
    url = 'https://api.us.socrata.com/api/catalog/v1?domains=stat.stpete.org&limit=30'
    res = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10, context=ctx)
    data = json.loads(res.read())
    print("Catalog HTTPS Success! Results:", len(data.get('results', [])))
    for r in data.get('results', [])[:10]:
        print(" ", r.get('resource', {}).get('id'), "|", r.get('resource', {}).get('name'))
except Exception as e:
    print("Catalog HTTPS error:", e)

# Test 2: stat.stpete.org data.json
try:
    url2 = 'https://stat.stpete.org/data.json'
    res2 = urllib.request.urlopen(urllib.request.Request(url2, headers=headers), timeout=10, context=ctx)
    data2 = json.loads(res2.read())
    print("data.json Success! Datasets:", len(data2.get('dataset', [])))
    for d in data2.get('dataset', [])[:10]:
        print(" ", d.get('identifier'), "|", d.get('title'))
except Exception as e:
    print("data.json error:", e)

# Test 3: St. Pete ArcGIS Hub
try:
    url3 = 'https://gis.stpete.org/arcgis/rest/services?f=json'
    res3 = urllib.request.urlopen(urllib.request.Request(url3, headers=headers), timeout=10, context=ctx)
    data3 = json.loads(res3.read())
    print("St. Pete ArcGIS REST Success! Folders:", data3.get('folders'))
    print("Services:", [s.get('name') for s in data3.get('services', [])[:10]])
except Exception as e:
    print("St. Pete ArcGIS error:", e)

# Test 4: Pinellas County GIS
try:
    url4 = 'https://egis.pinellas.gov/arcgis/rest/services?f=json'
    res4 = urllib.request.urlopen(urllib.request.Request(url4, headers=headers), timeout=10, context=ctx)
    data4 = json.loads(res4.read())
    print("Pinellas egis Success! Folders:", data4.get('folders'))
except Exception as e:
    print("Pinellas egis error:", e)
