import time
import zipfile
import openpyxl
import pandas as pd

t0 = time.time()
print("Opening Pasco parcel_summary.zip...")
with zipfile.ZipFile(r"data\FL\pasco\parcel_summary.zip") as z:
    with z.open("parcel_summary.xlsx") as f:
        wb = openpyxl.load_workbook(f, read_only=True)
        sheet = wb.active
        rows = sheet.iter_rows(values_only=True)
        headers = next(rows)
        data = []
        for i, row in enumerate(rows):
            data.append(row)
            if i % 50000 == 0 and i > 0:
                print(f"Read {i:,} rows in {time.time() - t0:.1f}s...")
        print(f"Total rows read: {len(data):,} in {time.time() - t0:.1f}s")
