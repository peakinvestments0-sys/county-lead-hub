"""
Build unified Master Parcel parquet for Hillsborough County, FL (Tampa & surrounding municipalities).
Pulls all 531,612 parcels directly from Hillsborough County Open Data GIS:
https://maps.hillsboroughcounty.org/arcgis/rest/services/PAO/Properties/MapServer/1
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
HILLSBOROUGH_DIR = os.path.join(BASE_DIR, "data", "FL", "hillsborough")
OUT_PARQUET = os.path.join(HILLSBOROUGH_DIR, "RP_PROPERTY_INFO.parquet")

FEATURE_URL = "https://maps.hillsboroughcounty.org/arcgis/rest/services/PAO/Properties/MapServer/1/query"
FIELDS = "FOLIO,PIN,STRAP,OWNER,ADDR_1,ADDR_2,CITY,STATE,ZIP,SITE_ADDR,SITE_CITY,SITE_ZIP,LEGAL1,LEGAL2,JUST,MARKET_VAL,ASD_VAL,TAX_VAL,HEAT_AR,ACT,DOR_CODE,LU_GRP"

def fetch_chunk(offset: int, batch_size: int = 2000, max_retries: int = 3):
    """Fetch a single chunk of parcel attributes from Hillsborough MapServer."""
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
                print(f"[Hillsborough] Error fetching chunk at offset {offset}: {e}")
                return []
            time.sleep(1.0 * (attempt + 1))
    return []

def get_total_count():
    """Get the exact total count of parcels in Hillsborough Layer 1."""
    params = {"where": "1=1", "returnCountOnly": "true", "f": "json"}
    url = f"{FEATURE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as res:
        data = json.loads(res.read().decode("utf-8"))
        return data.get("count", 531612)

def build_hillsborough_master():
    """Download and assemble all master parcels for Hillsborough County."""
    os.makedirs(HILLSBOROUGH_DIR, exist_ok=True)
    
    total_count = get_total_count()
    batch_size = 2000
    offsets = list(range(0, total_count + batch_size, batch_size))
    print(f"[Hillsborough Master] Total parcels to download: {total_count:,} across {len(offsets)} chunks.")
    
    all_records = []
    completed = 0
    t0 = time.time()
    
    with ThreadPoolExecutor(max_workers=12) as executor:
        future_map = {executor.submit(fetch_chunk, off, batch_size): off for off in offsets}
        for future in as_completed(future_map):
            records = future.result()
            if records:
                all_records.extend(records)
            completed += 1
            if completed % 30 == 0 or completed == len(offsets):
                elapsed = time.time() - t0
                pct = (completed / len(offsets)) * 100
                print(f"[Hillsborough Master] Progress: {completed}/{len(offsets)} chunks ({pct:.1f}%) - {len(all_records):,} parcels loaded ({elapsed:.1f}s)")
                
    if not all_records:
        print("[Hillsborough Master] Failed to retrieve any parcels.")
        return 0
        
    print(f"[Hillsborough Master] Assembling DataFrame for {len(all_records):,} parcels...")
    df = pd.DataFrame(all_records)
    
    # Map to standardized master parcel columns
    # PIN is the primary parcel number (e.g. 'U-03-29-17-0CB-000000-00001.0')
    # STRAP holds FOLIO / alt identifiers
    df["PARCEL_NUMBER"] = df["PIN"].fillna(df["FOLIO"]).astype(str).str.strip()
    df["STRAP"] = df["FOLIO"].fillna(df["PIN"]).astype(str).str.strip()
    df["SITE_ADDRESS"] = df["SITE_ADDR"].fillna("").astype(str).str.strip()
    df["SITE_CITY"] = df["SITE_CITY"].fillna("Tampa").astype(str).str.strip()
    df["SITE_ZIP"] = df["SITE_ZIP"].fillna("").astype(str).str.strip()
    
    df["OWNER1"] = df["OWNER"].fillna("").astype(str).str.strip()
    df["OWNER2"] = ""
    df["MAILING_ADDRESS_1"] = df["ADDR_1"].fillna("").astype(str).str.strip()
    df["MAILING_CITY"] = df["CITY"].fillna("").astype(str).str.strip()
    df["MAILING_STATE"] = df["STATE"].fillna("FL").astype(str).str.strip()
    df["MAILING_ZIP"] = df["ZIP"].fillna("").astype(str).str.strip()
    
    df["LEGAL"] = df["LEGAL1"].fillna("").astype(str).str.strip()
    df["PROPERTY_USE"] = df["LU_GRP"].fillna(df["DOR_CODE"]).fillna("Residential").astype(str).str.strip()
    df["TOTAL_LIVING_SQFT"] = pd.to_numeric(df["HEAT_AR"], errors="coerce").fillna(0.0)
    df["YEAR_BUILT"] = pd.to_numeric(df["ACT"], errors="coerce").fillna(0.0)
    
    df["CNTY_JST_VALUE"] = pd.to_numeric(df["JUST"].fillna(df["MARKET_VAL"]), errors="coerce").fillna(0.0)
    df["CNTY_ASD_VALUE"] = pd.to_numeric(df["ASD_VAL"].fillna(df["CNTY_JST_VALUE"]), errors="coerce").fillna(0.0)
    df["CNTY_TAXABLE_VALUE"] = pd.to_numeric(df["TAX_VAL"].fillna(df["CNTY_JST_VALUE"]), errors="coerce").fillna(0.0)
    
    target_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    
    df = df.drop_duplicates(subset=["PARCEL_NUMBER"])
    df = df[target_cols]
    
    print(f"[Hillsborough Master] Saving {len(df):,} parcels to {OUT_PARQUET}...")
    df.to_parquet(OUT_PARQUET, index=False)
    print(f"Successfully generated {OUT_PARQUET} ({os.path.getsize(OUT_PARQUET) / (1024*1024):.2f} MB)")
    return len(df)

if __name__ == "__main__":
    build_hillsborough_master()
