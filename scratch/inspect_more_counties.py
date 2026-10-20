import urllib.request
import re
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def inspect_page(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=7, context=ctx).read().decode('utf-8', errors='ignore')
        links = re.findall(r'href=[\'"]([^\'"]+\.(?:zip|csv|txt|gz))[\'"]', html, re.I)
        return links[:8]
    except Exception as e:
        return [f"ERR: {e}"]

print("Hillsborough links:", inspect_page("https://downloads.hcpafl.org/"))
print("Sarasota links:", inspect_page("https://www.sarasotapropertyappraiser.gov/downloads/download-data"))
print("Osceola links:", inspect_page("https://www.property-appraiser.org/data/"))
print("Manatee links:", inspect_page("https://www.manateepao.gov/tax-roll-data/"))
