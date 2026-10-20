import os
import sys
import time
import urllib.request
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def download_file(url, target_path, label):
    print(f"[{label}] Starting download from: {url}")
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    t0 = time.time()
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=90, context=ctx) as response, open(target_path, 'wb') as out_file:
        total_size = int(response.headers.get('Content-Length', 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1MB
        
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                percent = downloaded / total_size * 100
                sys.stdout.write(f"\r[{label}] {downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB ({percent:.1f}%)")
            else:
                sys.stdout.write(f"\r[{label}] {downloaded / 1024 / 1024:.1f} MB downloaded")
            sys.stdout.flush()
            
    print(f"\n[{label}] Download complete in {time.time() - t0:.2f}s -> {target_path}")
    return target_path

if __name__ == "__main__":
    download_file(
        "https://c.lakecountyfl.gov/ftp/PA_office/data/Situs_Addr_090226.txt",
        r"data\FL\lake\Situs_Addr.txt",
        "Lake Situs"
    )
    download_file(
        "https://c.lakecountyfl.gov/ftp/PA_office/data/NALExtractPublic_090226.txt",
        r"data\FL\lake\NALExtractPublic.txt",
        "Lake NAL"
    )
    download_file(
        "https://c.lakecountyfl.gov/ftp/PA_office/data/Parcel_Values090226.txt",
        r"data\FL\lake\Parcel_Values.txt",
        "Lake Values"
    )
