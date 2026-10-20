"""
City of Orlando Code Enforcement Live SODA API Sync Service
Direct integration with data.cityoforlando.net (Dataset ID: k6e8-nw6w)
Auto-pulls open residential deferred maintenance code violations,
matches against Orange County master tax parcels, and recomputes
Double Distress stacks against court judgments, recorded liens, probate, and water shutoffs.
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
import pandas as pd

from src.normalizer import clean_display_address, clean_display_name, clean_display_city
from src.counties import get_county_paths
from src.data_loader import load_master_parcels
from src.matcher import CrossReferenceEngine

ORLANDO_API_ENDPOINT = "https://data.cityoforlando.net/resource/k6e8-nw6w.json"

# Deferred maintenance & neglect keywords
NEGLECT_KEYWORDS = [
    "lot cleaning", "overgrown", "vegetation", "tall grass", "grass",
    "weed", "maintenance", "roof", "structure", "damaged", "trash",
    "debris", "junk", "abandoned", "boarded", "unfit", "minimum housing",
    "exterior", "unsafe", "inoperable", "no valid tag", "siding", "fence",
    "hazardous", "graffiti", "disrepair", "structural", "paint", "decay",
    "stagnant", "swimming pool", "window", "door", "porch", "fascia",
    "soffit", "gutters", "tarp", "dilapidated", "blight", "derelict"
]

# Excluded non-residential / commercial / multi-family keywords
EXCLUDED_USE_KEYWORDS = [
    "commercial", "office", "retail", "industrial", "warehouse",
    "shopping center", "hotel", "motel", "restaurant", "store",
    "apartment", "condo", "condominium", "church", "school",
    "hospital", "gas station", "auto repair"
]

def is_neglect_violation(case_name, comments, case_type):
    text = f"{case_name or ''} {comments or ''} {case_type or ''}".lower()
    return any(kw in text for kw in NEGLECT_KEYWORDS)

def is_residential_use(dor_desc, rev_class):
    desc = f"{dor_desc or ''} {rev_class or ''}".lower()
    # Check if explicitly residential or single family
    if any(k in desc for k in ["single family", "residential", "vacant residential", "mobile home", "duplex"]):
        # Ensure not condo or apartment
        if not any(k in desc for k in ["condo", "condominium", "apartment"]):
            return True
    # If unclassified or empty, don't discard if it has no commercial indicators
    if not any(k in desc for k in EXCLUDED_USE_KEYWORDS):
        return True
    return False

def fetch_live_orlando_cases(max_records=10000):
    """
    Fetch open code enforcement cases from City of Orlando SODA API.
    """
    all_records = []
    limit = 2000
    offset = 0

    while offset < max_records:
        query = {
            "$where": "caseinfostatus = 'Open' AND parcel_id IS NOT NULL",
            "$limit": limit,
            "$offset": offset,
            "$order": "casedt DESC"
        }
        url = f"{ORLANDO_API_ENDPOINT}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"})
        
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
                if not data:
                    break
                all_records.extend(data)
                if len(data) < limit:
                    break
                offset += limit
        except Exception as e:
            print(f"[Orlando Code API] Error fetching batch at offset {offset}: {e}")
            break

    return all_records

def sync_orlando_code_enforcement(db=None):
    """
    Pull live open cases, filter for residential deferred maintenance,
    cross-reference against master parcels and court records,
    and persist to matched_leads_cache.parquet.
    """
    orange_dir = os.path.join("data", "FL", "Orange")
    cache_file = os.path.join(orange_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(orange_dir, "Orange_Code_Enforcement_Property_Neglect_Leads.csv")

    print("[Orlando Code Sync] 1. Fetching live cases from City of Orlando API...")
    raw_cases = fetch_live_orlando_cases(max_records=8000)
    print(f"[Orlando Code Sync]    Fetched {len(raw_cases):,} open cases from API.")

    if not raw_cases:
        return {"status": "error", "message": "No cases returned from Orlando API."}

    # Filter for residential deferred maintenance & neglect
    filtered_cases = []
    for r in raw_cases:
        c_name = r.get("casename", "")
        c_comments = r.get("case_comments", "")
        c_type = r.get("casetype", "") or r.get("case_type", "")
        dor_desc = r.get("pa_dordesc", "")
        rev_class = r.get("dept_of_revenue_class", "")

        if not is_residential_use(dor_desc, rev_class):
            continue
        if not is_neglect_violation(c_name, c_comments, c_type):
            continue

        pid = str(r.get("parcel_id", "")).strip().replace("-", "").replace(" ", "")
        if len(pid) < 10:
            continue

        addr = r.get("derived_address", "") or r.get("case_address", "")
        filtered_cases.append({
            "Parcel ID": pid,
            "Case Address": addr,
            "Case Number": r.get("apno", ""),
            "Case Name": c_name,
            "Case Status": r.get("caseinfostatus", "Open"),
            "Case Open Date": (r.get("casedt", "") or "")[:10],
            "Case Comments": c_comments,
            "Dept Revenue Desc": dor_desc,
            "Source": "City of Orlando SODA API"
        })

    print(f"[Orlando Code Sync] 2. Filtered to {len(filtered_cases):,} residential neglect/maintenance cases.")
    if not filtered_cases:
        return {"status": "warning", "message": "No residential neglect cases found in current open batch."}

    api_df = pd.DataFrame(filtered_cases)

    # 3. Load Master Parcels for Cross-Referencing
    if db is None:
        print("[Orlando Code Sync] 3. Loading Orange County master tax parcels...")
        info = get_county_paths("Orange", state="FL")
        db = load_master_parcels(csv_path=info['csv_path'], parquet_path=info['parquet_path'])

    # 4. Cross reference against master database
    print("[Orlando Code Sync] 4. Matching against master parcels for owner & equity data...")
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
    matched_df = engine.cross_reference_dataframe(api_df, column_mapping)
    matched_code = matched_df[matched_df['Match_Status'] == 'MATCHED'].copy()
    print(f"[Orlando Code Sync]    Matched {len(matched_code):,} of {len(api_df):,} leads against master tax rolls.")

    matched_code['Lead_Type'] = 'Code Violation'
    matched_code['Source_File'] = 'City_of_Orlando_Live_API'
    if 'Subject_Case Number' in matched_code.columns:
        matched_code['Case_Number'] = matched_code['Subject_Case Number']

    # 5. Merge with existing other lead types (Lis Pendens, Judgments, Liens, Probate, Water)
    print("[Orlando Code Sync] 5. Merging with existing court and distressed filings...")
    cached_all = pd.read_parquet(cache_file)
    other_leads = cached_all[cached_all['Lead_Type'] != 'Code Violation'].copy()

    # Also keep any prior offline code leads that were already matched if not present in API
    prior_code = cached_all[cached_all['Lead_Type'] == 'Code Violation'].copy()
    api_pids = set(matched_code['Parcel_ID'])
    prior_unseen_code = prior_code[~prior_code['Parcel_ID'].isin(api_pids)]

    all_code_leads = pd.concat([prior_unseen_code, matched_code], ignore_index=True)
    all_code_leads = all_code_leads.drop_duplicates(subset=['Parcel_ID'], keep='last')

    combined_df = pd.concat([other_leads, all_code_leads], ignore_index=True)
    combined_df = combined_df.drop_duplicates(subset=['Parcel_ID', 'Lead_Type'], keep='last')

    # 6. Recompute Multi-Distress Stacking
    print("[Orlando Code Sync] 6. Recomputing Double & Triple Distress stacks...")
    c_lp = set(combined_df[combined_df['Lead_Type'] == 'Lis Pendens']['Parcel_ID'].dropna())
    c_code = set(combined_df[combined_df['Lead_Type'] == 'Code Violation']['Parcel_ID'].dropna())
    c_tax = set(combined_df[combined_df['Lead_Type'] == 'Tax Lien']['Parcel_ID'].dropna())
    c_probate = set(combined_df[combined_df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]['Parcel_ID'].dropna())
    c_water = set(combined_df[combined_df['Lead_Type'].str.contains('water|ouc', case=False, na=False)]['Parcel_ID'].dropna())
    c_judg = set(combined_df[combined_df['Lead_Type'].str.contains('judgment|lien', case=False, na=False)]['Parcel_ID'].dropna())

    def compute_stack(row):
        pid = row.get('Parcel_ID')
        lt = (row.get('Lead_Type') or '').lower()
        sig = []

        if "code" in lt:
            if pid in c_judg: sig.append("County Judgment / Recorded Lien")
            if pid in c_probate: sig.append("Active County Probate Court Case")
            if pid in c_lp: sig.append("Lis Pendens Foreclosure")
            if pid in c_water: sig.append("OUC Water Shutoff")
            if pid in c_tax: sig.append("County Tax Lien")
            if len(sig) >= 2:
                return ('Yes', f"💥 TRIPLE DISTRESS: Code Violation + {' + '.join(sig)}")
            elif len(sig) == 1:
                return ('Yes', f"🔥 DOUBLE DISTRESS: Code Violation + {sig[0]}")
            return ('No', '')
        elif "judgment" in lt or "lien" in lt:
            if pid in c_code: sig.append("Open Municipal Code Violation")
            if pid in c_probate: sig.append("Active County Probate Court Case")
            if pid in c_lp: sig.append("Lis Pendens Foreclosure")
            if pid in c_water: sig.append("OUC Water Shutoff")
            if len(sig) >= 2:
                return ('Yes', f"💥 TRIPLE DISTRESS: Judgment/Lien + {' + '.join(sig)}")
            elif len(sig) == 1:
                return ('Yes', f"🔥 DOUBLE DISTRESS: Judgment/Lien + {sig[0]}")
            return ('No', '')
        elif "probate" in lt:
            if pid in c_code: sig.append("Open Municipal Code Violation")
            if pid in c_judg: sig.append("County Judgment / Recorded Lien")
            if pid in c_lp: sig.append("Lis Pendens Foreclosure")
            if pid in c_water: sig.append("OUC Water Shutoff")
            if len(sig) >= 2:
                return ('Yes', f"💥 TRIPLE DISTRESS: Active Probate + {' + '.join(sig)}")
            elif len(sig) == 1:
                return ('Yes', f"🔥 DOUBLE DISTRESS: Active Probate + {sig[0]}")
            return ('No', '')
        elif "lis_pendens" in lt or "lis pendens" in lt:
            if pid in c_code: sig.append("Open Municipal Code Violation")
            if pid in c_judg: sig.append("County Judgment / Recorded Lien")
            if pid in c_probate: sig.append("Active County Probate Court Case")
            if pid in c_water: sig.append("OUC Water Shutoff")
            if len(sig) >= 2:
                return ('Yes', f"💥 TRIPLE DISTRESS: Lis Pendens + {' + '.join(sig)}")
            elif len(sig) == 1:
                return ('Yes', f"🔥 DOUBLE DISTRESS: Lis Pendens + {sig[0]}")
            return ('No', '')
        elif "water" in lt or "ouc" in lt:
            if pid in c_code: sig.append("Open Municipal Code Violation")
            if pid in c_judg: sig.append("County Judgment / Recorded Lien")
            if pid in c_probate: sig.append("Active County Probate Court Case")
            if len(sig) >= 1:
                return ('Yes', f"🔥 DOUBLE DISTRESS: Water Shutoff + {sig[0]}")
            return ('No', '')

        return ('No', '')

    stacks = [compute_stack(row) for _, row in combined_df.iterrows()]
    combined_df['Is_Stacked_Distress'] = [s[0] for s in stacks]
    combined_df['Distress_Stack_Notes'] = [s[1] for s in stacks]

    # Standardize column types to avoid PyArrow mixed type serialization errors
    for col in combined_df.columns:
        if col in ['Market_Value', 'Assessed_Value', 'Year_Built', 'Living_Sqft']:
            combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce').fillna(0).astype(int)
        elif col != 'All_Lead_Types':
            combined_df[col] = combined_df[col].fillna('').astype(str)

    # Save to parquet cache
    combined_df.to_parquet(cache_file, index=False)
    print(f"[Orlando Code Sync] 7. Saved {len(combined_df):,} total indexed records to {cache_file}.")

    # Write clean CSV backup of code leads
    code_export_df = combined_df[combined_df['Lead_Type'] == 'Code Violation']
    code_export_df.to_csv(csv_file, index=False)

    double_distress_code = len(combined_df[(combined_df['Lead_Type'] == 'Code Violation') & (combined_df['Is_Stacked_Distress'] == 'Yes')])

    # Count how many leads were genuinely new in this sync
    existing_pids = set(existing_code['Parcel_ID'].dropna().unique()) if not existing_code.empty else set()
    new_pids = set(all_code_leads['Parcel_ID'].dropna().unique()) - existing_pids
    new_leads_added = len(new_pids)

    # Determine the latest filing / inspection date published on the municipal API
    newest_case_date = "N/A"
    if raw_cases:
        dates = [c.get("casedt", "")[:10] for c in raw_cases if c.get("casedt")]
        if dates:
            newest_case_date = max(dates)

    return {
        "status": "success",
        "api_cases_fetched": len(raw_cases),
        "residential_neglect_leads": len(filtered_cases),
        "matched_code_leads": len(matched_code),
        "new_leads_added": new_leads_added,
        "newest_case_date": newest_case_date,
        "total_code_leads_now": len(all_code_leads),
        "code_double_distress_count": double_distress_code
    }

if __name__ == "__main__":
    res = sync_orlando_code_enforcement()
    print("Sync Result:", json.dumps(res, indent=2))
