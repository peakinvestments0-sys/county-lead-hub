import urllib.request

url = "https://www.leepa.org/TaxRoll/ParcelData/LCPA_Parcel_Data_TXT.zip"
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'}

req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req) as resp:
        cl = resp.getheader('Content-Length')
        ct = resp.getheader('Content-Type')
        print(f"LCPA_Parcel_Data_TXT.zip: size={cl} bytes ({int(cl)/(1024*1024):.2f} MB), type={ct}")
except Exception as e:
    print("Error:", e)
