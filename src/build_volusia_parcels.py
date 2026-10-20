"""
Build unified Master Parcel parquet for Volusia County, FL.
Pulls complete 313,739 parcel records directly from Volusia County Open Data GIS:
https://maps5.vcgov.org/arcgis/rest/services/Open_Data/Open_Data_3/FeatureServer/34
"""

import os
import sys
import time
import json
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

# Reconfigure stdout/stderr to utf-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VOLUSIA_DIR = os.path.join(BASE_DIR, "data", "FL", "volusia")
OUT_PARQUET = os.path.join(VOLUSIA_DIR, "RP_PROPERTY_INFO.parquet")

FEATURE_URL = "https://maps5.vcgov.org/arcgis/rest/services/Open_Data/Open_Data_3/FeatureServer/34/query"
FIELDS = "ALTKEY,PARID,DORPID,PID,OWNER1,OWNER2,MAILADDR1,MAILADDR2,MAILCITY,MAILSTATE,MAILZIP,ADDRFULL,CITYNAME,STATECODE,ZIP1,TOTJUST,LANDJUST,IMPRJUST,RES_BEDROOM,RES_BATHROOM,RES_TOTAL_SFLA,LASTSALEDT,LASTSALEPRICE,LEGAL1,PC_DESC,HXFLAG"

def fetch_chunk(offset: int, batch_size: int = 2000, max_retries: int = 3):
    """Fetch a single chunk of parcel attributes from ArcGIS FeatureServer."""
    params = {
        "where": "1=1",
        "outFields": FIELDS,
        "returnGeometry": "false",
        "resultOffset": str(offset),
        "resultRecordCount": str(batch_size),
        "f": "json"
    }
    url = f"{FEATURE_URL}?{urllib.parse.urlencode(params)}"
    
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
                features = data.get("features", [])
                records = [f["attributes"] for f in features if "attributes" in f]
                return records
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[Volusia] Error fetching chunk at offset {offset}: {e}")
                return []
            time.sleep(1.0 * (attempt + 1))
    return []

def get_total_count():
    """Get the exact total count of parcels in Volusia Layer 34."""
    params = {"where": "1=1", "returnCountOnly": "true", "f": "json"}
    url = f"{FEATURE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as res:
        data = json.loads(res.read().decode("utf-8"))
        return data.get("count", 313739)

def build_volusia_master():
    """Download and assemble all master parcels for Volusia County."""
    os.makedirs(VOLUSIA_DIR, exist_ok=True)
    
    total_count = get_total_count()
    batch_size = 2000
    offsets = list(range(0, total_count + batch_size, batch_size))
    print(f"[Volusia Master] Total parcels to download: {total_count:,} across {len(offsets)} chunks.")
    
    all_records = []
    completed = 0
    t0 = time.time()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {executor.submit(fetch_chunk, off, batch_size): off for off in offsets}
        for future in as_completed(future_map):
            records = future.result()
            if records:
                all_records.extend(records)
            completed += 1
            if completed % 20 == 0 or completed == len(offsets):
                elapsed = time.time() - t0
                pct = (completed / len(offsets)) * 100
                print(f"[Volusia Master] Progress: {completed}/{len(offsets)} chunks ({pct:.1f}%) - {len(all_records):,} parcels loaded ({elapsed:.1f}s)")
                
    if not all_records:
        print("[Volusia Master] Failed to retrieve any parcels.")
        return 0
        
    print(f"[Volusia Master] Assembling DataFrame for {len(all_records):,} parcels...")
    df = pd.DataFrame(all_records)
    
    # Map to standardized master parcel columns
    df["PARCEL_NUMBER"] = df["PID"].fillna(df["ALTKEY"]).astype(str).str.strip()
    df["STRAP"] = df["ALTKEY"].fillna(df["PID"]).astype(str).str.strip()
    df["SITE_ADDRESS"] = df["ADDRFULL"].fillna("").astype(str).str.strip()
    df["SITE_CITY"] = df["CITYNAME"].fillna("").astype(str).str.strip()
    df["SITE_ZIP"] = df["ZIP1"].fillna("").astype(str).str.strip()
    
    df["OWNER1"] = df["OWNER1"].fillna("").astype(str).str.strip()
    df["OWNER2"] = df["OWNER2"].fillna("").astype(str).str.strip()
    df["MAILING_ADDRESS_1"] = df["MAILADDR1"].fillna("").astype(str).str.strip()
    df["MAILING_CITY"] = df["MAILCITY"].fillna("").astype(str).str.strip()
    df["MAILING_STATE"] = df["MAILSTATE"].fillna("FL").astype(str).str.strip()
    df["MAILING_ZIP"] = df["MAILZIP"].fillna("").astype(str).str.strip()
    
    df["LEGAL"] = df["LEGAL1"].fillna("").astype(str).str.strip()
    df["PROPERTY_USE"] = df["PC_DESC"].fillna("").astype(str).str.strip()
    df["TOTAL_LIVING_SQFT"] = pd.to_numeric(df["RES_TOTAL_SFLA"], errors="coerce").fillna(0.0)
    df["YEAR_BUILT"] = 0.0
    
    df["CNTY_JST_VALUE"] = pd.to_numeric(df["TOTJUST"], errors="coerce").fillna(0.0)
    df["CNTY_ASD_VALUE"] = pd.to_numeric(df["IMPRJUST"], errors="coerce").fillna(0.0) + pd.to_numeric(df["LANDJUST"], errors="coerce").fillna(0.0)
    df["CNTY_ASD_VALUE"] = df["CNTY_ASD_VALUE"].where(df["CNTY_ASD_VALUE"] > 0, df["CNTY_JST_VALUE"])
    df["CNTY_TAXABLE_VALUE"] = df["CNTY_JST_VALUE"]
    
    target_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    
    df = df.drop_duplicates(subset=["PARCEL_NUMBER"])
    df = df[target_cols]
    
    print(f"[Volusia Master] Saving {len(df):,} parcels to {OUT_PARQUET}...")
    df.to_parquet(OUT_PARQUET, index=False)
    print(f"Successfully generated {OUT_PARQUET} ({os.path.getsize(OUT_PARQUET) / (1024*1024):.2f} MB)")
    return len(df)

if __name__ == "__main__":
    build_volusia_master()
