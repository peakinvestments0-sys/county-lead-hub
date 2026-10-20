import os
import sys
import time
import pandas as pd

DATA_DIR = r"C:\Projects\Apps\Pinellas-county-app\data\FL\manatee"
CSV_PATH = os.path.join(DATA_DIR, "PUBLIC_NAL.CSV")
OUTPUT_PARQUET = os.path.join(DATA_DIR, "RP_PROPERTY_INFO.parquet")

def build_manatee_master_parquet():
    print("=================================================================")
    print("BUILDING MANATEE COUNTY MASTER PARQUET FROM NAL CSV")
    print("=================================================================")
    t0 = time.time()
    
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"CSV not found at {CSV_PATH}")
        
    print(f"Reading {CSV_PATH}...")
    df = pd.read_csv(CSV_PATH, low_memory=False, encoding='latin1')
    print(f"Loaded {len(df):,} parcels in {time.time() - t0:.2f}s.")
    
    # 1. Parcel Number
    df['PARCEL_NUMBER'] = df['Parcel identification code'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df['STRAP'] = df['PARCEL_NUMBER']
    
    # 2. Owners
    df['OWNER1'] = df["Owner's name"].fillna('').astype(str).str.strip()
    df['OWNER2'] = ''
    
    # 3. Site Address
    st_addr = df['Physical location - Street address 1'].fillna('').astype(str).str.strip()
    df['SITE_ADDRESS'] = st_addr
    df['SITE_CITY'] = df['Physical location - City'].fillna('Bradenton').astype(str).str.strip().str.title()
    df['SITE_ZIP'] = df['Physical location - ZIP Code'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str[:5]
    df['SITE_CITYZIP'] = df['SITE_CITY'] + ', FL ' + df['SITE_ZIP']
    
    # 4. Mailing Address
    df['MAILING_ADDRESS_1'] = df["Owner's street address line 1"].fillna('').astype(str).str.strip()
    df['MAILING_ADDRESS_2'] = ''
    df['MAILING_CITY'] = df["Owner's city"].fillna('').astype(str).str.strip().str.title()
    df['MAILING_STATE'] = df["Owner's state or country"].fillna('FL').astype(str).str.strip().str.upper()
    df['MAILING_ZIP'] = df["Owner's US mail ZIP Code"].fillna('').astype(str).str.strip().str[:5]
    
    # 5. Property attributes
    df['LEGAL'] = df['Short legal description'].fillna('').astype(str).str.strip()
    df['PROPERTY_USE'] = df['DOR land use'].fillna('').astype(str).str.strip()
    df['TOTAL_LIVING_SQFT'] = pd.to_numeric(df['Total living or usable area'], errors='coerce').fillna(0).astype(int)
    df['YEAR_BUILT'] = pd.to_numeric(df['Actual year built'], errors='coerce').fillna(0).astype(int)
    
    df['CNTY_JST_VALUE'] = pd.to_numeric(df['Total just value'], errors='coerce').fillna(0).astype(float)
    df['CNTY_ASD_VALUE'] = pd.to_numeric(df['Non-school assessed value'], errors='coerce').fillna(0).astype(float)
    df['CNTY_TAXABLE_VALUE'] = pd.to_numeric(df['Non-school taxable value'], errors='coerce').fillna(0).astype(float)
    df['BEDROOMS'] = 0
    df['BATHROOMS'] = 0.0
    df['SUBDIVISION'] = df.get('Neighborhood code', '').fillna('').astype(str).str.strip()
    
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
    print(f"SUCCESS: Saved {len(df_out):,} Manatee County parcels to:")
    print(f"{OUTPUT_PARQUET}")
    print(f"Total time: {time.time() - t0:.2f}s")
    print("=================================================================")
    return df_out

if __name__ == "__main__":
    build_manatee_master_parquet()
