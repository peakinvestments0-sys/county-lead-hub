"""
Santa Rosa County (Milton, Gulf Breeze, Navarre, Pace, Jay)
Live Code Enforcement & Distress API Sync Service.

Direct integration with:
- Santa Rosa County Municipal SeeClickFix Filtered Property Distress Feeds.
- Matches against ~113k Santa Rosa County Master Parcels.
- Strictly filters out municipal infrastructure noise (potholes, streetlights, traffic signs).
- Retains genuine open code enforcement citations, structural hazards, unpermitted work, property neglect, blighted conditions, trash/debris dumping, and derelict structures.
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

SANTA_ROSA_SEECLICKFIX_CENTERS = [
    ("Milton", 30.6324, -87.0397),
    ("Gulf Breeze", 30.3571, -87.1639),
    ("Navarre", 30.4013, -86.8633),
    ("Pace", 30.5985, -87.1594),
    ("Jay", 30.9524, -87.1527)
]

SANTA_ROSA_CITIES = [
    'MILTON', 'GULF BREEZE', 'NAVARRE', 'PACE', 'JAY', 'SANTA ROSA'
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
    for city in SANTA_ROSA_CITIES:
        if u_clean.endswith(city):
            clean = clean[:len(clean) - len(city)].strip().rstrip(',')
            break
        if u_clean.endswith(", " + city) or u_clean.endswith("," + city):
            clean = clean.split(city)[0].strip().rstrip(',')
            break
    return clean.strip()

def fetch_santa_rosa_seeclickfix_distress():
    """Fetch and filter genuine property distress from SeeClickFix across Santa Rosa County."""
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

    for hub_name, lat, lng in SANTA_ROSA_SEECLICKFIX_CENTERS:
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
                print(f"[Santa Rosa SCF] Hub {hub_name} page {page} error: {e}", flush=True)
                break
            time.sleep(0.4)

    print(f"[Santa Rosa SCF] Harvested {len(total_issues)} property distress issues from SeeClickFix.", flush=True)
    return list(total_issues.values())

def sync_santa_rosa_leads(force_refresh=False):
    """
    Sync and match Santa Rosa County live distress feeds against master parcels.
    Outputs to data/FL/santa_rosa/matched_leads_cache.parquet.
    """
    leads_parquet = os.path.join(BASE_DIR, "data", "FL", "santa_rosa", "matched_leads_cache.parquet")
    parcels_parquet = os.path.join(BASE_DIR, "data", "FL", "santa_rosa", "RP_PROPERTY_INFO.parquet")

    if not os.path.exists(parcels_parquet):
        print(f"[Santa Rosa API Sync] Master parcel roll not found at {parcels_parquet}. Run parcel builder first.", flush=True)
        return {"status": "error", "message": "Master parcel roll not found"}

    print("[Santa Rosa API Sync] Loading Santa Rosa Master Parcels...", flush=True)
    t0 = time.time()
    parcels_df = pd.read_parquet(
        parcels_parquet,
        columns=[
            "PARCEL_NUMBER", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
            "OWNER1", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
            "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "YEAR_BUILT", "TOTAL_LIVING_SQFT", "LEGAL"
        ]
    )
    print(f"[Santa Rosa API Sync] Loaded {len(parcels_df):,} master parcels in {time.time()-t0:.2f}s", flush=True)

    parcels_df["NORM_ADDR"] = parcels_df["SITE_ADDRESS"].apply(norm_addr)
    addr_map = {}
    for idx, row in parcels_df.iterrows():
        n = row["NORM_ADDR"]
        if n and n not in addr_map:
            addr_map[n] = row

    scf_issues = fetch_santa_rosa_seeclickfix_distress()

    matched_rows = []

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
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Milton")),
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
            "Distress_Stack_Notes": f"Santa Rosa Property Distress: {scf_summary}",
            "Is_Stacked_Distress": "No",
            "Case_Number": f"SCF-{scf_id}",
            "Source_File": "Santa_Rosa_SeeClickFix_Live_API",
            "Filing_Date": created_at,
            "Photo_Url": media_url
        }
        matched_rows.append(lead_row)

    print(f"[Santa Rosa API Sync] Matched leads generated: {len(matched_rows):,}", flush=True)

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
        "county": "santa_rosa",
        "county_name": "Santa Rosa County",
        "total_leads": len(leads_df),
        "unique_properties": len(leads_df["Parcel_ID"].unique()),
        "stacked_distress_count": len(stacked_pids),
        "absentee_owners": int((leads_df["Is_Absentee"] == "Yes").sum()),
        "cache_file": leads_parquet,
        "cache_size_kb": round(file_size_kb, 1),
        "sync_timestamp": datetime.datetime.now().isoformat()
    }

    print(f"[Santa Rosa API Sync] COMPLETE: {stats['total_leads']:,} leads saved to {leads_parquet} ({file_size_kb:.1f} KB)", flush=True)
    return stats

if __name__ == "__main__":
    res = sync_santa_rosa_leads(force_refresh=True)
    print(json.dumps(res, indent=2))
