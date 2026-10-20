import urllib.request
import json

url = "https://seeclickfix.com/api/v2/issues?place_url=st-petersburg&per_page=30"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 PinellasLeadHub/1.0'})
res = urllib.request.urlopen(req, timeout=10)
d = json.loads(res.read())

print(f"Total issues on St. Pete SeeClickFix: {len(d.get('issues', []))}\n")
for iss in d.get('issues', [])[:15]:
    status = iss.get('status')
    summary = iss.get('summary')
    address = iss.get('address')
    desc = (iss.get('description') or '')[:50].replace('\n', ' ')
    print(f"[{status:<8}] {summary:<30} | {address:<40} | {desc}")
