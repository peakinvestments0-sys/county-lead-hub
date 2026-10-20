import urllib.request
import re
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def inspect_page(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=7, context=ctx).read().decode('utf-8', errors='ignore')
    links = re.findall(r'href=[\'"]([^\'"]+\.(?:zip|csv|txt|gz))[\'"]', html, re.I)
    return links[:10]

print("Pasco links:", inspect_page("https://downloads.pascopa.com/"))
print("Lake links:", inspect_page("https://c.lakecountyfl.gov/ftp/PA_office/data/"))
print("Volusia links:", inspect_page("https://vcpa.vcgov.org/download/database"))
