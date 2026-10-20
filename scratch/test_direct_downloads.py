import urllib.request
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

urls = [
    ("Alachua S3", "https://s3.amazonaws.com/acpa.cama/ACPA_CAMAData.zip"),
    ("Pasco Downloads", "https://downloads.pascopa.com/"),
    ("Volusia Downloads", "https://vcpa.vcgov.org/download/database"),
    ("Lake FTP", "https://c.lakecountyfl.gov/ftp/PA_office/data/"),
    ("Hillsborough Downloads", "https://downloads.hcpafl.org/"),
    ("Miami-Dade BBS", "https://bbs.miamidadepa.gov/")
]

for name, url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=5, context=ctx)
        print(f"[{res.status}] {name}: Accessible! (Content-Type: {res.headers.get('Content-Type')}, Size: {res.headers.get('Content-Length')})")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
