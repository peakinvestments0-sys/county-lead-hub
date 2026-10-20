import os
import sys
import time
import urllib.request
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def download_file(url, target_path, county_name):
    print(f"[{county_name}] Starting download from: {url}")
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    t0 = time.time()
    
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req, timeout=180, context=ctx) as response, open(target_path, 'wb') as out_file:
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
                sys.stdout.write(f"\r[{county_name}] {downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB ({percent:.1f}%)")
            else:
                sys.stdout.write(f"\r[{county_name}] {downloaded / 1024 / 1024:.1f} MB downloaded")
            sys.stdout.flush()
            
    print(f"\n[{county_name}] Download complete in {time.time() - t0:.2f}s -> {target_path}")
    return target_path

if __name__ == "__main__":
    download_file(
        "https://vcpa.vcgov.org/files/database/CAMA_DATA_EXPORT.zip",
        r"data\FL\volusia\CAMA_DATA_EXPORT.zip",
        "Volusia"
    )
