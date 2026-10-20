import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# 1. Test SeeClickFix API for St. Petersburg
try:
    url_scf = "https://seeclickfix.com/api/v2/issues?place_url=st-petersburg&per_page=5"
    req_scf = urllib.request.Request(url_scf, headers={'User-Agent': 'Mozilla/5.0 PinellasLeadHub/1.0'})
    res_scf = urllib.request.urlopen(req_scf, timeout=8, context=ctx)
    data_scf = json.loads(res_scf.read())
    issues = data_scf.get('issues', [])
    print(f"SeeClickFix St. Pete Success! Found {len(issues)} issues:")
    for iss in issues[:3]:
        print(f"  - [{iss.get('id')}] {iss.get('summary')}: {iss.get('address')} | Status: {iss.get('status')} | Date: {iss.get('created_at')}")
except Exception as e:
    print("SeeClickFix error:", e)

# 2. Test St. Pete Geohub API
try:
    url_gh = "https://geohub-stpete.opendata.arcgis.com/api/v3/datasets?q=code&page[size]=5"
    req_gh = urllib.request.Request(url_gh, headers={'User-Agent': 'Mozilla/5.0'})
    res_gh = urllib.request.urlopen(req_gh, timeout=8, context=ctx)
    data_gh = json.loads(res_gh.read())
    items = data_gh.get('data', [])
    print(f"\nGeohub St. Pete Success! Found {len(items)} datasets:")
    for it in items:
        attrs = it.get('attributes', {})
        print(f"  - {attrs.get('name')}: {attrs.get('url')}")
except Exception as e:
    print("Geohub error:", e)
