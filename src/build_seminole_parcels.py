import os
import sys
import re
import zipfile
import time
import pandas as pd

DATA_DIR = r"C:\Projects\Apps\Pinellas-county-app\data\FL\Seminole"
ZIP_PATH = os.path.join(DATA_DIR, "SeminoleCounty_cama.zip")
OUTPUT_PARQUET = os.path.join(DATA_DIR, "RP_PROPERTY_INFO.parquet")

CITIES_PAT = r'(ALTAMONTE SPRINGS|CASSELBERRY|LAKE MARY|LONGWOOD|OVIEDO|SANFORD|WINTER SPRINGS|CHULUOTA|GENEVA|FERN PARK|HEATHROW|MIDWAY|APOPKA|ORLANDO)'

def parse_site_addr(addr):
    if not isinstance(addr, str) or not addr.strip():
        return '', 'Seminole', ''
    m = re.match(r'^(.*?)\s+' + CITIES_PAT + r'\s+FL\s*(\d{5}(?:-\d{4})?)?$', addr.strip(), re.I)
    if m:
        return m.group(1).strip(), m.group(2).strip().title(), (m.group(3) or '').strip()
    return addr.strip(), 'Seminole', ''

def parse_owners(owner_str):
    if not isinstance(owner_str, str) or not owner_str.strip():
        return '', ''
    parts = owner_str.split('&')
    o1 = parts[0].strip()
    o2 = parts[1].strip() if len(parts) > 1 else ''
    return o1, o2

def build_seminole_master_parquet():
    print("=================================================================")
    print("BUILDING SEMINOLE COUNTY MASTER PARQUET FROM CAMA DATA")
    print("=================================================================")
    t0 = time.time()
    
    if not os.path.exists(ZIP_PATH):
        raise FileNotFoundError(f"CAMA zip not found at {ZIP_PATH}")

    z = zipfile.ZipFile(ZIP_PATH)
    
    print("Loading Parcels.csv...")
    df_parcels = pd.read_csv(z.open("Parcels.csv"), low_memory=False)
    print(f"Loaded {len(df_parcels):,} parcels in {time.time() - t0:.2f}s.")
    
    print("Loading MailingLabels.csv...")
    df_mail = pd.read_csv(z.open("MailingLabels.csv"), usecols=['Parcel', 'Address1', 'Address2', 'CityStateZip'], low_memory=False)
    print(f"Loaded {len(df_mail):,} mailing label records.")
    
    # Merge mailing data on Parcel
    print("Merging parcel and mailing data...")
    df = pd.merge(df_parcels, df_mail, on='Parcel', how='left')
    
    print("Parsing site addresses and cities...")
    site_tuples = df['PrimaryAddress'].apply(parse_site_addr)
    df['SITE_ADDRESS'] = [t[0] for t in site_tuples]
    df['SITE_CITY'] = [t[1] for t in site_tuples]
    df['SITE_ZIP'] = [t[2] for t in site_tuples]
    df['SITE_CITYZIP'] = df['SITE_CITY'] + ', FL ' + df['SITE_ZIP']
    
    print("Parsing owner names...")
    owner_tuples = df['OwnerName'].apply(parse_owners)
    df['OWNER1'] = [t[0] for t in owner_tuples]
    df['OWNER2'] = [t[1] for t in owner_tuples]
    
    print("Parsing mailing addresses...")
    def parse_mail_csz(row):
        csz = str(row.get('CityStateZip', '') or '')
        parts = csz.split(',')
        city = parts[0].strip().title() if len(parts) > 0 else ''
        st_zip = parts[1].strip().split() if len(parts) > 1 else ['FL', '']
        state = st_zip[0] if len(st_zip) > 0 else 'FL'
        zip_code = st_zip[1] if len(st_zip) > 1 else ''
        addr1 = str(row.get('Address2', '') or '').strip()
        addr2 = str(row.get('Address1', '') or '').strip()
        if not addr1 and addr2:
            addr1 = addr2
            addr2 = ''
        return addr1, addr2, city, state, zip_code
        
    mail_tuples = df.apply(parse_mail_csz, axis=1)
    df['MAILING_ADDRESS_1'] = [t[0] for t in mail_tuples]
    df['MAILING_ADDRESS_2'] = [t[1] for t in mail_tuples]
    df['MAILING_CITY'] = [t[2] for t in mail_tuples]
    df['MAILING_STATE'] = [t[3] for t in mail_tuples]
    df['MAILING_ZIP'] = [t[4] for t in mail_tuples]
    
    # Map remaining columns
    df['PARCEL_NUMBER'] = df['Parcel'].astype(str).str.strip()
    df['STRAP'] = df['ParcelFormat'].fillna(df['Parcel']).astype(str).str.strip()
    df['LEGAL'] = df['LegalDescription'].fillna('').astype(str)
    df['PROPERTY_USE'] = df['DORCode'].fillna(df.get('PrimaryPropertyType', '')).astype(str)
    df['TOTAL_LIVING_SQFT'] = pd.to_numeric(df['TotalLivingArea'], errors='coerce').fillna(0).astype(int)
    df['YEAR_BUILT'] = pd.to_numeric(df['YearBuilt'], errors='coerce').fillna(0).astype(int)
    df['CNTY_JST_VALUE'] = pd.to_numeric(df['TotalJustValue'], errors='coerce').fillna(0).astype(float)
    df['CNTY_ASD_VALUE'] = pd.to_numeric(df['AssessedValue'], errors='coerce').fillna(0).astype(float)
    df['CNTY_TAXABLE_VALUE'] = pd.to_numeric(df['TaxableValue'], errors='coerce').fillna(0).astype(float)
    df['BEDROOMS'] = pd.to_numeric(df.get('TotalBedrooms', 0), errors='coerce').fillna(0).astype(int)
    df['BATHROOMS'] = pd.to_numeric(df.get('TotalBathrooms', 0), errors='coerce').fillna(0).astype(float)
    df['SUBDIVISION'] = df['Subdivision'].fillna('').astype(str)
    
    # Keep final standard columns
    final_cols = [
        'PARCEL_NUMBER', 'STRAP', 'SITE_ADDRESS', 'SITE_CITY', 'SITE_ZIP', 'SITE_CITYZIP',
        'OWNER1', 'OWNER2', 'MAILING_ADDRESS_1', 'MAILING_ADDRESS_2', 'MAILING_CITY',
        'MAILING_STATE', 'MAILING_ZIP', 'LEGAL', 'PROPERTY_USE', 'TOTAL_LIVING_SQFT',
        'YEAR_BUILT', 'CNTY_JST_VALUE', 'CNTY_ASD_VALUE', 'CNTY_TAXABLE_VALUE',
        'BEDROOMS', 'BATHROOMS', 'SUBDIVISION'
    ]
    
    df_out = df[final_cols].copy()
    
    # Standardize string types
    for c in df_out.columns:
        if df_out[c].dtype == 'object':
            df_out[c] = df_out[c].fillna('').astype(str)
            
    print(f"Writing to {OUTPUT_PARQUET}...")
    df_out.to_parquet(OUTPUT_PARQUET, index=False)
    print(f"=================================================================")
    print(f"SUCCESS: Saved {len(df_out):,} Seminole County parcels to:")
    print(f"{OUTPUT_PARQUET}")
    print(f"Total time: {time.time() - t0:.2f}s")
    print("=================================================================")
    return df_out

if __name__ == "__main__":
    build_seminole_master_parquet()
