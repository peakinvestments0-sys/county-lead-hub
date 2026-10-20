import urllib.request
import re
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

candidates = [
    ("Flagler GIS", "https://flaglerpa.com/gis/"),
    ("Indian River", "https://ircpa.org/site-links/downloads/"),
    ("Citrus", "https://www.citruspa.org/_dnn/Downloads"),
    ("St Johns Forms", "https://www.sjcpa.gov/forms/"),
    ("St Lucie Data", "https://www.paslc.gov/231/Data-Requests"),
]

for name, url in candidates:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=5, context=ctx).read().decode('utf-8', errors='ignore')
        zips = re.findall(r'href=[\'"]([^\'"]+\.(?:zip|csv|txt))[\'"]', html, re.I)
        print(f"{name}: Accessible! Found {len(zips)} file links: {zips[:4]}")
    except Exception as e:
        print(f"{name}: {e}")
