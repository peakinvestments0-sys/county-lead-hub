import os
import sys
import re
import zipfile
import time
import pandas as pd

DATA_DIR = r"C:\Projects\Apps\Pinellas-county-app\data\FL\charlotte"
ZIP_PATH = os.path.join(DATA_DIR, "charlotte.zip")
OUTPUT_PARQUET = os.path.join(DATA_DIR, "RP_PROPERTY_INFO.parquet")

def parse_owners(owner_str):
    if not isinstance(owner_str, str) or not owner_str.strip():
        return '', ''
    parts = owner_str.split('&')
    o1 = parts[0].strip()
    o2 = parts[1].strip() if len(parts) > 1 else ''
    return o1, o2

ZIP_CITY_MAP = {
    '33954': 'Port Charlotte',
    '33952': 'Port Charlotte',
    '33948': 'Port Charlotte',
    '33980': 'Port Charlotte',
    '33981': 'Port Charlotte',
    '33983': 'Punta Gorda',
    '33950': 'Punta Gorda',
    '33955': 'Punta Gorda',
    '33982': 'Punta Gorda',
    '34224': 'Englewood',
    '34223': 'Englewood',
    '33946': 'Placida',
    '33947': 'Rotonda West',
    '34295': 'El Jobean',
    '33938': 'Boca Grande'
}

def build_charlotte_master_parquet():
    print("=================================================================")
    print("BUILDING CHARLOTTE COUNTY MASTER PARQUET FROM RAW CAMA")
    print("=================================================================")
    t0 = time.time()
    
    if not os.path.exists(ZIP_PATH):
        raise FileNotFoundError(f"Zip not found at {ZIP_PATH}")
        
    z = zipfile.ZipFile(ZIP_PATH)
    print("Reading cd.txt...")
    df = pd.read_csv(z.open('cd.txt'), sep='|', low_memory=False, encoding='latin1')
    print(f"Loaded {len(df):,} parcels in {time.time() - t0:.2f}s.")
    
    # 1. Parcel Number
    df['PARCEL_NUMBER'] = df['account'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df['STRAP'] = df['PARCEL_NUMBER']
    
    # 2. Owners
    owner_tuples = df['ownersname'].astype(str).apply(parse_owners)
    df['OWNER1'] = [t[0] for t in owner_tuples]
    df['OWNER2'] = [t[1] for t in owner_tuples]
    
    # 3. Site Address
    st_num = df['streetnumber'].fillna('').astype(str).str.replace(r'\.0$', '', regex=True).str.strip()
    st_name = df['streetname'].fillna('').astype(str).str.strip()
    df['SITE_ADDRESS'] = (st_num + ' ' + st_name).str.strip()
    
    df['SITE_ZIP'] = df['padZip'].fillna('').astype(str).str.strip().str[:5]
    df['SITE_CITY'] = df['SITE_ZIP'].map(ZIP_CITY_MAP).fillna('Port Charlotte')
    df['SITE_CITYZIP'] = df['SITE_CITY'] + ', FL ' + df['SITE_ZIP']
    
    # 4. Mailing Address
    m1 = df['mailingaddress2'].fillna('').astype(str).str.strip()
    m2 = df['mailingaddress'].fillna('').astype(str).str.strip()
    df['MAILING_ADDRESS_1'] = m1.where(m1 != '', m2)
    df['MAILING_ADDRESS_2'] = m2.where(m1 != '', '')
    df['MAILING_CITY'] = df['city'].fillna('').astype(str).str.strip().str.title()
    df['MAILING_STATE'] = df['state'].fillna('FL').astype(str).str.strip().str.upper()
    df['MAILING_ZIP'] = df['zipcode'].fillna('').astype(str).str.strip().str[:5]
    
    # 5. Property attributes
    df['LEGAL'] = df['longlegal'].fillna(df['shortlegal']).fillna('').astype(str).str.strip()
    df['PROPERTY_USE'] = df['landuse'].fillna('').astype(str).str.strip()
    df['TOTAL_LIVING_SQFT'] = pd.to_numeric(df['livingarea'], errors='coerce').fillna(0).astype(int)
    df['YEAR_BUILT'] = pd.to_numeric(df['yearbuilt'], errors='coerce').fillna(0).astype(int)
    
    # Valuations (priorjust = just/market value, priorassessed = assessed, priortaxable = taxable)
    df['CNTY_JST_VALUE'] = pd.to_numeric(df['priorjust'], errors='coerce').fillna(0).astype(float)
    df['CNTY_ASD_VALUE'] = pd.to_numeric(df['priorassessed'], errors='coerce').fillna(0).astype(float)
    df['CNTY_TAXABLE_VALUE'] = pd.to_numeric(df['priortaxable'], errors='coerce').fillna(0).astype(float)
    df['BEDROOMS'] = 0
    df['BATHROOMS'] = 0.0
    df['SUBDIVISION'] = df['neighborhood'].fillna('').astype(str).str.strip()
    
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
    print(f"SUCCESS: Saved {len(df_out):,} Charlotte County parcels to:")
    print(f"{OUTPUT_PARQUET}")
    print(f"Total time: {time.time() - t0:.2f}s")
    print("=================================================================")
    return df_out

if __name__ == "__main__":
    build_charlotte_master_parquet()
