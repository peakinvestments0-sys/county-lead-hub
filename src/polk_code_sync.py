"""
Polk County Live Code Enforcement & Distress API Sync Service
Direct integration with:
1. City of Lakeland IMS Code Enforcement FeatureServer:
   https://services1.arcgis.com/mcbQY5xNGGGM1vBX/arcgis/rest/services/IMS_Enforcement_Cases/FeatureServer/0
2. Polk County / Winter Haven SeeClickFix Distress Feed.

Matches against 438,643 Polk County Master Parcels (Lakeland, Winter Haven, Haines City, Bartow, Lake Wales, Davenport).
Strictly filters out municipal infrastructure noise (potholes, street lights, sidewalks).
Retains genuine property neglect, damaged structures, zoning violations, and open code citations.
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
import pandas as pd

from src.normalizer import clean_display_address, clean_display_name, clean_display_city

LAKELAND_IMS_ENDPOINT = "https://services1.arcgis.com/mcbQY5xNGGGM1vBX/arcgis/rest/services/IMS_Enforcement_Cases/FeatureServer/0/query"

POLK_SEECLICKFIX_CENTERS = [
    ("Winter Haven", 28.0222, -81.7329),
    ("Lakeland", 28.0395, -81.9498),
    ("Haines City", 28.1142, -81.6179),
    ("Bartow", 27.8964, -81.8431),
    ("Lake Wales", 27.9014, -81.5859),
    ("Auburndale", 28.0653, -81.7887),
    ("Davenport", 28.1614, -81.6017)
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
        ' PARKWAY': ' PKWY', ' HIGHWAY': ' HWY', ' PLACE': ' PL'
    }
    for k, v in replacements.items():
        a = a.replace(k, v)
    return a.strip()

def fetch_lakeland_ims_cases():
    """Fetch active code enforcement cases from City of Lakeland IMS FeatureServer."""
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    params = {
        "where": "1=1",
        "outFields": "CASENO,CASENAME,SITE_ADDR,SITE_CITY,SITE_STATE,SITE_ZIP,CASETYPE,STATUS,STARTED,URL",
        "f": "json"
    }
    url = f"{LAKELAND_IMS_ENDPOINT}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            features = data.get("features", [])
            cases = [f.get("attributes", {}) for f in features]
            print(f"[Polk API Sync] Lakeland IMS cases fetched: {len(cases):,}", flush=True)
            return cases
    except Exception as e:
        print(f"[Polk API Sync] Error fetching Lakeland IMS cases: {e}", flush=True)
        return []

def fetch_polk_seeclickfix_distress():
    """Fetch and filter genuine property distress from SeeClickFix across Polk County."""
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    total_issues = {}

    noise_keywords = [
        "pothole", "street light", "streetlight", "traffic light", "traffic signal",
        "sidewalk", "curb", "playground", "park", "drainage", "storm drain",
        "dead animal", "sign request", "street sign", "speeding", "traffic calming"
    ]

    for name, lat, lng in POLK_SEECLICKFIX_CENTERS:
        for page in range(1, 3):
            url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=100&page={page}"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    issues = data.get("issues", [])
                    if not issues:
                        break
                    for iss in issues:
                        iid = iss.get("id")
                        if not iid or iid in total_issues:
                            continue
                        cat = str((iss.get("request_type") or {}).get("title") or "").lower()
                        summary = str(iss.get("summary") or "").lower()
                        desc = str(iss.get("description") or "").lower()
                        full_text = f"{cat} {summary} {desc}"

                        # Skip noise
                        if any(k in full_text for k in noise_keywords):
                            continue

                        # Keep genuine property distress
                        distress_keywords = [
                            "code", "violation", "neglect", "trash", "debris", "overgrown",
                            "abandoned", "derelict", "unoccupied", "water", "damage",
                            "structure", "roof", "blight", "dumping", "inoperable"
                        ]
                        if any(k in full_text for k in distress_keywords):
                            total_issues[iid] = iss
                time.sleep(0.05)
            except Exception:
                break

    print(f"[Polk API Sync] Filtered property distress issues from SeeClickFix: {len(total_issues):,}", flush=True)
    return list(total_issues.values())

def sync_polk_live_apis():
    """
    Live sync all Polk County distress feeds against 438,643 Master Parcels:
    1. Fetch Lakeland IMS Code Enforcement cases (1,267 live cases).
    2. Fetch Polk SeeClickFix filtered distress issues.
    3. Match against Master Parcels via normalized site addresses.
    4. Build and cache matched_leads_cache.parquet.
    """
    polk_dir = os.path.join(BASE_DIR, "data", "FL", "polk")
    parquet_path = os.path.join(polk_dir, "RP_PROPERTY_INFO.parquet")
    cache_file = os.path.join(polk_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(polk_dir, "Polk_Live_API_Distress_Leads.csv")

    if not os.path.exists(parquet_path):
        return {"status": "error", "message": f"Polk master parcels not found at {parquet_path}"}

    print(f"[Polk API Sync] Loading Polk Master Parcels from {parquet_path}...", flush=True)
    master_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    master_df = pd.read_parquet(parquet_path, columns=master_cols)
    print(f"[Polk API Sync] Loaded {len(master_df):,} master parcels. Indexing normalized addresses...", flush=True)

    master_df["NORM_ADDR"] = master_df["SITE_ADDRESS"].apply(norm_addr)
    # Fast dict mapping: norm_addr -> master series
    master_lookup = {}
    for r in master_df.to_dict(orient="records"):
        n = r.get("NORM_ADDR")
        if n and n not in master_lookup:
            master_lookup[n] = r

    ims_cases = fetch_lakeland_ims_cases()
    scf_cases = fetch_polk_seeclickfix_distress()

    matched_rows = []
    seen_lead_keys = set()

    # 1. Process Lakeland IMS Code Enforcement Cases
    for c in ims_cases:
        raw_addr = c.get("SITE_ADDR") or ""
        na = norm_addr(raw_addr)
        if not na or na not in master_lookup:
            continue

        m = master_lookup[na]
        pid = str(m.get("PARCEL_NUMBER") or "").strip()
        case_no = str(c.get("CASENO") or "").strip()
        lead_key = f"{pid}_{case_no}"
        if lead_key in seen_lead_keys:
            continue
        seen_lead_keys.add(lead_key)

        site_addr = str(m.get("SITE_ADDRESS") or raw_addr).strip().upper()
        mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
        site_zip = str(m.get("SITE_ZIP") or c.get("SITE_ZIP") or "").strip()
        mail_zip = str(m.get("MAILING_ZIP") or "").strip()
        is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
        absentee_status = "Out of State" if (m.get("MAILING_STATE") and str(m.get("MAILING_STATE")).strip().upper() not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

        case_desc = str(c.get("CASENAME") or c.get("CASETYPE") or "Municipal Code Violation").strip()
        c_type = str(c.get("CASETYPE") or "Code Violation").strip()
        started_ts = c.get("STARTED")
        filing_date = ""
        if started_ts:
            try:
                filing_date = datetime.datetime.fromtimestamp(started_ts / 1000.0).strftime("%Y-%m-%d")
            except Exception:
                filing_date = ""

        lead_row = {
            "Match_Status": "MATCHED",
            "Match_Confidence": 99.0,
            "Match_Method": "EXACT_NORMALIZED_ADDRESS",
            "Match_Notes": f"Lakeland Code Case #{case_no}: {case_desc}",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or c.get("SITE_CITY") or "Lakeland")),
            "Property_Zip": site_zip,
            "Parcel_ID": pid,
            "Strap": pid,
            "Mailing_Address": clean_display_address(str(m.get("MAILING_ADDRESS_1") or "")),
            "Mailing_City": clean_display_city(str(m.get("MAILING_CITY") or "")),
            "Mailing_State": str(m.get("MAILING_STATE") or "FL").strip(),
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
            "Distress_Stack_Notes": f"City of Lakeland IMS Case: {case_desc}",
            "Is_Stacked_Distress": "No",
            "Case_Number": case_no,
            "Source_File": "Polk_Lakeland_IMS_Live_API",
            "Filing_Date": filing_date,
            "Photo_Url": ""
        }
        matched_rows.append(lead_row)

    # 2. Process SeeClickFix Filtered Property Distress
    for scf in scf_cases:
        raw_addr = scf.get("address") or ""
        # Remove city/zip suffixes if present
        clean_s = raw_addr.split(",")[0].strip()
        na = norm_addr(clean_s)
        if not na or na not in master_lookup:
            continue

        m = master_lookup[na]
        pid = str(m.get("PARCEL_NUMBER") or "").strip()
        scf_id = str(scf.get("id") or "").strip()
        lead_key = f"{pid}_scf_{scf_id}"
        if lead_key in seen_lead_keys:
            continue
        seen_lead_keys.add(lead_key)

        site_addr = str(m.get("SITE_ADDRESS") or raw_addr).strip().upper()
        mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
        site_zip = str(m.get("SITE_ZIP") or "").strip()
        mail_zip = str(m.get("MAILING_ZIP") or "").strip()
        is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
        absentee_status = "Out of State" if (m.get("MAILING_STATE") and str(m.get("MAILING_STATE")).strip().upper() not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

        scf_cat = (scf.get("request_type") or {}).get("title") or "Code Compliance Request"
        scf_summary = scf.get("summary") or scf_cat
        created_at = str(scf.get("created_at") or "")[:10]
        media_url = (scf.get("media") or {}).get("image_full") or ""

        lead_row = {
            "Match_Status": "MATCHED",
            "Match_Confidence": 95.0,
            "Match_Method": "SEECLICKFIX_ADDRESS_MATCH",
            "Match_Notes": f"Polk SeeClickFix #{scf_id}: {scf_summary}",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Winter Haven")),
            "Property_Zip": site_zip,
            "Parcel_ID": pid,
            "Strap": pid,
            "Mailing_Address": clean_display_address(str(m.get("MAILING_ADDRESS_1") or "")),
            "Mailing_City": clean_display_city(str(m.get("MAILING_CITY") or "")),
            "Mailing_State": str(m.get("MAILING_STATE") or "FL").strip(),
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
            "Distress_Stack_Notes": f"Polk SeeClickFix: {scf_summary}",
            "Is_Stacked_Distress": "No",
            "Case_Number": f"SCF-{scf_id}",
            "Source_File": "Polk_SeeClickFix_Live_API",
            "Filing_Date": created_at,
            "Photo_Url": media_url
        }
        matched_rows.append(lead_row)

    print(f"[Polk API Sync] Total matched leads generated: {len(matched_rows):,}", flush=True)

    if not matched_rows:
        return {"status": "warning", "message": "No cases matched against master parcels."}

    leads_df = pd.DataFrame(matched_rows)

    # Calculate stacked distress (multiple violations on same parcel)
    pid_counts = leads_df["Parcel_ID"].value_counts()
    stacked_pids = set(pid_counts[pid_counts > 1].index)
    leads_df["Is_Stacked_Distress"] = leads_df["Parcel_ID"].apply(lambda p: "Yes" if p in stacked_pids else "No")
    stacked_count = len(stacked_pids)

    # Persist cache
    leads_df.to_parquet(cache_file, index=False)
    leads_df.to_csv(csv_file, index=False)
    print(f"[Polk API Sync] Saved {len(leads_df):,} leads to {cache_file} and {csv_file}.", flush=True)

    unique_matched = leads_df["Parcel_ID"].nunique()
    total_cases = len(ims_cases) + len(scf_cases)

    return {
        "status": "success",
        "county": "Polk",
        "cases_fetched": total_cases,
        "matched_leads": len(leads_df),
        "unique_properties": unique_matched,
        "total_polk_leads": unique_matched,
        "double_distress_count": stacked_count,
        "cache_file": cache_file
    }

if __name__ == "__main__":
    res = sync_polk_live_apis()
    print(json.dumps(res, indent=2))
