import urllib.request
import urllib.parse
import json

headers = {'User-Agent': 'Mozilla/5.0'}

# 1. Inspect City of Cocoa Damage Assessment
url_cocoa = "https://services1.arcgis.com/Tex1uhbqnOZPx6qT/arcgis/rest/services/Damage_Assessment_Feature_Layer_-_Public_View/FeatureServer/0?f=json"
try:
    with urllib.request.urlopen(urllib.request.Request(url_cocoa, headers=headers), timeout=10) as r:
        meta = json.loads(r.read())
        print("Cocoa Damage Layer fields:", [f['name'] for f in meta.get('fields', [])][:15])
        
    count_url = "https://services1.arcgis.com/Tex1uhbqnOZPx6qT/arcgis/rest/services/Damage_Assessment_Feature_Layer_-_Public_View/FeatureServer/0/query?where=1=1&returnCountOnly=true&f=json"
    with urllib.request.urlopen(urllib.request.Request(count_url, headers=headers), timeout=10) as r:
        cres = json.loads(r.read())
        print("Cocoa Damage count:", cres.get('count'))
except Exception as e:
    print("Cocoa error:", e)

# 2. Inspect Helene SD Structures in Brevard
url_helene = "https://services7.arcgis.com/qkz4LIZAMHN41UKn/arcgis/rest/services/Helene_SD_Structures/FeatureServer/0?f=json"
try:
    with urllib.request.urlopen(urllib.request.Request(url_helene, headers=headers), timeout=10) as r:
        meta_h = json.loads(r.read())
        print("\nHelene SD Structures fields:", [f['name'] for f in meta_h.get('fields', [])][:15])
    
    count_h = "https://services7.arcgis.com/qkz4LIZAMHN41UKn/arcgis/rest/services/Helene_SD_Structures/FeatureServer/0/query?where=1=1&returnCountOnly=true&f=json"
    with urllib.request.urlopen(urllib.request.Request(count_h, headers=headers), timeout=10) as r:
        hres = json.loads(r.read())
        print("Helene SD count:", hres.get('count'))
except Exception as e:
    print("Helene error:", e)

# 3. Search for Brevard code violations on ArcGIS Online
print("\n=== Searching ArcGIS Online for Brevard distress ===")
for kw in ["Brevard Code", "Brevard Violation", "Brevard Damage", "Brevard Lien", "Brevard Unsafe"]:
    search_url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(kw)}&f=json&num=5"
    try:
        with urllib.request.urlopen(urllib.request.Request(search_url, headers=headers), timeout=10) as r:
            sdata = json.loads(r.read())
            results = sdata.get('results', [])
            print(f"Keyword '{kw}': {len(results)} results")
            for item in results:
                print(f"  - {item.get('title')} ({item.get('type')}): {item.get('url')}")
    except Exception as e:
        print(f"Error {kw}: {e}")
