"""
Build unified Master Parcel Parquet for Bay County, FL (Panama City, Lynn Haven, Panama City Beach).
Streams the official Florida Department of Revenue (FDOR) certified roll for Bay County (CO_NO = '13')
from Florida Statewide Cadastral FeatureServer via concurrent chunked requests.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json
import time
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

BAY_DIR = os.path.join(BASE_DIR, "data", "FL", "bay")
OUT_PARQUET = os.path.join(BAY_DIR, "RP_PROPERTY_INFO.parquet")

CADASTRAL_URL = "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/Florida_Statewide_Cadastral/FeatureServer/0/query"

MIN_ID = 132352
MAX_ID = 267425
CHUNK_SIZE = 2000

def fetch_chunk(start_id, end_id, max_retries=3):
    """Fetch a single chunk of Bay County parcels by OBJECTID range."""
    params = {
        'where': f"OBJECTID >= {start_id} AND OBJECTID < {end_id} AND CO_NO = '13'",
        'outFields': 'PARCEL_ID,PHY_ADDR1,PHY_CITY,PHY_ZIPCD,OWN_NAME,OWN_ADDR1,OWN_CITY,OWN_STATE,OWN_ZIPCD,JV,AV_SD,TV_SD,TOT_LVG_AR,ACT_YR_BLT,DOR_UC,S_LEGAL',
        'returnGeometry': 'false',
        'resultRecordCount': '2000',
        'f': 'json'
    }
    url = f"{CADASTRAL_URL}?{urllib.parse.urlencode(params)}"
    headers = {'User-Agent': 'Mozilla/5.0 FloridaLeadHub/2.0'}

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode())
                features = data.get('features', [])
                records = [f.get('attributes', {}) for f in features]
                return records
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[Bay Build] Chunk [{start_id}-{end_id}] failed after {max_retries} attempts: {e}", flush=True)
                return []
            time.sleep(1.0 + attempt)
    return []

def build_bay_master():
    print("[Bay Build] Starting Bay County Master Parcel build...", flush=True)
    os.makedirs(BAY_DIR, exist_ok=True)

    ranges = []
    curr = MIN_ID
    while curr <= MAX_ID:
        ranges.append((curr, curr + CHUNK_SIZE))
        curr += CHUNK_SIZE

    print(f"[Bay Build] Total chunks to fetch: {len(ranges)} across OBJECTID {MIN_ID:,} - {MAX_ID:,}...", flush=True)

    all_records = []
    completed = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=14) as executor:
        futures = {executor.submit(fetch_chunk, s, e): (s, e) for s, e in ranges}
        for future in as_completed(futures):
            records = future.result()
            all_records.extend(records)
            completed += 1
            if completed % 15 == 0 or completed == len(ranges):
                elapsed = time.time() - t0
                print(f"[Bay Build] Progress: {completed}/{len(ranges)} chunks ({len(all_records):,} records) in {elapsed:.1f}s", flush=True)

    print(f"[Bay Build] Total raw records retrieved: {len(all_records):,}. Converting to DataFrame...", flush=True)
    df = pd.DataFrame(all_records)

    def clean_col(col):
        if col in df.columns:
            return df[col].fillna('').astype(str).str.strip()
        return pd.Series('', index=df.index)

    df['PARCEL_NUMBER'] = clean_col('PARCEL_ID')
    df['STRAP'] = clean_col('PARCEL_ID')
    df['SITE_ADDRESS'] = clean_col('PHY_ADDR1')
    df['SITE_CITY'] = clean_col('PHY_CITY').replace({'': 'PANAMA CITY'})
    df['SITE_ZIP'] = clean_col('PHY_ZIPCD')

    df['OWNER1'] = clean_col('OWN_NAME')
    df['OWNER2'] = ''
    df['MAILING_ADDRESS_1'] = clean_col('OWN_ADDR1')
    df['MAILING_CITY'] = clean_col('OWN_CITY')
    df['MAILING_STATE'] = clean_col('OWN_STATE').replace({'': 'FL'})
    df['MAILING_ZIP'] = clean_col('OWN_ZIPCD')

    df['LEGAL'] = clean_col('S_LEGAL')
    df['PROPERTY_USE'] = clean_col('DOR_UC').replace({'': 'Residential'})

    living = clean_col('TOT_LVG_AR').replace({'': '0'})
    df['TOTAL_LIVING_SQFT'] = pd.to_numeric(living, errors='coerce').fillna(0.0)

    yr_built = clean_col('ACT_YR_BLT').replace({'': '0'})
    df['YEAR_BUILT'] = pd.to_numeric(yr_built, errors='coerce').fillna(0.0)

    df['CNTY_JST_VALUE'] = pd.to_numeric(clean_col('JV'), errors='coerce').fillna(0.0)
    df['CNTY_ASD_VALUE'] = pd.to_numeric(clean_col('AV_SD'), errors='coerce').fillna(df['CNTY_JST_VALUE'])
    df['CNTY_TAXABLE_VALUE'] = pd.to_numeric(clean_col('TV_SD'), errors='coerce').fillna(df['CNTY_JST_VALUE'])

    target_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]

    final_df = df[target_cols].drop_duplicates(subset=['PARCEL_NUMBER'])
    final_df = final_df[final_df['PARCEL_NUMBER'] != '']

    print(f"[Bay Build] Writing {len(final_df):,} master parcels to {OUT_PARQUET}...", flush=True)
    final_df.to_parquet(OUT_PARQUET, index=False)
    file_size_mb = os.path.getsize(OUT_PARQUET) / (1024 * 1024)
    print(f"[Bay Build] COMPLETE: {OUT_PARQUET} generated ({file_size_mb:.2f} MB, {len(final_df):,} parcels).", flush=True)
    return len(final_df)

if __name__ == "__main__":
    build_bay_master()
