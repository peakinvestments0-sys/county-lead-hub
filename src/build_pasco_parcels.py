import os
import sys
import time
import zipfile
import openpyxl
import pandas as pd

DATA_DIR = r"C:\Projects\Apps\Pinellas-county-app\data\FL\pasco"
ZIP_PATH = os.path.join(DATA_DIR, "parcel_summary.zip")
OUTPUT_PARQUET = os.path.join(DATA_DIR, "RP_PROPERTY_INFO.parquet")

def build_pasco_master_parquet():
    print("=================================================================")
    print("BUILDING PASCO COUNTY MASTER PARQUET FROM RAW CAMA EXCEL")
    print("=================================================================")
    t0 = time.time()
    
    if not os.path.exists(ZIP_PATH):
        raise FileNotFoundError(f"Zip not found at {ZIP_PATH}")
        
    print("Opening parcel_summary.zip...")
    z = zipfile.ZipFile(ZIP_PATH)
    with z.open("parcel_summary.xlsx") as f:
        wb = openpyxl.load_workbook(f, read_only=True)
        sheet = wb.active
        rows = sheet.iter_rows(values_only=True)
        headers = [str(h).strip() for h in next(rows)]
        h_idx = {h: i for i, h in enumerate(headers)}
        
        parsed_records = []
        for i, r in enumerate(rows):
            p_num = str(r[h_idx['PARCEL']] or '').strip()
            if not p_num:
                continue
                
            o1 = str(r[h_idx['OWNER_NAME_1']] or '').strip()
            o2 = str(r[h_idx['OWNER_NAME_2']] or '').strip()
            
            site_addr = str(r[h_idx['SITE_ADDRESS']] or '').strip()
            site_city = str(r[h_idx['SITE_CITY']] or 'Pasco').strip().title()
            site_zip = str(r[h_idx['SITE_ZIP']] or '').strip()[:5]
            site_cityzip = f"{site_city}, FL {site_zip}"
            
            m1 = str(r[h_idx['MAILING_ADDRESS_1']] or '').strip()
            m2 = str(r[h_idx['MAILING_ADDRESS_2']] or '').strip()
            m_city = str(r[h_idx['MAILING_CITY']] or '').strip().title()
            m_state = str(r[h_idx['MAILING_STATE']] or 'FL').strip().upper()
            m_zip = str(r[h_idx['MAILING_ZIP']] or '').strip()[:5]
            
            legal = str(r[h_idx['LEGAL_DESCRIPTION']] or '').strip()
            prop_use = str(r[h_idx['LAND_USE_CODE']] or '').strip()
            subdiv = str(r[h_idx['SUBDIVISION']] or '').strip()
            
            jst_val = float(r[h_idx['JUST_VALUE']] or 0)
            asd_val = float(r[h_idx['ASSD_VAL_COUNTY']] or 0)
            txbl_val = float(r[h_idx['TAXABLE_VAL_COUNTY']] or 0)
            
            living_sqft = int(r[h_idx['LIVING_AREA']] or 0)
            year_built = int(r[h_idx['ACTUAL_YEAR_BUILT']] or 0)
            
            parsed_records.append({
                'PARCEL_NUMBER': p_num,
                'STRAP': p_num,
                'SITE_ADDRESS': site_addr,
                'SITE_CITY': site_city,
                'SITE_ZIP': site_zip,
                'SITE_CITYZIP': site_cityzip,
                'OWNER1': o1,
                'OWNER2': o2,
                'MAILING_ADDRESS_1': m1,
                'MAILING_ADDRESS_2': m2,
                'MAILING_CITY': m_city,
                'MAILING_STATE': m_state,
                'MAILING_ZIP': m_zip,
                'LEGAL': legal,
                'PROPERTY_USE': prop_use,
                'TOTAL_LIVING_SQFT': living_sqft,
                'YEAR_BUILT': year_built,
                'CNTY_JST_VALUE': jst_val,
                'CNTY_ASD_VALUE': asd_val,
                'CNTY_TAXABLE_VALUE': txbl_val,
                'BEDROOMS': 0,
                'BATHROOMS': 0.0,
                'SUBDIVISION': subdiv
            })
            
            if i % 100000 == 0 and i > 0:
                print(f"Parsed {i:,} parcels ({time.time() - t0:.1f}s)...")
                
    print(f"Creating DataFrame from {len(parsed_records):,} records...")
    df = pd.DataFrame(parsed_records)
    print(f"Writing to {OUTPUT_PARQUET}...")
    df.to_parquet(OUTPUT_PARQUET, index=False)
    print("=================================================================")
    print(f"SUCCESS: Saved {len(df):,} Pasco County parcels to:")
    print(f"{OUTPUT_PARQUET}")
    print(f"Total time: {time.time() - t0:.2f}s")
    print("=================================================================")
    return df

if __name__ == "__main__":
    build_pasco_master_parquet()
