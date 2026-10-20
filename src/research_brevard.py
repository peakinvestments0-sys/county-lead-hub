"""
Comprehensive research script for Brevard County, FL.
"""
import urllib.request
import urllib.parse
import json

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def check_statewide_cadastral():
    print("=== 1. Checking Statewide Cadastral for Brevard (CO_NO = '15') ===")
    count_url = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query?where=CO_NO=%2715%27&returnCountOnly=true&f=json"
    req = urllib.request.Request(count_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read())
            print(f"Statewide Cadastral Brevard parcel count: {res.get('count')}")
    except Exception as e:
        print("Cadastral count error:", e)

    # Check min/max OBJECTID
    stats_url = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query?where=CO_NO=%2715%27&outStatistics=[{%22statisticType%22:%22min%22,%22onStatisticField%22:%22OBJECTID%22,%22outStatisticFieldName%22:%22min_id%22},{%22statisticType%22:%22max%22,%22onStatisticField%22:%22OBJECTID%22,%22outStatisticFieldName%22:%22max_id%22}]&f=json"
    try:
        with urllib.request.urlopen(urllib.request.Request(stats_url, headers=headers), timeout=10) as r:
            sres = json.loads(r.read())
            print("Cadastral Brevard ID range:", sres.get('features', [{}])[0].get('attributes'))
    except Exception as e:
        print("Stats error:", e)

    # Check sample
    sample_url = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query?where=CO_NO=%2715%27&outFields=PARCEL_ID,PHY_ADDR1,PHY_CITY,PHY_ZIPCD,OWN_NAME,OWN_ADDR1,OWN_CITY,OWN_STATE,OWN_ZIPCD,JV,AV_SD,TV_SD,TOT_LVG_AR,ACT_YR_BLT,DOR_UC,S_LEGAL&resultRecordCount=1&returnGeometry=false&f=json"
    try:
        with urllib.request.urlopen(urllib.request.Request(sample_url, headers=headers), timeout=10) as r:
            s = json.loads(r.read())
            for f in s.get('features', []):
                print("Sample Brevard Cadastral Record:", f.get('attributes'))
    except Exception as e:
        print("Sample error:", e)

def search_arcgis_brevard():
    print("\n=== 2. Searching ArcGIS Online for Brevard Code Enforcement & Distress ===")
    queries = [
        "Brevard County Code Enforcement",
        "Palm Bay Code Enforcement",
        "Melbourne Code Enforcement",
        "Brevard County Violations",
        "Palm Bay Code Violations",
        "Cocoa Code Enforcement",
        "Titusville Code Enforcement",
        "Brevard County Parcels",
        "Brevard Damage Assessment"
    ]
    for q in queries:
        url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(q)}&f=json&num=5"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
                data = json.loads(r.read())
                results = data.get('results', [])
                print(f"\nQuery '{q}': {len(results)} items")
                for item in results:
                    u = item.get('url') or item.get('item', '')
                    print(f"  - {item.get('title')} ({item.get('type')}): {u}")
        except Exception as e:
            print(f"Error {q}: {e}")

def check_brevard_seeclickfix():
    print("\n=== 3. Testing SeeClickFix for Brevard Cities ===")
    places = [
        ("Palm Bay", 28.0345, -80.5887),
        ("Melbourne", 28.0836, -80.6081),
        ("Cocoa", 28.3861, -80.7431),
        ("Titusville", 28.6122, -80.8076),
        ("Merritt Island", 28.3181, -80.6660),
        ("Rockledge", 28.3167, -80.7303)
    ]
    for name, lat, lng in places:
        url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=20"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
                data = json.loads(r.read())
                issues = data.get('issues', [])
                print(f"{name} SeeClickFix: {len(issues)} issues returned")
                for i in issues[:2]:
                    print(f"   - {i.get('summary')} | {i.get('address')}")
        except Exception as e:
            print(f"{name} SCF error: {e}")

if __name__ == "__main__":
    check_statewide_cadastral()
    search_arcgis_brevard()
    check_brevard_seeclickfix()
