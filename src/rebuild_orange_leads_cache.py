import os
import sys
import time
import re
import pandas as pd
import openpyxl

sys.path.insert(0, os.path.abspath("."))

from src.counties import get_county_paths
from src.data_loader import load_master_parcels
from src.matcher import CrossReferenceEngine
from src.normalizer import normalize_name_for_matching
from src.wholesaling import enrich_wholesale_record
from src.jail_lead_agent import sync_orange_county_jail_leads

def build_full_orange_cache():
    orange_dir = os.path.join("data", "FL", "Orange")
    cache_file = os.path.join(orange_dir, "matched_leads_cache.parquet")
    info = get_county_paths("Orange", state="FL")
    
    print("=================================================================")
    print("STEP 1: Loading Orange County Master Parcels (496k records)...")
    print("=================================================================")
    t0 = time.time()
    db = load_master_parcels(csv_path=info['csv_path'], parquet_path=info['parquet_path'])
    engine = CrossReferenceEngine(db)
    master_df = db.df
    print(f"Master parcels loaded in {time.time() - t0:.2f}s.")

    all_matched_dfs = []

    # -------------------------------------------------------------
    # 2. LIS PENDENS
    # -------------------------------------------------------------
    lp_file = os.path.join(orange_dir, "Orange_County_Lis_Pendens_10526.csv")
    if os.path.exists(lp_file):
        print("\nSTEP 2: Matching Lis Pendens leads...")
        df_lp = pd.read_csv(lp_file, dtype=str, low_memory=False)
        extracted_pids = []
        for leg in df_lp.get('Legal Description', []):
            leg_str = str(leg or '')
            m = re.search(r'Parcel:\s*([0-9\s]+)', leg_str)
            if m:
                extracted_pids.append(re.sub(r'\s+', '', m.group(1)))
            else:
                extracted_pids.append('')
        df_lp['EXTRACTED_PARCEL'] = extracted_pids

        col_map_lp = {
            'name_col': 'Full Name' if 'Full Name' in df_lp.columns else 'Last Name',
            'address_col': '',
            'parcel_col': 'EXTRACTED_PARCEL',
            'legal_col': 'Legal Description',
            'bookpage_col': ''
        }
        matched_lp = engine.cross_reference_dataframe(df_lp, col_map_lp)
        matched_lp = matched_lp[matched_lp['Match_Status'] == 'MATCHED'].copy()
        matched_lp['Lead_Type'] = 'Lis Pendens'
        matched_lp['Source_File'] = os.path.basename(lp_file)
        if 'Document #' in matched_lp.columns:
            matched_lp['Document_Number'] = matched_lp['Document #']
        if 'Recording Date' in matched_lp.columns:
            matched_lp['Recording_Date'] = matched_lp['Recording Date']
        print(f"-> Matched {len(matched_lp):,} Lis Pendens leads.")
        all_matched_dfs.append(matched_lp)

    # -------------------------------------------------------------
    # 3. CODE ENFORCEMENT
    # -------------------------------------------------------------
    code_file = os.path.join(orange_dir, "Orange_Code_Enforcement_Property_Neglect_Leads.csv")
    if not os.path.exists(code_file):
        code_file = os.path.join(orange_dir, "Code_Enforcement_Cases_20261005.csv")
    if os.path.exists(code_file):
        print("\nSTEP 3: Matching Code Enforcement leads...")
        df_code = pd.read_csv(code_file, dtype=str, low_memory=False)
        col_map_code = {
            'name_col': '',
            'address_col': 'Case Address',
            'parcel_col': 'Parcel ID',
            'legal_col': '',
            'bookpage_col': ''
        }
        matched_code = engine.cross_reference_dataframe(df_code, col_map_code)
        matched_code = matched_code[matched_code['Match_Status'] == 'MATCHED'].copy()
        matched_code['Lead_Type'] = 'Code Violation'
        matched_code['Source_File'] = os.path.basename(code_file)
        if 'Subject_Case Number' in matched_code.columns:
            matched_code['Case_Number'] = matched_code['Subject_Case Number']
        if 'Subject_Case Open Date' in matched_code.columns:
            matched_code['Recording_Date'] = matched_code['Subject_Case Open Date']
        print(f"-> Matched {len(matched_code):,} Code Enforcement leads.")
        all_matched_dfs.append(matched_code)

    # -------------------------------------------------------------
    # 4. COMPTROLLER OFFICIAL RECORDS (Judgments, Liens, Probate, Divorce)
    # -------------------------------------------------------------
    compt_file = os.path.join(orange_dir, "Orange_County_Comptroller_Official_Records_2026.csv")
    if os.path.exists(compt_file):
        print("\nSTEP 4: Matching Comptroller Official Records...")
        raw_df = pd.read_csv(compt_file, dtype=str, low_memory=False)
        matched_compt = []
        for idx, r in raw_df.iterrows():
            desc = str(r.get('Description', '')).strip()
            grantor = str(r.get('Grantor', '')).strip()
            grantee = str(r.get('Grantee', '')).strip()
            parcel = str(r.get('Extracted_Parcel', '')).strip()
            doc_num = str(r.get('Document #', '')).strip()
            rec_date = str(r.get('Recording Date', '')).strip()

            match_idx = None
            match_method = ''

            if parcel and parcel in db.parcel_index:
                match_idx = db.parcel_index[parcel]
                match_method = 'Exact Parcel ID'
            elif parcel and parcel in db.strap_index:
                match_idx = db.strap_index[parcel]
                match_method = 'Exact Strap ID'

            if match_idx is None:
                target_names = []
                if 'Death Certificate' in desc: target_names = [grantor]
                elif 'Power of Attorney' in desc: target_names = [grantor, grantee]
                elif 'Domestic Relations' in desc: target_names = [grantor, grantee]
                elif 'Probate' in desc: target_names = [grantor, grantee]
                elif 'Judgment' in desc: target_names = [grantee]
                elif 'Lien' in desc: target_names = [grantee]
                else: target_names = [grantee, grantor]

                for nm in target_names:
                    if not nm or nm == 'nan': continue
                    for sub in re.split(r'[,;]', nm):
                        sub = sub.strip()
                        if not sub or len(sub) < 4: continue
                        if any(k in sub.upper() for k in [
                            'STATE OF FLORIDA', 'CLERK', 'COUNTY', 'CITY OF', 'DEPARTMENT', 'BANK',
                            'LLC', 'INC', 'CORP', 'COMPANY', 'HOSPITAL', 'ADVENTHEALTH', 'ORLANDO HEALTH',
                            'PROGRESSIVE', 'GEICO', 'STATE FARM', 'ALLSTATE', 'UNITED STATES', 'USA'
                        ]): continue
                        norm = normalize_name_for_matching(sub)
                        if norm in db.owner_exact_index:
                            match_idx = db.owner_exact_index[norm][0]
                            match_method = 'Exact Owner Name'
                            break
                        toks = norm.split()
                        if len(toks) >= 2:
                            inv = f'{toks[-1]} ' + ' '.join(toks[:-1])
                            if inv in db.owner_exact_index:
                                match_idx = db.owner_exact_index[inv][0]
                                match_method = 'Inverted Owner Name'
                                break
                    if match_idx is not None: break

            if match_idx is not None:
                p_row = master_df.iloc[match_idx].to_dict()
                l_type = desc
                if 'Judgment' in desc: l_type = 'Civil Judgment'
                elif 'Lien' in desc: l_type = 'Recorded Lien'
                elif 'Probate' in desc: l_type = 'Probate Court Paper'
                elif 'Domestic Relations' in desc: l_type = 'Divorce (Domestic Relations)'
                elif 'Death Certificate' in desc: l_type = 'Probate (Death Certificate)'
                elif 'Power of Attorney' in desc: l_type = 'Power of Attorney'

                row_lead = {
                    'Match_Status': 'MATCHED',
                    'Match_Confidence': 'HIGH',
                    'Match_Method': match_method,
                    'Lead_Type': l_type,
                    'Source_File': os.path.basename(compt_file),
                    'Document_Number': doc_num,
                    'Recording_Date': rec_date,
                    'Subject_Grantor': grantor,
                    'Subject_Grantee': grantee,
                    'Subject_Description': desc,
                    'Property_Address': p_row.get('SITE_ADDRESS', ''),
                    'Property_City': p_row.get('SITE_CITY', ''),
                    'Property_Zip': str(p_row.get('SITE_ZIP', '')),
                    'Parcel_ID': str(p_row.get('PARCEL_NUMBER', '')),
                    'Strap': str(p_row.get('STRAP', p_row.get('PARCEL_NUMBER', ''))),
                    'County_Owner_1': p_row.get('OWNER1', ''),
                    'County_Owner_2': p_row.get('OWNER2', ''),
                    'Mailing_Address': p_row.get('MAILING_ADDRESS_1', ''),
                    'Mailing_City': p_row.get('MAILING_CITY', ''),
                    'Mailing_State': p_row.get('MAILING_STATE', 'FL'),
                    'Mailing_Zip': str(p_row.get('MAILING_ZIP', '')),
                    'Market_Value': p_row.get('CNTY_JST_VALUE', 0),
                    'Assessed_Value': p_row.get('CNTY_ASD_VALUE', 0),
                    'Year_Built': p_row.get('YEAR_BUILT', 0),
                    'Living_Sqft': p_row.get('TOTAL_LIVING_SQFT', 0),
                    'Property_Use': p_row.get('PROPERTY_USE', ''),
                    'Is_Absentee': 'Yes' if str(p_row.get('MAILING_ADDRESS_1', '')).strip().upper() != str(p_row.get('SITE_ADDRESS', '')).strip().upper() else 'No',
                    'Absentee_Status': 'Owner-Occupied' if str(p_row.get('MAILING_ADDRESS_1', '')).strip().upper() == str(p_row.get('SITE_ADDRESS', '')).strip().upper() else ('Absentee (Out-of-State)' if str(p_row.get('MAILING_STATE', 'FL')).strip().upper() != 'FL' else 'Absentee (In-State)')
                }
                matched_compt.append(row_lead)

        df_compt = pd.DataFrame(matched_compt)
        print(f"-> Matched {len(df_compt):,} Comptroller leads.")
        all_matched_dfs.append(df_compt)

    # -------------------------------------------------------------
    # 5. OUC WATER SHUTOFF
    # -------------------------------------------------------------
    ouc_file = os.path.join(orange_dir, "Orange_County_OUC_Water_Shutoff_1026.xlsx")
    if os.path.exists(ouc_file):
        print("\nSTEP 5: Matching OUC Water Shutoffs...")
        wb = openpyxl.load_workbook(ouc_file, read_only=True)
        ws = wb.active
        headers = None
        header_idx = None
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True), 1):
            if not any(row): continue
            if 'ACCOUNT STATUS' in [str(c).upper() for c in row if c]:
                headers = [str(c).strip() if c else f'COL_{ci}' for ci, c in enumerate(row)]
                header_idx = i
                continue
            if headers and header_idx and i > header_idx:
                status = str(row[1]).upper() if len(row) > 1 and row[1] else ''
                if 'OFF' in status:
                    rows.append(dict(zip(headers, row)))
        subject_ouc = pd.DataFrame(rows)
        col_map_ouc = {
            'address_col': 'SERVICE ADDRESS',
            'name_col': 'NAME',
            'parcel_col': '',
            'legal_col': '',
            'bookpage_col': ''
        }
        matched_ouc = engine.cross_reference_dataframe(subject_ouc, col_map_ouc)
        matched_ouc = matched_ouc[matched_ouc['Match_Status'] == 'MATCHED'].copy()
        matched_ouc['Lead_Type'] = 'OUC water shutoff'
        matched_ouc['Source_File'] = os.path.basename(ouc_file)
        print(f"-> Matched {len(matched_ouc):,} OUC Water Shutoff leads.")
        all_matched_dfs.append(matched_ouc)

    # -------------------------------------------------------------
    # 6. ORANGE COUNTY JAIL LEGAL DISTRESS (FELONY)
    # -------------------------------------------------------------
    jail_file = os.path.join(orange_dir, "Orange_County_Legal_Distress_Leads.csv")
    if os.path.exists(jail_file):
        print("\nSTEP 6: Ingesting Orange County Jail Felony Legal Distress leads...")
        df_jail = pd.read_csv(jail_file, dtype=str, low_memory=False)
        print(f"-> Ingesting {len(df_jail):,} Felony Legal Distress leads.")
        all_matched_dfs.append(df_jail)

    # -------------------------------------------------------------
    # 7. COMBINE, RECONCILE COLUMNS & MULTI-DISTRESS STACKING
    # -------------------------------------------------------------
    print("\nSTEP 7: Combining all sources & computing Multi-Distress Stacking...")
    combined = pd.concat(all_matched_dfs, ignore_index=True)
    combined = combined[
        (combined['Match_Status'] == 'MATCHED') &
        (combined['Parcel_ID'].astype(str).str.strip() != '') &
        (combined['Property_Address'].astype(str).str.strip() != '')
    ].copy()

    # Build distress sets by Parcel_ID
    c_lp = set(combined[combined['Lead_Type'] == 'Lis Pendens']['Parcel_ID'].dropna())
    c_code = set(combined[combined['Lead_Type'] == 'Code Violation']['Parcel_ID'].dropna())
    c_water = set(combined[combined['Lead_Type'].str.contains('water|ouc', case=False, na=False)]['Parcel_ID'].dropna())
    c_probate = set(combined[combined['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]['Parcel_ID'].dropna())
    c_legal = set(combined[combined['Lead_Type'].str.contains('legal distress|arrest|felony', case=False, na=False)]['Parcel_ID'].dropna())
    c_judgment = set(combined[combined['Lead_Type'].str.contains('judgment|lien', case=False, na=False)]['Parcel_ID'].dropna())

    def compute_combined_stacking(r):
        pid = str(r.get('Parcel_ID', ''))
        lt = str(r.get('Lead_Type', '')).lower()
        signals = []

        if pid in c_legal and 'legal' not in lt:
            signals.append("⚖️ Felony Arrest / Legal Distress")
        if pid in c_code and 'code' not in lt:
            signals.append("Open Municipal Code Violation")
        if pid in c_lp and 'lis pendens' not in lt:
            signals.append("Lis Pendens Foreclosure")
        if pid in c_water and 'water' not in lt and 'ouc' not in lt:
            signals.append("OUC Water Shutoff")
        if pid in c_probate and 'probate' not in lt and 'death' not in lt:
            signals.append("County Probate / Estate Case")
        if pid in c_judgment and 'judgment' not in lt and 'lien' not in lt:
            signals.append("County Civil Judgment / Recorded Lien")

        if len(signals) >= 2:
            return ('Yes', f"💥 TRIPLE DISTRESS: {r.get('Lead_Type', '')} + {' + '.join(signals)}")
        elif len(signals) == 1:
            return ('Yes', f"🔥 DOUBLE DISTRESS: {r.get('Lead_Type', '')} + {signals[0]}")
        return ('No', r.get('Distress_Stack_Notes', ''))

    res_stack = combined.apply(compute_combined_stacking, axis=1)
    combined['Is_Stacked_Distress'] = res_stack.apply(lambda x: x[0])
    combined['Distress_Stack_Notes'] = res_stack.apply(lambda x: x[1])

    # Ensure all string columns
    for col in combined.columns:
        if combined[col].dtype == 'object':
            combined[col] = combined[col].fillna('').astype(str)

    # Save final cache
    combined.to_parquet(cache_file, index=False)
    print(f"\n=================================================================")
    print(f"CACHE GENERATION COMPLETE: {cache_file}")
    print(f"Total Unique Matched Leads: {len(combined):,}")
    print("Breakdown by Lead_Type:")
    print(combined['Lead_Type'].value_counts())
    print(f"Total Stacked Distress Leads: {len(combined[combined['Is_Stacked_Distress'] == 'Yes']):,}")
    print("=================================================================")
    return combined

if __name__ == "__main__":
    build_full_orange_cache()
