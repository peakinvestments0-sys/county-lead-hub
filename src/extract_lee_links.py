import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0'}
urls = [
    "https://leegis.leegov.com/datasets/a69c335ad6e54fc0872f7ed47208f11e_0/explore",
    "https://www.leepa.org/DataServices/DataServices.aspx"
]

for url in urls:
    print("=" * 60)
    print("Inspecting:", url)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            
        links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', html)
        for l in links:
            if any(k in l.lower() for k in ['zip', 'csv', 'download', 'ftp', 'data', 'roll']):
                print("  Link:", l)
    except Exception as e:
        print("  Error:", e)
