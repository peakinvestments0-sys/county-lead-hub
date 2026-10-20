"""
Build unified Master Parcel Parquet for Lee County, FL (Fort Myers, Cape Coral, Lehigh Acres, Bonita Springs, Estero).
Parses the official Lee County Property Appraiser (LeePA) roll from LCPA_Parcel_Data_TXT.zip:
LCPA2609.txt (tab-delimited certified roll).
"""

import os
import sys
import zipfile
import pandas as pd

# Reconfigure stdout/stderr to utf-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEE_DIR = os.path.join(BASE_DIR, "data", "FL", "lee")
ZIP_PATH = os.path.join(LEE_DIR, "LCPA_Parcel_Data_TXT.zip")
OUT_PARQUET = os.path.join(LEE_DIR, "RP_PROPERTY_INFO.parquet")

def build_lee_master():
    print("[Lee Master] Starting Lee County Master Parcel build...", flush=True)

    if not os.path.exists(ZIP_PATH):
        print(f"[Lee Master] Error: {ZIP_PATH} not found.", flush=True)
        return 0

    print(f"[Lee Master] Opening {ZIP_PATH}...", flush=True)
    with zipfile.ZipFile(ZIP_PATH, 'r') as z:
        txt_files = [f for f in z.namelist() if f.endswith('.txt') and 'Field' not in f]
        if not txt_files:
            print("[Lee Master] Error: No data text file found in zip.", flush=True)
            return 0
        target_file = txt_files[0]
        print(f"[Lee Master] Reading {target_file} (tab-delimited)...", flush=True)

        cols_needed = [
            'Strap', 'FolioID', 'SiteAddress', 'SiteCity', 'SiteZip',
            'OwnerName', 'OwnerOthers', 'OwnerAddr1', 'OwnerCity', 'OwnerState', 'OwnerZip',
            'ShortLegal', 'DORcode', 'HeatedArea', 'TotalArea', 'MaxBuiltYear', 'MinBuiltYear',
            'Just', 'Assessed', 'Taxable'
        ]

        with z.open(target_file) as f:
            df = pd.read_csv(
                f,
                sep='\t',
                usecols=cols_needed,
                dtype=str,
                encoding='latin-1',
                on_bad_lines='skip'
            )

    print(f"[Lee Master] Loaded {len(df):,} raw parcels. Cleaning and standardizing...", flush=True)

    def clean_col(col):
        if col in df.columns:
            return df[col].fillna('').astype(str).str.strip()
        return pd.Series('', index=df.index)

    df['PARCEL_NUMBER'] = clean_col('Strap')
    df['STRAP'] = clean_col('Strap')
    df['FOLIO'] = clean_col('FolioID')
    df['SITE_ADDRESS'] = clean_col('SiteAddress')
    df['SITE_CITY'] = clean_col('SiteCity')
    df['SITE_ZIP'] = clean_col('SiteZip')

    df['OWNER1'] = clean_col('OwnerName')
    df['OWNER2'] = clean_col('OwnerOthers')
    df['MAILING_ADDRESS_1'] = clean_col('OwnerAddr1')
    df['MAILING_CITY'] = clean_col('OwnerCity')
    df['MAILING_STATE'] = clean_col('OwnerState').replace({'': 'FL'})
    df['MAILING_ZIP'] = clean_col('OwnerZip')

    df['LEGAL'] = clean_col('ShortLegal')
    df['PROPERTY_USE'] = clean_col('DORcode').replace({'': 'Residential'})

    living = clean_col('HeatedArea').replace({'': '0'})
    total_area = clean_col('TotalArea').replace({'': '0'})
    df['TOTAL_LIVING_SQFT'] = pd.to_numeric(living, errors='coerce').fillna(pd.to_numeric(total_area, errors='coerce')).fillna(0.0)

    yr_max = clean_col('MaxBuiltYear').replace({'': '0'})
    yr_min = clean_col('MinBuiltYear').replace({'': '0'})
    df['YEAR_BUILT'] = pd.to_numeric(yr_max, errors='coerce').fillna(pd.to_numeric(yr_min, errors='coerce')).fillna(0.0)

    df['CNTY_JST_VALUE'] = pd.to_numeric(clean_col('Just'), errors='coerce').fillna(0.0)
    df['CNTY_ASD_VALUE'] = pd.to_numeric(clean_col('Assessed'), errors='coerce').fillna(df['CNTY_JST_VALUE'])
    df['CNTY_TAXABLE_VALUE'] = pd.to_numeric(clean_col('Taxable'), errors='coerce').fillna(df['CNTY_JST_VALUE'])

    target_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]

    final_df = df[target_cols].drop_duplicates(subset=['PARCEL_NUMBER'])
    print(f"[Lee Master] Writing {len(final_df):,} master parcels to {OUT_PARQUET}...", flush=True)
    final_df.to_parquet(OUT_PARQUET, index=False)
    file_size_mb = os.path.getsize(OUT_PARQUET) / (1024 * 1024)
    print(f"[Lee Master] COMPLETE: {OUT_PARQUET} generated ({file_size_mb:.2f} MB, {len(final_df):,} parcels).", flush=True)
    return len(final_df)

if __name__ == "__main__":
    build_lee_master()
