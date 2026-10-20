import urllib.request
import json

headers = {'User-Agent': 'Mozilla/5.0'}
item_id = 'a69c335ad6e54fc0872f7ed47208f11e'
url = f"https://www.arcgis.com/sharing/rest/content/items/{item_id}?f=json"

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read().decode('utf-8'))
        print("Item Title:", d.get('title'))
        print("Type:", d.get('type'))
        print("URL:", d.get('url'))
        print("Owner:", d.get('owner'))
        print("Description:", d.get('snippet'))
        
        # Check layer details
        svc_url = d.get('url')
        if svc_url:
            req_s = urllib.request.Request(f"{svc_url}?f=json", headers=headers)
            with urllib.request.urlopen(req_s) as rs:
                ds = json.loads(rs.read().decode('utf-8'))
                layers = ds.get('layers', [])
                print(f"Service has {len(layers)} layers:")
                for l in layers:
                    print(f"  Layer {l.get('id')}: {l.get('name')}")
except Exception as e:
    print("Error:", e)
