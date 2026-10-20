import urllib.request
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

urls = [
    ("Lake Situs", "https://c.lakecountyfl.gov/ftp/PA_office/data/Situs_Addr_090226.txt"),
    ("Lake NAL", "https://c.lakecountyfl.gov/ftp/PA_office/data/NALExtractPublic_090226.txt"),
    ("Lake Values", "https://c.lakecountyfl.gov/ftp/PA_office/data/Parcel_Values090226.txt"),
]

for name, url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=5, context=ctx)
        print(f"[{res.status}] {name}: Size = {res.headers.get('Content-Length')}")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
