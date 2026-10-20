"""
Deep inspection of Brevard County GIS, Palm Bay GIS, and BCSO bookings.
"""
import urllib.request
import urllib.parse
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def inspect_brevard_gis():
    print("=== 1. Inspecting Brevard County GIS Server ===")
    url = "https://gis.brevardfl.gov/gissrv/rest/services?f=json"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            data = json.loads(r.read())
            services = data.get('services', [])
            folders = data.get('folders', [])
            print(f"Brevard GIS Root Services ({len(services)}), Folders ({len(folders)}): {folders}")
            for s in services:
                print(f"  Service: {s.get('name')} ({s.get('type')})")
            
            # Check folders
            for f in folders:
                f_url = f"https://gis.brevardfl.gov/gissrv/rest/services/{f}?f=json"
                try:
                    with urllib.request.urlopen(urllib.request.Request(f_url, headers=headers), timeout=10, context=ctx) as fr:
                        fdata = json.loads(fr.read())
                        f_services = fdata.get('services', [])
                        print(f"\nFolder [{f}] Services ({len(f_services)}):")
                        for fs in f_services:
                            name = fs.get('name', '')
                            if any(w in name.lower() for w in ['code', 'violation', 'permit', 'damage', 'unsafe', 'lien', 'inspect', 'case', 'building', 'flood', 'planning']):
                                print(f"  Match: {name} ({fs.get('type')})")
                except Exception as fe:
                    print(f"Folder {f} error: {fe}")
    except Exception as e:
        print("Brevard GIS Root error:", e)

def search_palmbay_melbourne():
    print("\n=== 2. Searching for Palm Bay & Melbourne GIS Services ===")
    queries = [
        "Palm Bay Open Data",
        "City of Palm Bay GIS",
        "Palm Bay Code Enforcement",
        "City of Melbourne Open Data",
        "Melbourne FL Code Violations",
        "Brevard County Building Permits"
    ]
    for q in queries:
        url = f"https://www.arcgis.com/sharing/rest/search?q={urllib.parse.quote(q)}&f=json&num=5"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
                res = json.loads(r.read())
                items = res.get('results', [])
                print(f"\nQuery '{q}': {len(items)} results")
                for it in items:
                    print(f"  - {it.get('title')} ({it.get('type')}): {it.get('url')}")
        except Exception as e:
            print(f"Search {q} error: {e}")

def check_bcso_arrests():
    print("\n=== 3. Checking Brevard County Sheriff (BCSO) Arrest / Booking Data ===")
    urls = [
        "https://www.brevardsheriff.com/home/booking-blotter/",
        "https://www.brevardsheriff.com/home/commands/jail/daily-inmate-roster/",
        "https://www.brevardsheriff.com/inmates/",
        "https://jail.brevardsheriff.com/"
    ]
    for u in urls:
        try:
            req = urllib.request.Request(u, headers=headers)
            with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
                print(f"BCSO URL: {u} -> Status {r.status}")
        except Exception as e:
            print(f"BCSO URL: {u} -> Error: {e}")

if __name__ == "__main__":
    inspect_brevard_gis()
    search_palmbay_melbourne()
    check_bcso_arrests()
