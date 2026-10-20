import urllib.request
import re
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
headers = {'User-Agent': 'Mozilla/5.0'}

url = "https://www.brevardsheriff.com/"
try:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), context=ctx, timeout=10) as r:
        html = r.read().decode('utf-8', errors='ignore')
        # Find jail or inmate or booking links
        links = re.findall(r'href=[\'"]([^\'"]*(?:jail|inmate|booking|arrest)[^\'"]*)[\'"]', html, re.I)
        print("BCSO Jail links found on homepage:")
        for l in set(links):
            print("  -", l)
except Exception as e:
    print("Error:", e)
