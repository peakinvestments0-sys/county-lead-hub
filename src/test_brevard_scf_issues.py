import urllib.request
import json

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

places = [
    ("Palm Bay", "palm-bay"),
    ("Melbourne", "melbourne"),
    ("Brevard County", "brevard-county"),
    ("Cocoa", "cocoa"),
    ("Titusville", "titusville"),
    ("Rockledge", "rockledge"),
    ("Merritt Island", "merritt-island"),
    ("Indian Harbour Beach", "indian-harbour-beach")
]

for name, url_slug in places:
    url = f"https://seeclickfix.com/api/v2/issues?place_url={url_slug}&per_page=50"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            issues = data.get('issues', [])
            print(f"\n{name} ({url_slug}): {len(issues)} issues returned")
            categories = set(i.get('summary') for i in issues if i.get('summary'))
            for c in list(categories)[:5]:
                print(f"  - {c}")
    except Exception as e:
        print(f"Error {name}: {e}")
