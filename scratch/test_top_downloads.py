import urllib.request
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

urls = [
    ("Brevard", "https://www.bcpao.us/Docs/PublicDownload/PropData/WebData.zip"),
    ("Charlotte", "https://www.ccappraiser.com/downloads/charlotte.zip"),
    ("Sarasota", "https://www.sarasotapropertyappraiser.gov/downloads/SCPA_Parcels_Sales_CSV.zip"),
    ("Manatee", "https://www.manateepao.gov/DATA/PUBLIC_NAL.CSV"),
    ("Volusia", "https://vcpa.vcgov.org/files/database/CAMA_DATA_EXPORT.zip"),
    ("Pasco", "https://ftp01.pascopa.com/real_estate/parcel_summary.zip")
]

for name, url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        res = urllib.request.urlopen(req, timeout=5, context=ctx)
        print(f"[{res.status}] {name}: Accessible! (Size: {res.headers.get('Content-Length')}, Type: {res.headers.get('Content-Type')})")
    except Exception as e:
        print(f"[FAIL] {name}: {e}")
