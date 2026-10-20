import urllib.request
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# 1. Check stat.stpete.org discovery catalog
url = 'http://api.us.socrata.com/api/catalog/v1?domains=stat.stpete.org&search_context=stat.stpete.org&limit=50'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    res = urllib.request.urlopen(req, timeout=10, context=ctx)
    data = json.loads(res.read())
    results = data.get('results', [])
    print(f"Found {len(results)} datasets on stat.stpete.org:\n")
    for r in results:
        res_info = r.get('resource', {})
        d_id = res_info.get('id')
        name = res_info.get('name')
        desc = (res_info.get('description') or '')[:75].replace('\n', ' ')
        updated = res_info.get('updatedAt', '')[:10]
        print(f"[{d_id}] {name:<35} (Updated: {updated}) | {desc}")
except Exception as e:
    print('Error checking stat.stpete.org:', e)
