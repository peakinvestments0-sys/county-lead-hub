import urllib.request
import urllib.parse
import json

headers = {'User-Agent': 'Mozilla/5.0'}

places = [
    "Palm Bay, FL",
    "Melbourne, FL",
    "Cocoa, FL",
    "Titusville, FL",
    "Rockledge, FL",
    "Merritt Island, FL",
    "Brevard County, FL",
    "Indian Harbour Beach, FL",
    "Satellite Beach, FL",
    "Cocoa Beach, FL"
]

print("=== Checking SeeClickFix Places for Brevard County ===")
for p in places:
    url = f"https://seeclickfix.com/api/v2/places?address={urllib.parse.quote(p)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
            data = json.loads(r.read())
            plist = data.get('places', [])
            print(f"\n{p}: {len(plist)} places found")
            for item in plist[:3]:
                print(f"  - ID: {item.get('id')}, Name: {item.get('name')}, URL: {item.get('url_name')}")
    except Exception as e:
        print(f"Error {p}: {e}")
