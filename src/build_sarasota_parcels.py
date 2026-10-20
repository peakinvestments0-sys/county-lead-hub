import os
import sys
import zipfile
import time
import pandas as pd

DATA_DIR = r"C:\Projects\Apps\Pinellas-county-app\data\FL\sarasota"
ZIP_PATH = os.path.join(DATA_DIR, "SCPA_Parcels_Sales_CSV.zip")
OUTPUT_PARQUET = os.path.join(DATA_DIR, "RP_PROPERTY_INFO.parquet")

def build_sarasota_master_parquet():
    print("=================================================================")
    print("BUILDING SARASOTA COUNTY MASTER PARQUET FROM SCPA DATA")
    print("=================================================================")
    t0 = time.time()
    
    if not os.path.exists(ZIP_PATH):
        raise FileNotFoundError(f"Zip not found at {ZIP_PATH}")
        
    z = zipfile.ZipFile(ZIP_PATH)
    print("Reading Parcel_Sales_CSV/Sarasota.csv...")
    df = pd.read_csv(z.open('Parcel_Sales_CSV/Sarasota.csv'), low_memory=False, encoding='latin1')
    print(f"Loaded {len(df):,} parcels in {time.time() - t0:.2f}s.")
    
    # 1. Parcel Number
    df['PARCEL_NUMBER'] = df['ACCOUNT'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df['STRAP'] = df['PARCEL_NUMBER']
    
    # 2. Owners
    df['OWNER1'] = df['NAME1'].fillna('').astype(str).str.strip()
    df['OWNER2'] = df['NAME_ADD2'].fillna('').astype(str).str.strip()
    
    # 3. Site Address
    st_num = df['LOCN'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    st_name = df['LOCS'].fillna('').astype(str).str.strip()
    unit = df['UNIT'].fillna('').astype(str).str.strip()
    unit_str = (' ' + unit).where(unit != '', '')
    df['SITE_ADDRESS'] = (st_num + ' ' + st_name + unit_str).str.strip()
    
    df['SITE_CITY'] = df['LOCCITY'].fillna('Sarasota').astype(str).str.strip().str.title()
    df['SITE_ZIP'] = df['LOCZIP'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str[:5]
    df['SITE_CITYZIP'] = df['SITE_CITY'] + ', FL ' + df['SITE_ZIP']
    
    # 4. Mailing Address
    m1 = df['NAME_ADD3'].fillna('').astype(str).str.strip()
    m2 = df['NAME_ADD4'].fillna('').astype(str).str.strip()
    df['MAILING_ADDRESS_1'] = m1
    df['MAILING_ADDRESS_2'] = m2
    df['MAILING_CITY'] = df['CITY'].fillna('').astype(str).str.strip().str.title()
    df['MAILING_STATE'] = df['STATE'].fillna('FL').astype(str).str.strip().str.upper()
    df['MAILING_ZIP'] = df['ZIP'].fillna('').astype(str).str.strip().str[:5]
    
    # 5. Property attributes
    l1 = df['LEGAL1'].fillna('').astype(str).str.strip()
    l2 = df['LEGAL2'].fillna('').astype(str).str.strip()
    l3 = df['LEGAL3'].fillna('').astype(str).str.strip()
    df['LEGAL'] = (l1 + ' ' + l2 + ' ' + l3).str.strip()
    
    df['PROPERTY_USE'] = df['STCD'].fillna(df.get('ZONING_1', '')).astype(str).str.strip()
    df['TOTAL_LIVING_SQFT'] = pd.to_numeric(df['LIVING'], errors='coerce').fillna(0).astype(int)
    df['YEAR_BUILT'] = pd.to_numeric(df['YRBL'], errors='coerce').fillna(0).astype(int)
    
    df['CNTY_JST_VALUE'] = pd.to_numeric(df['JUST'], errors='coerce').fillna(0).astype(float)
    df['CNTY_ASD_VALUE'] = pd.to_numeric(df['ASSD'], errors='coerce').fillna(0).astype(float)
    df['CNTY_TAXABLE_VALUE'] = pd.to_numeric(df['TXBL'], errors='coerce').fillna(0).astype(float)
    df['BEDROOMS'] = pd.to_numeric(df['BEDR'], errors='coerce').fillna(0).astype(int)
    df['BATHROOMS'] = pd.to_numeric(df['BATH'], errors='coerce').fillna(0).astype(float)
    df['SUBDIVISION'] = df['SUBD'].fillna('').astype(str).str.strip()
    
    final_cols = [
        'PARCEL_NUMBER', 'STRAP', 'SITE_ADDRESS', 'SITE_CITY', 'SITE_ZIP', 'SITE_CITYZIP',
        'OWNER1', 'OWNER2', 'MAILING_ADDRESS_1', 'MAILING_ADDRESS_2', 'MAILING_CITY',
        'MAILING_STATE', 'MAILING_ZIP', 'LEGAL', 'PROPERTY_USE', 'TOTAL_LIVING_SQFT',
        'YEAR_BUILT', 'CNTY_JST_VALUE', 'CNTY_ASD_VALUE', 'CNTY_TAXABLE_VALUE',
        'BEDROOMS', 'BATHROOMS', 'SUBDIVISION'
    ]
    
    df_out = df[final_cols].copy()
    for c in df_out.columns:
        if df_out[c].dtype == 'object':
            df_out[c] = df_out[c].fillna('').astype(str)
            
    print(f"Writing to {OUTPUT_PARQUET}...")
    df_out.to_parquet(OUTPUT_PARQUET, index=False)
    print(f"=================================================================")
    print(f"SUCCESS: Saved {len(df_out):,} Sarasota County parcels to:")
    print(f"{OUTPUT_PARQUET}")
    print(f"Total time: {time.time() - t0:.2f}s")
    print("=================================================================")
    return df_out

if __name__ == "__main__":
    build_sarasota_master_parquet()
