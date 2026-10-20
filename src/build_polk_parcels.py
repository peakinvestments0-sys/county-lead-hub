"""
Build unified Master Parcel Parquet for Polk County, FL (Lakeland, Winter Haven, Haines City, Davenport).
Merges official Polk County Property Appraiser (PCPA) CAMA data rolls:
- ftp_parcel.txt: parcel assessment, values, use codes
- ftp_owner.txt: owner names and mailing addresses
- ftp_site.txt: physical street addresses, cities, zips
- ftp_bldg.txt: year built and living area square footage
"""

import os
import sys
import pandas as pd

# Reconfigure stdout/stderr to utf-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLK_DIR = os.path.join(BASE_DIR, "data", "FL", "polk")
CAMA_DIR = os.path.join(POLK_DIR, "FTP_CAMA")
OUT_PARQUET = os.path.join(POLK_DIR, "RP_PROPERTY_INFO.parquet")

def build_polk_master():
    print("[Polk Master] Starting Polk County Master Parcel build...", flush=True)

    parcel_file = os.path.join(CAMA_DIR, "ftp_parcel.txt")
    owner_file = os.path.join(CAMA_DIR, "ftp_owner.txt")
    site_file = os.path.join(CAMA_DIR, "ftp_site.txt")
    bldg_file = os.path.join(CAMA_DIR, "ftp_bldg.txt")

    if not os.path.exists(parcel_file):
        print(f"[Polk Master] Error: {parcel_file} not found.", flush=True)
        return 0

    # 1. Load parcels
    print(f"[Polk Master] Reading {parcel_file}...", flush=True)
    df_parcel = pd.read_csv(
        parcel_file,
        usecols=['PARCEL_ID', 'TOTALVAL', 'ASSESSVAL', 'TAXVAL', 'HOMESTEAD', 'DORUS_CODE', 'DORDESC1'],
        dtype=str,
        encoding='latin-1',
        on_bad_lines='skip'
    )
    df_parcel['PARCEL_ID'] = df_parcel['PARCEL_ID'].astype(str).str.strip()
    df_parcel = df_parcel.drop_duplicates(subset=['PARCEL_ID'])
    print(f"[Polk Master] Loaded {len(df_parcel):,} unique parcel IDs.", flush=True)

    # 2. Load owners (primary owner: LN_NUM == '1')
    print(f"[Polk Master] Reading {owner_file}...", flush=True)
    df_owner = pd.read_csv(
        owner_file,
        usecols=['PARCEL_ID', 'LN_NUM', 'NAME', 'ADDR_1', 'ADDR_2', 'CITY', 'STATE', 'ZIP'],
        dtype=str,
        encoding='latin-1',
        on_bad_lines='skip'
    )
    df_owner['PARCEL_ID'] = df_owner['PARCEL_ID'].astype(str).str.strip()
    # Filter for primary owner line 1
    df_owner_p = df_owner[df_owner['LN_NUM'].astype(str).str.strip() == '1'].copy()
    if df_owner_p.empty:
        df_owner_p = df_owner.drop_duplicates(subset=['PARCEL_ID'])
    else:
        df_owner_p = df_owner_p.drop_duplicates(subset=['PARCEL_ID'])
    print(f"[Polk Master] Loaded {len(df_owner_p):,} primary owner records.", flush=True)

    # 3. Load site addresses
    print(f"[Polk Master] Reading {site_file}...", flush=True)
    df_site = pd.read_csv(
        site_file,
        usecols=['PARCEL_ID', 'STR_NUM', 'STR_PFX', 'STR', 'STR_SFX', 'STR_SFX_DIR', 'STR_UNIT', 'CITY', 'ZIP'],
        dtype=str,
        encoding='latin-1',
        on_bad_lines='skip'
    )
    df_site['PARCEL_ID'] = df_site['PARCEL_ID'].astype(str).str.strip()
    df_site = df_site.drop_duplicates(subset=['PARCEL_ID'])

    # Assemble site address
    def clean_str(s):
        return s.fillna('').astype(str).str.strip()

    num = clean_str(df_site['STR_NUM'])
    pfx = clean_str(df_site['STR_PFX'])
    street = clean_str(df_site['STR'])
    sfx = clean_str(df_site['STR_SFX'])
    sfx_dir = clean_str(df_site['STR_SFX_DIR'])
    unit = clean_str(df_site['STR_UNIT'])

    # Combine parts
    parts = []
    for col in [num, pfx, street, sfx, sfx_dir]:
        parts.append(col)
    
    # Vectorized join of non-empty words
    site_combined = parts[0]
    for p in parts[1:]:
        site_combined = site_combined + p.apply(lambda x: f" {x}" if x else "")
    
    unit_part = unit.apply(lambda x: f" #{x}" if x else "")
    df_site['SITE_ADDRESS'] = (site_combined + unit_part).str.strip()
    df_site['SITE_CITY'] = clean_str(df_site['CITY'])
    df_site['SITE_ZIP'] = clean_str(df_site['ZIP'])
    df_site = df_site[['PARCEL_ID', 'SITE_ADDRESS', 'SITE_CITY', 'SITE_ZIP']]
    print(f"[Polk Master] Assembled {len(df_site):,} site address records.", flush=True)

    # 4. Load buildings
    print(f"[Polk Master] Reading {bldg_file}...", flush=True)
    df_bldg = pd.read_csv(
        bldg_file,
        usecols=['PARCEL_ID', 'YEARBUILT', 'LIVINGAREA'],
        dtype=str,
        encoding='latin-1',
        on_bad_lines='skip'
    )
    df_bldg['PARCEL_ID'] = df_bldg['PARCEL_ID'].astype(str).str.strip()
    df_bldg = df_bldg.drop_duplicates(subset=['PARCEL_ID'])
    print(f"[Polk Master] Loaded {len(df_bldg):,} building records.", flush=True)

    # 5. Merge all into master roll
    print("[Polk Master] Merging datasets on PARCEL_ID...", flush=True)
    merged = df_parcel.merge(df_owner_p, on='PARCEL_ID', how='left')
    merged = merged.merge(df_site, on='PARCEL_ID', how='left')
    merged = merged.merge(df_bldg, on='PARCEL_ID', how='left')

    merged['PARCEL_NUMBER'] = merged['PARCEL_ID']
    merged['STRAP'] = merged['PARCEL_ID']
    merged['OWNER1'] = merged['NAME'].fillna('').astype(str).str.strip()
    merged['OWNER2'] = ''
    
    addr1 = merged['ADDR_1'].fillna('').astype(str).str.strip()
    addr2 = merged['ADDR_2'].fillna('').astype(str).str.strip()
    merged['MAILING_ADDRESS_1'] = addr1 + addr2.apply(lambda x: f" {x}" if x else "")
    merged['MAILING_CITY'] = merged['CITY'].fillna('').astype(str).str.strip()
    merged['MAILING_STATE'] = merged['STATE'].fillna('FL').astype(str).str.strip()
    merged['MAILING_ZIP'] = merged['ZIP'].fillna('').astype(str).str.strip()

    merged['LEGAL'] = ''
    merged['PROPERTY_USE'] = merged['DORDESC1'].fillna(merged['DORUS_CODE']).fillna('Residential').astype(str).str.strip()
    merged['TOTAL_LIVING_SQFT'] = pd.to_numeric(merged['LIVINGAREA'], errors='coerce').fillna(0.0)
    merged['YEAR_BUILT'] = pd.to_numeric(merged['YEARBUILT'], errors='coerce').fillna(0.0)
    
    merged['CNTY_JST_VALUE'] = pd.to_numeric(merged['TOTALVAL'], errors='coerce').fillna(0.0)
    merged['CNTY_ASD_VALUE'] = pd.to_numeric(merged['ASSESSVAL'], errors='coerce').fillna(merged['CNTY_JST_VALUE'])
    merged['CNTY_TAXABLE_VALUE'] = pd.to_numeric(merged['TAXVAL'], errors='coerce').fillna(merged['CNTY_JST_VALUE'])

    target_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]

    final_df = merged[target_cols].drop_duplicates(subset=['PARCEL_NUMBER'])
    print(f"[Polk Master] Writing {len(final_df):,} master parcels to {OUT_PARQUET}...", flush=True)
    final_df.to_parquet(OUT_PARQUET, index=False)
    file_size_mb = os.path.getsize(OUT_PARQUET) / (1024 * 1024)
    print(f"[Polk Master] COMPLETE: {OUT_PARQUET} generated ({file_size_mb:.2f} MB, {len(final_df):,} parcels).", flush=True)
    return len(final_df)

if __name__ == "__main__":
    build_polk_master()
