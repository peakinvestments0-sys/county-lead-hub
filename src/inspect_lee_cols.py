import zipfile
import os

zip_path = os.path.abspath("data/FL/lee/LCPA_Parcel_Data_TXT.zip")
with zipfile.ZipFile(zip_path, 'r') as z:
    with z.open("Field List.txt") as f:
        print("=== Field List.txt ===")
        print(f.read().decode('latin-1'))
        
    with z.open("LCPA2609.txt") as f:
        header = f.readline().decode('latin-1').strip().split('\t')
        row1 = f.readline().decode('latin-1').strip().split('\t')
        print(f"\nTotal columns in LCPA2609.txt: {len(header)}")
        for i, (col, val) in enumerate(zip(header, row1)):
            print(f"  {i}: {col} = {val}")
