import zipfile
import os

zip_path = os.path.abspath("data/FL/lee/LCPA_Parcel_Data_TXT.zip")
print(f"Zip size: {os.path.getsize(zip_path) / (1024*1024):.2f} MB")

with zipfile.ZipFile(zip_path, 'r') as z:
    infolist = z.infolist()
    print(f"Found {len(infolist)} files in zip:")
    for info in infolist:
        print(f"  {info.filename} ({info.file_size / (1024*1024):.2f} MB uncompressed)")
        
    # Inspect first 3 lines of the largest text file
    first_txt = [i.filename for i in infolist if i.filename.endswith('.txt') or i.filename.endswith('.csv')][0]
    print(f"\nSample from {first_txt}:")
    with z.open(first_txt) as f:
        for _ in range(5):
            line = f.readline().decode('latin-1').strip()
            print(" ", line[:120])
