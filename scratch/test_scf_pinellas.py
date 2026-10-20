import urllib.request
import json

headers = {'User-Agent': 'Mozilla/5.0'}

# 1. Test Bounding Box
bb_url = 'https://seeclickfix.com/api/v2/issues?min_lat=27.65&max_lat=28.17&min_lng=-82.88&max_lng=-82.55&per_page=10'
print("--- 1. Testing Bounding Box ---")
try:
    req = urllib.request.Request(bb_url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
        issues = data.get('issues', [])
        print(f"Bounding box issues: {len(issues)}")
        print(f"Pagination: {data.get('pagination')}")
        for i in issues[:3]:
            print(f"  [{i.get('status')}] {i.get('summary')} | {i.get('address')} | {i.get('created_at')}")
except Exception as e:
    print(f"Bounding box failed: {e}")

# 2. Test the 4 Pinellas municipalities
print("\n--- 2. Testing Pinellas Municipalities ---")
municipalities = ['st-petersburg', 'clearwater', 'largo', 'pinellas-park']
for city in municipalities:
    url = f"https://seeclickfix.com/api/v2/issues?place_url={city}&per_page=100"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            issues = data.get('issues', [])
            pag = data.get('pagination', {})
            print(f"City: {city} -> {len(issues)} issues in batch 1 | Total pages/entries: {pag}")
            # Count categories or keywords
            neglect_matches = []
            for item in issues:
                text = f"{item.get('summary','')} {item.get('description','')} {item.get('request_type',{}).get('title','')}".lower()
                if any(w in text for w in ['trash', 'dump', 'grass', 'weed', 'board', 'overgrown', 'debris', 'derelict', 'fence', 'roof', 'damage', 'tree', 'abandon', 'code', 'neglect', 'unfit', 'blight']):
                    neglect_matches.append(item)
            print(f"  Neglect/Distress candidates in first 100: {len(neglect_matches)}")
            if neglect_matches:
                sample = neglect_matches[0]
                print(f"  Sample neglect lead: [{sample.get('status')}] {sample.get('summary')} | {sample.get('address')} | lat:{sample.get('lat')}, lng:{sample.get('lng')}")
    except Exception as e:
        print(f"City {city} failed: {e}")
