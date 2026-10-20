import urllib.request
import json
import re

headers = {'User-Agent': 'Mozilla/5.0'}

BREVARD_CENTERS = [
    ("Palm Bay", 28.0345, -80.5887),
    ("Melbourne", 28.0836, -80.6081),
    ("Cocoa", 28.3861, -80.7431),
    ("Titusville", 28.6122, -80.8076),
    ("Rockledge", 28.3167, -80.7303),
    ("Merritt Island", 28.3181, -80.6660),
    ("West Melbourne", 28.0778, -80.6559),
    ("Indialantic", 28.0906, -80.5606),
    ("Cape Canaveral", 28.4058, -80.6048)
]

noise_keywords = [
    "pothole", "street light", "streetlight", "traffic light", "traffic signal",
    "sidewalk", "curb", "playground", "park", "drainage", "storm drain",
    "dead animal", "sign request", "street sign", "speeding", "traffic calming"
]

distress_indicators = [
    "trash", "debris", "overgrown", "grass", "blight", "dumping",
    "abandoned", "derelict", "unsafe", "damage", "squatter",
    "boarded", "roof", "hazard", "nuisance", "structure",
    "unpermitted", "violation", "code enforcement", "water heater",
    "code", "demolition", "vacant", "junk", "tall grass", "inoperable"
]

all_issues = {}

for name, lat, lng in BREVARD_CENTERS:
    for page in range(1, 4):
        url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=100&page={page}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
                issues = data.get('issues', [])
                if not issues:
                    break
                for issue in issues:
                    iid = issue.get('id')
                    if not iid or iid in all_issues:
                        continue
                    summary = str(issue.get('summary') or '').lower()
                    desc = str(issue.get('description') or '').lower()
                    cat = str((issue.get('request_type') or {}).get('title') or '').lower()
                    full_text = f"{summary} {desc} {cat}"
                    
                    if any(n in full_text for n in noise_keywords):
                        continue
                        
                    if any(d in full_text for d in distress_indicators):
                        all_issues[iid] = issue
        except Exception as e:
            print(f"Error {name}: {e}")
            break

print(f"\nTotal genuine property distress issues filtered across Brevard: {len(all_issues)}")
for i, (iid, iss) in enumerate(list(all_issues.items())[:10]):
    print(f"\n{i+1}. ID: {iid}")
    print(f"   Summary: {iss.get('summary')}")
    print(f"   Address: {iss.get('address')}")
    print(f"   Category: {(iss.get('request_type') or {}).get('title')}")
    print(f"   Status: {iss.get('status')}")
