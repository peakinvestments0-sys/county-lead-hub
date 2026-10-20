"""
Collier County Live Distress & Milestone Safety API Sync Service
Direct integration with:
1. Collier County GIS Milestone Structural Inspection FeatureServer (FL SB 4-D Compliance):
   https://services2.arcgis.com/SlIq32SqARUHIhSx/arcgis/rest/services/MilestoneMap/FeatureServer/2
2. Collier County & City of Naples SeeClickFix Filtered Property Distress Feeds.

Matches against ~368k Collier County Master Parcels (Naples, Marco Island, Immokalee).
Strictly filters out municipal infrastructure noise (potholes, streetlights, traffic signs).
Retains genuine structural milestone delinquencies, unsafe buildings, and property neglect.
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

COLLIER_MILESTONE_ENDPOINT = "https://services2.arcgis.com/SlIq32SqARUHIhSx/arcgis/rest/services/MilestoneMap/FeatureServer/2/query"

COLLIER_SEECLICKFIX_CENTERS = [
    ("Naples", 26.1420, -81.7948),
    ("North Naples", 26.2554, -81.7826),
    ("Marco Island", 25.9406, -81.7148),
    ("Immokalee", 26.4187, -81.4192),
    ("East Naples", 26.1265, -81.7450)
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
        ' TRAIL': ' TRL', ' WAY': ' WAY'
    }
    for k, v in replacements.items():
        a = a.replace(k, v)
    return a.strip()

def extract_street_address(loc_str):
    """Extract clean street address from Collier permit location strings like '35 Bluebill AVE B, (BLDG) , Naples'."""
    if not loc_str:
        return ""
    # Remove building suffixes and city
    cleaned = re.sub(r'\(BLDG\)', '', loc_str, flags=re.I)
    cleaned = re.sub(r',.*$', '', cleaned) # Take part before first comma
    # Remove unit/suite markers at the end
    cleaned = re.sub(r'\b(BLDG|UNIT|APT|STE|SUITE|LOT|FL)\b.*$', '', cleaned, flags=re.I)
    return norm_addr(cleaned)

def fetch_collier_milestone_cases():
    """Fetch structural milestone inspection records from Collier County GIS."""
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    params = {
        "where": "1=1",
        "outFields": "OBJECTID,PermitNumber,ApplicationName,AssociationName,Application_Status,ApplicationStatus,NextMilestoneInspectionYear,PermitLocation,SiteAddressID",
        "returnGeometry": "false",
        "resultRecordCount": "2000",
        "f": "json"
    }
    url = f"{COLLIER_MILESTONE_ENDPOINT}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            features = data.get("features", [])
            cases = [f.get("attributes", {}) for f in features]
            print(f"[Collier API Sync] Milestone inspection records fetched: {len(cases):,}", flush=True)
            return cases
    except Exception as e:
        print(f"[Collier API Sync] Error fetching Milestone records: {e}", flush=True)
        return []

def fetch_collier_seeclickfix_distress():
    """Fetch and filter genuine property distress from SeeClickFix across Collier County."""
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    total_issues = {}

    noise_keywords = [
        "pothole", "street light", "streetlight", "traffic light", "traffic signal",
        "sidewalk", "curb", "playground", "park", "drainage", "storm drain",
        "dead animal", "sign request", "street sign", "speeding", "traffic calming"
    ]

    for name, lat, lng in COLLIER_SEECLICKFIX_CENTERS:
        for page in range(1, 3):
            url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=100&page={page}"
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    issues = data.get("issues", [])
                    if not issues:
                        break
                    for issue in issues:
                        iid = issue.get("id")
                        if not iid or iid in total_issues:
                            continue
                        summary = str(issue.get("summary") or "").lower()
                        desc = str(issue.get("description") or "").lower()
                        cat = str((issue.get("request_type") or {}).get("title") or "").lower()
                        full_text = f"{summary} {desc} {cat}"

                        # Strictly filter out municipal noise
                        if any(n in full_text for n in noise_keywords):
                            continue

                        # Retain genuine property distress
                        distress_indicators = [
                            "trash", "debris", "overgrown", "grass", "blight", "dumping",
                            "abandoned", "derelict", "unsafe", "damage", "squatter",
                            "boarded", "roof", "hazard", "nuisance", "structure",
                            "unpermitted", "violation", "code enforcement", "water heater"
                        ]
                        if any(d in full_text for d in distress_indicators):
                            total_issues[iid] = issue
            except Exception as e:
                print(f"[Collier API Sync] Error fetching SeeClickFix for {name}: {e}", flush=True)
                break

    print(f"[Collier API Sync] SeeClickFix filtered distress issues: {len(total_issues):,}", flush=True)
    return list(total_issues.values())

def sync_collier_leads(force_refresh=False):
    """
    Synchronize Collier County Distress feeds, join with Master Parcels,
    and persist into matched_leads_cache.parquet.
    """
    collier_dir = os.path.join(BASE_DIR, "data", "FL", "collier")
    master_parquet = os.path.join(collier_dir, "RP_PROPERTY_INFO.parquet")
    leads_parquet = os.path.join(collier_dir, "matched_leads_cache.parquet")

    if not os.path.exists(master_parquet):
        return {
            "status": "error",
            "message": f"Master parcel file not found at {master_parquet}. Run build_collier_parcels.py first."
        }

    print("[Collier API Sync] Loading Collier County Master Parcels...", flush=True)
    master_cols = [
        "PARCEL_NUMBER", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    df_master = pd.read_parquet(master_parquet, columns=master_cols)
    print(f"[Collier API Sync] Loaded {len(df_master):,} master parcels.", flush=True)

    # Build address lookup
    addr_lookup = {}
    for row in df_master.to_dict(orient="records"):
        s_addr = norm_addr(row.get("SITE_ADDRESS") or "")
        if s_addr:
            addr_lookup[s_addr] = row

    # Fetch live cases
    milestones = fetch_collier_milestone_cases()
    scf_cases = fetch_collier_seeclickfix_distress()

    matched_rows = []
    seen_lead_keys = set()

    # 1. Process Milestone Structural Inspections
    for mcase in milestones:
        raw_loc = mcase.get("PermitLocation") or ""
        norm_loc = extract_street_address(raw_loc)
        pnum = str(mcase.get("PermitNumber") or "").strip()
        app_status = str(mcase.get("Application_Status") or "").strip()
        assoc_name = str(mcase.get("AssociationName") or "").strip()
        app_name = str(mcase.get("ApplicationName") or "").strip()

        # Prioritize delinquent and open milestone reviews
        is_delinquent = "Delinquent" in app_status
        lead_type = "Milestone Delinquent" if is_delinquent else "Structural Inspection"

        m = addr_lookup.get(norm_loc)
        if not m:
            continue

        pid = str(m.get("PARCEL_NUMBER") or "").strip()
        lead_key = f"{pid}_ms_{pnum}"
        if lead_key in seen_lead_keys:
            continue
        seen_lead_keys.add(lead_key)

        site_addr = str(m.get("SITE_ADDRESS") or raw_loc).strip().upper()
        mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
        site_zip = str(m.get("SITE_ZIP") or "").strip()
        mail_zip = str(m.get("MAILING_ZIP") or "").strip()

        is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
        mail_state = str(m.get("MAILING_STATE") or "FL").strip().upper()
        absentee_status = "Out of State" if (mail_state and mail_state not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

        notes = f"FL SB 4-D Milestone Safety: {app_status} ({assoc_name or app_name})"

        lead_row = {
            "Match_Status": "MATCHED",
            "Match_Confidence": 98.0,
            "Match_Method": "EXACT_NORMALIZED_ADDRESS",
            "Match_Notes": f"Collier Milestone #{pnum}: {notes}",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or assoc_name)),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or assoc_name)),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Naples")),
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
            "Lead_Type": lead_type,
            "All_Lead_Types": [lead_type],
            "Distress_Stack_Notes": notes,
            "Is_Stacked_Distress": "No",
            "Case_Number": pnum,
            "Source_File": "Collier_GIS_Milestone_API",
            "Filing_Date": "",
            "Photo_Url": ""
        }
        matched_rows.append(lead_row)

    # 2. Process SeeClickFix Filtered Property Distress
    for scf in scf_cases:
        raw_addr = scf.get("address") or ""
        clean_s = raw_addr.split(",")[0].strip()
        na = norm_addr(clean_s)
        if not na or na not in addr_lookup:
            continue

        m = addr_lookup[na]
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
        mail_state = str(m.get("MAILING_STATE") or "FL").strip().upper()
        absentee_status = "Out of State" if (mail_state and mail_state not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

        scf_cat = (scf.get("request_type") or {}).get("title") or "Property Distress"
        scf_summary = scf.get("summary") or scf_cat
        created_at = str(scf.get("created_at") or "")[:10]
        media_url = (scf.get("media") or {}).get("image_full") or ""

        lead_row = {
            "Match_Status": "MATCHED",
            "Match_Confidence": 95.0,
            "Match_Method": "SEECLICKFIX_ADDRESS_MATCH",
            "Match_Notes": f"Collier SeeClickFix #{scf_id}: {scf_summary}",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Naples")),
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
            "Distress_Stack_Notes": f"Collier Property Distress: {scf_summary}",
            "Is_Stacked_Distress": "No",
            "Case_Number": f"SCF-{scf_id}",
            "Source_File": "Collier_SeeClickFix_Live_API",
            "Filing_Date": created_at,
            "Photo_Url": media_url
        }
        matched_rows.append(lead_row)

    print(f"[Collier API Sync] Matched leads generated: {len(matched_rows):,}", flush=True)

    if not matched_rows:
        return {"status": "warning", "message": "No cases matched against master parcels."}

    leads_df = pd.DataFrame(matched_rows)

    # Calculate stacked distress (multiple violations on same parcel)
    pid_counts = leads_df["Parcel_ID"].value_counts()
    stacked_pids = set(pid_counts[pid_counts > 1].index)
    leads_df["Is_Stacked_Distress"] = leads_df["Parcel_ID"].apply(lambda x: "Yes" if x in stacked_pids else "No")

    # Update All_Lead_Types for stacked records
    for p_id in stacked_pids:
        sub = leads_df[leads_df["Parcel_ID"] == p_id]
        types_combined = sorted(list(set(sub["Lead_Type"].tolist())))
        for idx in sub.index:
            leads_df.at[idx, "All_Lead_Types"] = types_combined

    # Save to Parquet cache
    leads_df.to_parquet(leads_parquet, index=False)
    file_size_kb = os.path.getsize(leads_parquet) / 1024

    stats = {
        "status": "success",
        "county": "collier",
        "county_name": "Collier County",
        "total_leads": len(leads_df),
        "unique_properties": len(leads_df["Parcel_ID"].unique()),
        "stacked_distress_count": len(stacked_pids),
        "absentee_owners": int((leads_df["Is_Absentee"] == "Yes").sum()),
        "cache_file": leads_parquet,
        "cache_size_kb": round(file_size_kb, 1),
        "sync_timestamp": datetime.datetime.now().isoformat()
    }

    print(f"[Collier API Sync] COMPLETE: {stats['total_leads']:,} leads ({stats['unique_properties']:,} properties) saved to {leads_parquet} ({file_size_kb:.1f} KB)", flush=True)
    return stats

if __name__ == "__main__":
    res = sync_collier_leads(force_refresh=True)
    print(json.dumps(res, indent=2))
