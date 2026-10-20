import urllib.request
import urllib.parse
import json
import time

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

print("Testing Flagler Palm Coast SeeClickFix with 1.0s delay...")
time.sleep(2.0)
url = "https://seeclickfix.com/api/v2/issues?lat=29.5845&lng=-81.2079&zoom=11&per_page=50"
req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())
        issues = data.get("issues", [])
        print(f"Palm Coast SCF issues retrieved: {len(issues)}")
        for i in issues[:5]:
            print(f"  #{i.get('id')} - {i.get('summary')} | {i.get('address')}")
except Exception as e:
    print(f"Error: {e}")
