import os
import sys
sys.path.insert(0, os.path.abspath("."))
import shutil
import time
import pandas as pd
from src.counties import get_county_paths
from src.data_loader import load_master_parcels
from src.matcher import CrossReferenceEngine

def main():
    downloads_file = r"C:\Users\johng\Downloads\Orange_Code_Enforcement_Property_Neglect_Leads.csv"
    orange_dir = os.path.join("data", "FL", "Orange")
    old_file = os.path.join(orange_dir, "Code_Enforcement_Cases_20261005.csv")
    target_code_file = os.path.join(orange_dir, "Orange_Code_Enforcement_Property_Neglect_Leads.csv")
    cache_file = os.path.join(orange_dir, "matched_leads_cache.parquet")

    if not os.path.exists(downloads_file):
        print(f"Error: Could not find download file at {downloads_file}")
        sys.exit(1)

    print("1. Replacing file in data/FL/Orange/...")
    shutil.copy2(downloads_file, target_code_file)
    print(f"   Saved new file to: {target_code_file} ({os.path.getsize(target_code_file):,} bytes)")

    if os.path.exists(old_file):
        os.remove(old_file)
        print(f"   Removed old uncurated file: {old_file}")

    print("2. Loading Orange County master parcel database...")
    info = get_county_paths("Orange", state="FL")
    db = load_master_parcels(csv_path=info['csv_path'], parquet_path=info['parquet_path'])
    print(f"   Master parcels loaded: {len(db.df):,}")

    print("3. Matching newly filtered Code Enforcement leads...")
    subject_df = pd.read_csv(target_code_file, dtype=str, low_memory=False)
    print(f"   Input lead rows to match: {len(subject_df):,}")

    column_mapping = {
        'name_col': '',
        'first_name_col': '',
        'last_name_col': '',
        'address_col': 'Case Address',
        'parcel_col': 'Parcel ID',
        'legal_col': '',
        'bookpage_col': ''
    }

    engine = CrossReferenceEngine(db)
    matched_df = engine.cross_reference_dataframe(subject_df, column_mapping)
    matched_code = matched_df[matched_df['Match_Status'] == 'MATCHED'].copy()
    print(f"   Matched {len(matched_code):,} of {len(subject_df):,} leads against master tax rolls ({round(len(matched_code)/len(subject_df)*100, 1)}%)")

    matched_code['Lead_Type'] = 'Code Violation'
    matched_code['Source_File'] = os.path.basename(target_code_file)
    if 'Subject_Case Number' in matched_code.columns:
        matched_code['Case_Number'] = matched_code['Subject_Case Number']

    print("4. Updating matched_leads_cache.parquet...")
    cached_all = pd.read_parquet(cache_file)
    other_leads = cached_all[cached_all['Lead_Type'] != 'Code Violation'].copy()
    print(f"   Retained {len(other_leads):,} leads from other categories (Lis Pendens, OUC Water, Judgments, Liens, Divorce, Probate)")

    combined_df = pd.concat([other_leads, matched_code], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=['Parcel_ID', 'Lead_Type'], keep='last')

    print("5. Recomputing multi-distress stacking...")
    c_lp = set(combined_df[combined_df['Lead_Type'] == 'Lis Pendens']['Parcel_ID'].dropna())
    c_code = set(combined_df[combined_df['Lead_Type'] == 'Code Violation']['Parcel_ID'].dropna())
    c_tax = set(combined_df[combined_df['Lead_Type'] == 'Tax Lien']['Parcel_ID'].dropna())
    c_probate = set(combined_df[combined_df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]['Parcel_ID'].dropna())
    c_water = set(combined_df[combined_df['Lead_Type'].str.contains('water|ouc', case=False, na=False)]['Parcel_ID'].dropna())

    def compute_combined(pid, ltype):
        sig = []
        lt = (ltype or "").lower()
        if "probate" in lt:
            if pid in c_lp: sig.append("Lis Pendens Foreclosure")
            if pid in c_code: sig.append("Open Municipal Code Violation")
            if pid in c_tax: sig.append("County Tax Lien")
            if pid in c_water: sig.append("OUC Water Shutoff")
            if len(sig) >= 2: return ('Yes', f"💥 TRIPLE DISTRESS: Active Probate + {' + '.join(sig)}")
            elif len(sig) == 1: return ('Yes', f"🔥 DOUBLE DISTRESS: Active Probate + {sig[0]}")
            return ('No', '')
        elif "lis_pendens" in lt or "lis pendens" in lt:
            if pid in c_probate: sig.append("Active County Probate Court Case")
            if pid in c_code: sig.append("Open Municipal Code Violation")
            if pid in c_tax: sig.append("County Tax Lien")
            if pid in c_water: sig.append("OUC Water Shutoff")
            if len(sig) >= 2: return ('Yes', f"💥 TRIPLE DISTRESS: Lis Pendens + {' + '.join(sig)}")
            elif len(sig) == 1: return ('Yes', f"🔥 DOUBLE DISTRESS: Lis Pendens + {sig[0]}")
            return ('No', '')
        elif "code" in lt:
            if pid in c_probate: sig.append("Active County Probate Court Case")
            if pid in c_lp: sig.append("Lis Pendens Foreclosure")
            if pid in c_tax: sig.append("County Tax Lien")
            if pid in c_water: sig.append("OUC Water Shutoff")
            if len(sig) >= 2: return ('Yes', f"💥 TRIPLE DISTRESS: Code Violation + {' + '.join(sig)}")
            elif len(sig) == 1: return ('Yes', f"🔥 DOUBLE DISTRESS: Code Violation + {sig[0]}")
            return ('No', '')
        elif "tax" in lt:
            if pid in c_probate: sig.append("Active County Probate Court Case")
            if pid in c_lp: sig.append("Lis Pendens Foreclosure")
            if pid in c_code: sig.append("Open Municipal Code Violation")
            if pid in c_water: sig.append("OUC Water Shutoff")
            if len(sig) >= 2: return ('Yes', f"💥 TRIPLE DISTRESS: Tax Lien + {' + '.join(sig)}")
            elif len(sig) == 1: return ('Yes', f"🔥 DOUBLE DISTRESS: Tax Lien + {sig[0]}")
            return ('No', '')
        elif "water" in lt or "ouc" in lt:
            if pid in c_probate: sig.append("Active County Probate Court Case")
            if pid in c_lp: sig.append("Lis Pendens Foreclosure")
            if pid in c_code: sig.append("Open Municipal Code Violation")
            if pid in c_tax: sig.append("County Tax Lien")
            if len(sig) >= 2: return ('Yes', f"💥 TRIPLE DISTRESS: Water Shutoff + {' + '.join(sig)}")
            elif len(sig) == 1: return ('Yes', f"🔥 DOUBLE DISTRESS: Water Shutoff + {sig[0]}")
            return ('No', '')
        return ('No', '')

    res_c = combined_df.apply(lambda r: compute_combined(r.get('Parcel_ID', ''), r.get('Lead_Type', '')), axis=1)
    combined_df['Is_Stacked_Distress'] = res_c.apply(lambda x: x[0])
    combined_df['Distress_Stack_Notes'] = res_c.apply(lambda x: x[1])
    combined_df['Is_Trust_In_LP'] = combined_df.apply(
        lambda r: 'Yes' if (r.get('Lead_Type') == 'Lis Pendens' and (r.get('Is_Trust_Or_Estate') == 'Yes' or 'Trust' in str(r.get('Owner_Entity_Type', '')) or r.get('Is_Stacked_Distress') == 'Yes')) else 'No',
        axis=1
    )

    for c in combined_df.columns:
        if combined_df[c].dtype == 'object':
            combined_df[c] = combined_df[c].fillna('').astype(str)

    backup_cache = cache_file + ".bak"
    shutil.copy2(cache_file, backup_cache)
    combined_df.to_parquet(cache_file, index=False)
    print(f"   Successfully wrote updated cache: {cache_file} ({len(combined_df):,} total leads)")
    print(f"   - Code Violations: {len(combined_df[combined_df['Lead_Type'] == 'Code Violation']):,}")
    print(f"   - Stacked Distress Leads: {len(combined_df[combined_df['Is_Stacked_Distress'] == 'Yes']):,}")
    print("Done!")

if __name__ == "__main__":
    main()
