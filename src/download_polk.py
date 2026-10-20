import urllib.request
import zipfile
import os

target_dir = os.path.abspath("data/FL/polk")
os.makedirs(target_dir, exist_ok=True)

files = ["ftp_parcel.zip", "ftp_owner.zip", "ftp_site.zip", "ftp_bldg.zip"]
base_url = "https://www.polkflpa.gov/FTPPage/downloader.ashx?filename={}&dir=%5CAppraisalData%5C"

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0'}

for f in files:
    zip_path = os.path.join(target_dir, f)
    url = base_url.format(f)
    print(f"Downloading {f}...", flush=True)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp, open(zip_path, 'wb') as out_f:
        out_f.write(resp.read())
    print(f"Downloaded {f} ({os.path.getsize(zip_path)} bytes). Extracting...", flush=True)
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(target_dir)
        print(f"Extracted: {z.namelist()}", flush=True)

print("All Polk files downloaded and extracted successfully!", flush=True)
