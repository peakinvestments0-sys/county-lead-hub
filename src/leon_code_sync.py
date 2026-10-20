"""
Leon County (Tallahassee, Woodville, Bradfordville, Chaires, Fort Braden)
Live Code Enforcement & Distress API Sync Service.

Direct integration with:
- City of Tallahassee / Leon County Cityworks PLL Code Enforcement FeatureServer (COT_PSEVENTS_CWPLL_D_WM).
  Extracts active Code Board Fines (CB-FINE), Mowing Liens (MOW-FINE), Violation Notices (VCN),
  Unsafe Structures (UNSAFE), Hearings (HEARING), and Special Magistrate Referrals (REFERRED).
- Tallahassee & Leon County SeeClickFix Property Distress Feeds.
- Direct matching against ~111k Leon County Master Parcels via official Parcel PIN and normalized address.
- Retains genuine open citations, daily fine accumulations, structural hazards, and derelict properties.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json
import re
import time
import datetime
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

from src.normalizer import clean_display_address, clean_display_name, clean_display_city

LEON_CODE_URL = "https://cotinter.leoncountyfl.gov/cotinter/rest/services/Vector/COT_PSEVENTS_CWPLL_D_WM/MapServer/0/query"

LEON_SEECLICKFIX_CENTERS = [
    ("Tallahassee", 30.4383, -84.2807),
    ("Leon County", 30.4500, -84.3000),
    ("Woodville", 30.3094, -84.2505),
    ("Bradfordville", 30.5516, -84.2185)
]

LEON_CITIES = [
    'TALLAHASSEE', 'WOODVILLE', 'BRADFORDVILLE', 'CHAIRES', 'FORT BRADEN', 'LEON'
]

def norm_addr(a):
    """Normalize address for robust matching."""
    if not a:
        return ""
    a = str(a).upper().strip()
    a = re.sub(r'[^\w\s]', ' ', a)
    a = re.sub(r'\s+', ' ', a).strip()
    replacements = {
        ' STREET': ' ST', ' AVENUE': ' AVE', ' ROAD': ' RD', ' BOULEVARD': ' BLVD',
        ' DRIVE': ' DR', ' COURT': ' CT', ' LANE': ' LN', ' CIRCLE': ' CIR',
        ' NORTH': ' N', ' SOUTH': ' S', ' EAST': ' E', ' WEST': ' W',
        ' PARKWAY': ' PKWY', ' HIGHWAY': ' HWY', ' PLACE': ' PL', ' TERRACE': ' TER',
        ' TRAIL': ' TRL', ' WAY': ' WAY', ' SUITE': ' STE', ' APARTMENT': ' APT',
        ' UNIT': ' UNIT'
    }
    for k, v in replacements.items():
        a = a.replace(k, v)
    return a.strip()

def clean_scf_address(raw_addr):
    """Strip city names, zip code, state and trailing fluff from raw SeeClickFix addresses."""
    if not raw_addr:
        return ""
    clean = re.sub(r',\s*FLORIDA.*$', '', raw_addr, flags=re.IGNORECASE)
    clean = re.sub(r',\s*FL\b.*$', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\b32\d{3}\b', '', clean)
    clean = clean.replace('USA', '').replace('United States', '')
    clean = clean.strip().rstrip(',')
    u_clean = clean.upper()
    for city in LEON_CITIES:
        if u_clean.endswith(city):
            clean = clean[:len(clean) - len(city)].strip().rstrip(',')
            break
        if u_clean.endswith(", " + city) or u_clean.endswith("," + city):
            clean = clean.split(city)[0].strip().rstrip(',')
            break
    return clean.strip()

def fetch_leon_cityworks_violations():
    """Fetch active code violations and fines from Tallahassee-Leon Cityworks FeatureServer."""
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    all_records = []
    chunk_size = 1000
    offset = 0

    print("[Leon API Sync] Querying Tallahassee-Leon Cityworks Code Violations API...", flush=True)

    where_clause = "STATUSCURRENT IN ('CB-FINE', 'MOW-FINE', 'VCN', 'REFERRED', 'UNSAFE', 'NOTICE', 'HEARING')"
    fields = "OBJECTID,PERMITNUM,STATUSCURRENT,ORGINALADDRESS1,ORGINALCITY,ORIGINALZIP,PIN,DESCRIPTION,FINEDAILY,FINEBASE,WORKCLASSMAPPED,COMP_TYPE,VIO_YEAR,APPLIEDDATE"

    while True:
        params = {
            'where': where_clause,
            'outFields': fields,
            'resultOffset': str(offset),
            'resultRecordCount': str(chunk_size),
            'returnGeometry': 'false',
            'f': 'json'
        }
        url = f"{LEON_CODE_URL}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
                features = data.get("features", [])
                if not features:
                    break
                records = [f.get("attributes", {}) for f in features]
                all_records.extend(records)
                print(f"[Leon API Sync] Fetched {len(all_records):,} violations so far (offset {offset})...", flush=True)
                if len(features) < chunk_size:
                    break
                offset += chunk_size
        except Exception as e:
            print(f"[Leon API Sync] Error fetching Cityworks violations at offset {offset}: {e}", flush=True)
            break
        time.sleep(0.3)

    print(f"[Leon API Sync] Harvested {len(all_records):,} active Cityworks code violations.", flush=True)
    return all_records

def fetch_leon_seeclickfix_distress():
    """Fetch and filter genuine property distress from SeeClickFix across Leon County."""
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    total_issues = {}

    noise_keywords = [
        "pothole", "street light", "streetlight", "traffic light", "traffic signal",
        "sidewalk", "curb", "playground", "park", "drainage", "storm drain",
        "dead animal", "roadkill", "dead cat", "dead dog", "sign request", "street sign",
        "speeding", "traffic calming", "road", "hacked", "borrow", "financing"
    ]

    distress_keywords = [
        "code", "violation", "overgrown", "grass", "weed", "trash", "debris",
        "abandon", "vacant", "boarded", "hazard", "unsafe", "derelict",
        "blight", "unpermitted", "roof", "tarp", "squatter", "demolition",
        "building", "structure", "dilapidated", "junk", "inoperable vehicle"
    ]

    for hub_name, lat, lng in LEON_SEECLICKFIX_CENTERS:
        for page in [1, 2]:
            url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=12&per_page=100&page={page}"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode())
                    issues = data.get("issues", [])
                    if not issues:
                        break
                    for issue in issues:
                        issue_id = issue.get("id")
                        summary = str(issue.get("summary") or "").lower()
                        desc = str(issue.get("description") or "").lower()
                        comb = f"{summary} {desc}"

                        if any(n in comb for n in noise_keywords):
                            continue
                        if any(d in comb for d in distress_keywords):
                            total_issues[issue_id] = issue
            except Exception as e:
                print(f"[Leon SCF] Hub {hub_name} page {page} error: {e}", flush=True)
                break
            time.sleep(0.4)

    print(f"[Leon SCF] Harvested {len(total_issues)} property distress issues from SeeClickFix.", flush=True)
    return list(total_issues.values())

def sync_leon_leads(force_refresh=False):
    """
    Sync and match Leon County live distress feeds against master parcels.
    Outputs to data/FL/leon/matched_leads_cache.parquet.
    """
    leads_parquet = os.path.join(BASE_DIR, "data", "FL", "leon", "matched_leads_cache.parquet")
    parcels_parquet = os.path.join(BASE_DIR, "data", "FL", "leon", "RP_PROPERTY_INFO.parquet")

    if not os.path.exists(parcels_parquet):
        print(f"[Leon API Sync] Master parcel roll not found at {parcels_parquet}. Run parcel builder first.", flush=True)
        return {"status": "error", "message": "Master parcel roll not found"}

    print("[Leon API Sync] Loading Leon Master Parcels...", flush=True)
    t0 = time.time()
    parcels_df = pd.read_parquet(
        parcels_parquet,
        columns=[
            "PARCEL_NUMBER", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
            "OWNER1", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
            "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "YEAR_BUILT", "TOTAL_LIVING_SQFT", "LEGAL"
        ]
    )
    print(f"[Leon API Sync] Loaded {len(parcels_df):,} master parcels in {time.time()-t0:.2f}s", flush=True)

    # Index by exact PARCEL_NUMBER and normalized SITE_ADDRESS
    parcel_pin_map = {}
    addr_map = {}
    for idx, row in parcels_df.iterrows():
        p = str(row["PARCEL_NUMBER"] or "").strip()
        if p and p not in parcel_pin_map:
            parcel_pin_map[p] = row
            # Also without spaces if needed
            p_nospace = p.replace(" ", "")
            if p_nospace not in parcel_pin_map:
                parcel_pin_map[p_nospace] = row

        site_a = norm_addr(row["SITE_ADDRESS"])
        if site_a and site_a not in addr_map:
            addr_map[site_a] = row

    matched_rows = []

    # 1. Process Cityworks Code Violations
    cityworks_violations = fetch_leon_cityworks_violations()
    for v in cityworks_violations:
        raw_pin = str(v.get("PIN") or "").strip()
        raw_addr = str(v.get("ORGINALADDRESS1") or "").strip()

        matched_parcel = parcel_pin_map.get(raw_pin)
        if matched_parcel is None and raw_pin:
            matched_parcel = parcel_pin_map.get(raw_pin.replace(" ", ""))
        if matched_parcel is None and raw_addr:
            matched_parcel = addr_map.get(norm_addr(raw_addr))

        if matched_parcel is None:
            continue

        m = matched_parcel
        pid = str(m.get("PARCEL_NUMBER") or raw_pin)
        site_addr = str(m.get("SITE_ADDRESS") or raw_addr)
        site_zip = str(m.get("SITE_ZIP") or v.get("ORIGINALZIP") or "")
        mail_addr = str(m.get("MAILING_ADDRESS_1") or "")
        mail_state = str(m.get("MAILING_STATE") or "FL")
        mail_zip = str(m.get("MAILING_ZIP") or "")

        is_absentee = "Yes" if (mail_state and mail_state != "FL") or (norm_addr(site_addr) != norm_addr(mail_addr) and mail_addr != "") else "No"
        absentee_status = "Out of State" if mail_state and mail_state != "FL" else ("Out of County" if is_absentee == "Yes" else "Owner Occupied")

        status_cur = str(v.get("STATUSCURRENT") or "Code Violation")
        case_num = str(v.get("PERMITNUM") or v.get("CASE_NUMBER") or f"LEON-{v.get('OBJECTID')}")
        fine_daily = v.get("FINEDAILY")
        fine_base = v.get("FINEBASE")
        applied_ts = v.get("APPLIEDDATE")

        filing_date = ""
        if applied_ts:
            try:
                filing_date = datetime.datetime.fromtimestamp(applied_ts / 1000.0).strftime('%Y-%m-%d')
            except Exception:
                filing_date = str(v.get("VIO_YEAR") or "2024")
        else:
            filing_date = str(v.get("VIO_YEAR") or "2024")

        distress_note = f"Cityworks Code Enforcement ({status_cur})"
        if fine_daily and fine_daily > 0:
            distress_note += f" • Daily Fine: ${fine_daily}/day"
        if fine_base and fine_base > 0:
            distress_note += f" • Base Fine: ${fine_base}"

        lead_row = {
            "Match_Status": "MATCHED",
            "Match_Confidence": 100 if raw_pin in parcel_pin_map else 95,
            "Match_Method": "PIN Exact Match" if raw_pin in parcel_pin_map else "Address Exact Match",
            "Match_Notes": f"Tallahassee-Leon Cityworks Code Violation #{case_num} ({status_cur})",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Tallahassee")),
            "Property_Zip": site_zip,
            "Parcel_ID": pid,
            "Strap": pid,
            "Mailing_Address": clean_display_address(str(m.get("MAILING_ADDRESS_1") or "")),
            "Mailing_City": clean_display_city(str(m.get("MAILING_CITY") or "")),
            "Mailing_State": mail_state,
            "Mailing_Zip": mail_zip,
            "Absentee_Status": absentee_status,
            "Is_Absentee": is_absentee,
            "Homestead_Exemption": "Yes" if is_absentee == "No" else "No",
            "Market_Value": int(m.get("CNTY_JST_VALUE") or 0),
            "Assessed_Value": int(m.get("CNTY_ASD_VALUE") or 0),
            "Year_Built": int(m.get("YEAR_BUILT") or 0),
            "Living_Sqft": int(m.get("TOTAL_LIVING_SQFT") or 0),
            "Legal_Description": str(m.get("LEGAL") or ""),
            "Lead_Type": "Code Violation",
            "All_Lead_Types": ["Code Violation"],
            "Distress_Stack_Notes": distress_note,
            "Is_Stacked_Distress": "No",
            "Case_Number": case_num,
            "Source_File": "Tallahassee_Leon_Cityworks_Live_API",
            "Filing_Date": filing_date,
            "Photo_Url": ""
        }
        matched_rows.append(lead_row)

    # 2. Process SeeClickFix issues
    scf_issues = fetch_leon_seeclickfix_distress()
    for issue in scf_issues:
        raw_addr = issue.get("address") or ""
        clean_addr = clean_scf_address(raw_addr)
        n_addr = norm_addr(clean_addr)

        matched_parcel = addr_map.get(n_addr)
        if matched_parcel is None:
            continue

        m = matched_parcel
        pid = str(m.get("PARCEL_NUMBER") or "")
        site_addr = str(m.get("SITE_ADDRESS") or clean_addr)
        site_zip = str(m.get("SITE_ZIP") or "")
        mail_addr = str(m.get("MAILING_ADDRESS_1") or "")
        mail_state = str(m.get("MAILING_STATE") or "FL")
        mail_zip = str(m.get("MAILING_ZIP") or "")

        is_absentee = "Yes" if (mail_state and mail_state != "FL") or (norm_addr(site_addr) != norm_addr(mail_addr) and mail_addr != "") else "No"
        absentee_status = "Out of State" if mail_state and mail_state != "FL" else ("Out of County" if is_absentee == "Yes" else "Owner Occupied")

        scf_summary = issue.get("summary") or "Code Violation"
        scf_id = issue.get("id")
        created_at = issue.get("created_at", "")[:10]
        media_url = issue.get("media", {}).get("image_full") if issue.get("media") else ""

        lead_row = {
            "Match_Status": "MATCHED",
            "Match_Confidence": 95,
            "Match_Method": "Address Exact Match",
            "Match_Notes": f"Matched via SeeClickFix distress report #{scf_id}",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Tallahassee")),
            "Property_Zip": site_zip,
            "Parcel_ID": pid,
            "Strap": pid,
            "Mailing_Address": clean_display_address(str(m.get("MAILING_ADDRESS_1") or "")),
            "Mailing_City": clean_display_city(str(m.get("MAILING_CITY") or "")),
            "Mailing_State": mail_state,
            "Mailing_Zip": mail_zip,
            "Absentee_Status": absentee_status,
            "Is_Absentee": is_absentee,
            "Homestead_Exemption": "Yes" if is_absentee == "No" else "No",
            "Market_Value": int(m.get("CNTY_JST_VALUE") or 0),
            "Assessed_Value": int(m.get("CNTY_ASD_VALUE") or 0),
            "Year_Built": int(m.get("YEAR_BUILT") or 0),
            "Living_Sqft": int(m.get("TOTAL_LIVING_SQFT") or 0),
            "Legal_Description": str(m.get("LEGAL") or ""),
            "Lead_Type": "Code Violation",
            "All_Lead_Types": ["Code Violation"],
            "Distress_Stack_Notes": f"Leon Property Distress: {scf_summary}",
            "Is_Stacked_Distress": "No",
            "Case_Number": f"SCF-{scf_id}",
            "Source_File": "Leon_SeeClickFix_Live_API",
            "Filing_Date": created_at,
            "Photo_Url": media_url
        }
        matched_rows.append(lead_row)

    print(f"[Leon API Sync] Total matched leads generated: {len(matched_rows):,}", flush=True)

    target_columns = [
        "Match_Status", "Match_Confidence", "Match_Method", "Match_Notes",
        "Clean_First_Name", "Clean_Last_Name", "Clean_Full_Name", "Owner_Entity_Type",
        "Is_Trust_Or_Estate", "County_Owner_1", "County_Owner_2", "Secondary_Owner",
        "Property_Address", "Property_City", "Property_Zip", "Parcel_ID", "Strap",
        "Mailing_Address", "Mailing_City", "Mailing_State", "Mailing_Zip",
        "Absentee_Status", "Is_Absentee", "Homestead_Exemption",
        "Market_Value", "Assessed_Value", "Year_Built", "Living_Sqft",
        "Legal_Description", "Lead_Type", "All_Lead_Types", "Distress_Stack_Notes",
        "Is_Stacked_Distress", "Case_Number", "Source_File", "Filing_Date", "Photo_Url"
    ]

    if not matched_rows:
        if os.path.exists(leads_parquet) and os.path.getsize(leads_parquet) > 1000:
            existing_df = pd.read_parquet(leads_parquet)
            return {
                "status": "success",
                "county": os.path.basename(os.path.dirname(leads_parquet)),
                "total_leads": len(existing_df),
                "unique_properties": len(existing_df["Parcel_ID"].unique()) if "Parcel_ID" in existing_df.columns else len(existing_df),
                "cache_file": leads_parquet,
                "message": "No new leads in live poll; preserved existing verified cache."
            }
        empty_df = pd.DataFrame(columns=target_columns)
        empty_df.to_parquet(leads_parquet, index=False)
        return {
            "status": "success",
            "county": os.path.basename(os.path.dirname(leads_parquet)),
            "total_leads": 0,
            "cache_file": leads_parquet,
            "message": "Initialized empty matched leads cache."
        }

    leads_df = pd.DataFrame(matched_rows)

    pid_counts = leads_df["Parcel_ID"].value_counts()
    stacked_pids = set(pid_counts[pid_counts > 1].index)
    leads_df["Is_Stacked_Distress"] = leads_df["Parcel_ID"].apply(lambda x: "Yes" if x in stacked_pids else "No")

    for p_id in stacked_pids:
        sub = leads_df[leads_df["Parcel_ID"] == p_id]
        types_combined = sorted(list(set(sub["Lead_Type"].tolist())))
        for idx in sub.index:
            leads_df.at[idx, "All_Lead_Types"] = types_combined

    if os.path.exists(leads_parquet) and os.path.getsize(leads_parquet) > 1000:


        try:


            _existing_df = pd.read_parquet(leads_parquet)


            if len(_existing_df) > 0 and "Parcel_ID" in _existing_df.columns:


                leads_df = pd.concat([_existing_df, leads_df], ignore_index=True).drop_duplicates(subset=["Parcel_ID"]).reset_index(drop=True)


        except Exception:


            pass


    leads_df.to_parquet(leads_parquet, index=False)
    file_size_kb = os.path.getsize(leads_parquet) / 1024

    stats = {
        "status": "success",
        "county": "leon",
        "county_name": "Leon County",
        "total_leads": len(leads_df),
        "unique_properties": len(leads_df["Parcel_ID"].unique()),
        "stacked_distress_count": len(stacked_pids),
        "absentee_owners": int((leads_df["Is_Absentee"] == "Yes").sum()),
        "cache_file": leads_parquet,
        "cache_size_kb": round(file_size_kb, 1),
        "sync_timestamp": datetime.datetime.now().isoformat()
    }

    print(f"[Leon API Sync] COMPLETE: {stats['total_leads']:,} leads saved to {leads_parquet} ({file_size_kb:.1f} KB)", flush=True)
    return stats

if __name__ == "__main__":
    res = sync_leon_leads(force_refresh=True)
    print(json.dumps(res, indent=2))
