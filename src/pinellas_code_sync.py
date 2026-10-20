"""
Pinellas County Live API Sync Service
Direct dual integration with:
1. Official Pinellas County eGIS / Accela REST Service (Substantial Damage Assessments)
   Endpoint: https://services.arcgis.com/f5HgUpxURgEzTccH/arcgis/rest/services/SD_Parcels_for_Accela_view/FeatureServer/0/query
   Pulls FEMA/County building inspected substantially damaged properties (DeterminedSD=1, DamagePct >= 50%)
2. Pinellas County SeeClickFix Live REST API
   Endpoint: https://seeclickfix.com/api/v2/issues
   Pulls real-time citizen & inspector reported deferred maintenance, overgrown lots, illegal dumping, and structural violations across St. Petersburg, Clearwater, Largo, Pinellas Park, Seminole, etc.

Matches directly against Pinellas Master Parcel Database (437,559 parcels),
extracts owner names, mailing addresses, market values, and recomputes
Double/Triple Distress stacks against active court Lis Pendens and Probate records.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json
import time
import re
import urllib.request
import urllib.parse
import pandas as pd
import numpy as np

from src.normalizer import clean_display_address, clean_display_name, clean_display_city, normalize_address
from src.counties import get_county_paths
from src.data_loader import load_master_parcels
from src.matcher import CrossReferenceEngine

# -------------------------------------------------------------
# 1. API Endpoints
# -------------------------------------------------------------
PINELLAS_ACCELA_SD_ENDPOINT = (
    "https://services.arcgis.com/f5HgUpxURgEzTccH/arcgis/rest/services/"
    "SD_Parcels_for_Accela_view/FeatureServer/0/query"
)

PINELLAS_SCF_ENDPOINT = "https://seeclickfix.com/api/v2/issues"

# Bounding box for Pinellas County
PINELLAS_BBOX = {
    "min_lat": 27.65,
    "max_lat": 28.17,
    "min_lng": -82.88,
    "max_lng": -82.55
}

# Neglect & code violation keywords for SeeClickFix filtering
NEGLECT_KEYWORDS = [
    "trash", "dumping", "illegal dump", "grass", "overgrown", "weed",
    "debris", "boarded", "board", "broken", "unfit", "unsafe", "derelict",
    "fence", "roof", "damage", "tree", "abandoned", "abandon", "code",
    "compliance", "neglect", "blight", "clean", "vacant", "structure",
    "unpermitted", "squatter", "tall grass", "junk"
]

def fetch_accela_substantial_damage_parcels(max_records=10000):
    """
    Fetch all Determined Substantially Damaged properties from Pinellas County Accela eGIS API.
    """
    all_features = []
    offset = 0
    batch_size = 2000
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

    print("[Pinellas Accela API] Fetching Substantial Damage records from County eGIS...")
    while offset < max_records:
        params = {
            "where": "DeterminedSD=1",
            "outFields": "ParcelID,PotentialSD,DeterminedSD,DamagePct,Inspection_ID,last_edited_date",
            "resultOffset": offset,
            "resultRecordCount": batch_size,
            "f": "json"
        }
        url = f"{PINELLAS_ACCELA_SD_ENDPOINT}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
                features = data.get("features", [])
                if not features:
                    break
                all_features.extend([f.get("attributes", {}) for f in features])
                if len(features) < batch_size:
                    break
                offset += batch_size
        except Exception as e:
            print(f"[Pinellas Accela API] Error at offset {offset}: {e}")
            break

    print(f"[Pinellas Accela API] Total records fetched: {len(all_features):,}")
    return all_features


def fetch_pinellas_seeclickfix_issues(max_pages=3):
    """
    Fetch live citizen and municipal inspector issues across Pinellas County bounding box.
    """
    all_issues = []
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

    print("[Pinellas SeeClickFix API] Fetching live issues across Pinellas County...")
    for page in range(1, max_pages + 1):
        params = {
            "min_lat": PINELLAS_BBOX["min_lat"],
            "max_lat": PINELLAS_BBOX["max_lat"],
            "min_lng": PINELLAS_BBOX["min_lng"],
            "max_lng": PINELLAS_BBOX["max_lng"],
            "per_page": 100,
            "page": page
        }
        url = f"{PINELLAS_SCF_ENDPOINT}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                issues = data.get("issues", [])
                if not issues:
                    break
                all_issues.extend(issues)
        except Exception as e:
            print(f"[Pinellas SeeClickFix API] Error on page {page}: {e}")
            break

    print(f"[Pinellas SeeClickFix API] Total issues retrieved: {len(all_issues):,}")

    filtered = []
    for item in all_issues:
        summary = item.get("summary") or ""
        desc = item.get("description") or ""
        req_title = (item.get("request_type") or {}).get("title") or ""
        full_text = f"{summary} {desc} {req_title}".lower()

        if any(kw in full_text for kw in NEGLECT_KEYWORDS):
            addr = item.get("address") or ""
            # Must look like an address with digits
            if re.search(r"\d+", addr):
                media = item.get("media") or {}
                photo = media.get("image_full") or media.get("image_square_100x100") or ""
                filtered.append({
                    "Issue_ID": str(item.get("id")),
                    "Case Address": addr,
                    "Summary": summary,
                    "Description": desc[:250],
                    "Status": item.get("status") or "Open",
                    "Created_At": (item.get("created_at") or "")[:10],
                    "Lat": item.get("lat"),
                    "Lng": item.get("lng"),
                    "Photo_Url": photo,
                    "Source": "Pinellas_SeeClickFix_Live_API"
                })

    print(f"[Pinellas SeeClickFix API] Filtered to {len(filtered):,} property neglect/distress issues.")
    return filtered


def sync_pinellas_live_apis(db=None):
    """
    Main orchestration routine:
    1. Fetch Substantial Damage parcels from Pinellas County Accela eGIS API.
    2. Fetch live code violations from Pinellas SeeClickFix API.
    3. Cross-reference against 437,559 Pinellas master parcels.
    4. Merge into data/FL/pinellas/matched_leads_cache.parquet.
    5. Recompute Double/Triple Distress stacks.
    """
    pinellas_dir = os.path.join(BASE_DIR, "data", "FL", "pinellas")
    cache_file = os.path.join(pinellas_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(pinellas_dir, "Pinellas_Live_API_Distress_Leads.csv")

    # 1. Fetch from APIs
    accela_records = fetch_accela_substantial_damage_parcels(max_records=10000)
    scf_records = fetch_pinellas_seeclickfix_issues(max_pages=3)

    # 2. Load Master Parcels
    parquet_path = os.path.join(pinellas_dir, "RP_PROPERTY_INFO.parquet")
    print(f"[Pinellas API Sync] Loading Pinellas Master Parcels from {parquet_path}...")
    master_cols = [
        "CLEAN_PARCEL", "PARCEL_NUMBER", "STRAP", "CLEAN_STRAP",
        "SITE_ADDRESS", "STR_CITY", "STR_ZIP", "SITE_CITYZIP",
        "OWNER1", "OWNER2", "NORM_OWNER1",
        "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE",
        "TOTAL_LIVING_SQFT", "YEAR_BUILT", "PROPERTY_USE", "LEGAL", "OR_BOOK_PAGE", "NORM_ADDR"
    ]
    master_df = pd.read_parquet(parquet_path, columns=master_cols)

    # Build lookup dicts for speed
    master_by_pid = master_df.set_index("CLEAN_PARCEL")

    # 3. Process Accela Substantial Damage Leads
    print("[Pinellas API Sync] Matching Accela Substantial Damage parcels...")
    matched_accela_rows = []
    for r in accela_records:
        pid = str(r.get("ParcelID", "")).strip().replace("-", "").replace(" ", "")
        if pid in master_by_pid.index:
            m = master_by_pid.loc[pid]
            # Handle possible duplicate index in master
            if isinstance(m, pd.DataFrame):
                m = m.iloc[0]

            dmg_pct = r.get("DamagePct")
            insp_id = r.get("Inspection_ID")
            dmg_str = f"{dmg_pct:.1f}%" if dmg_pct is not None else ">=50%"

            # Check absentee
            site_addr = str(m.get("SITE_ADDRESS") or "").strip().upper()
            mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
            site_zip = str(m.get("STR_ZIP") or "").strip()
            mail_zip = str(m.get("MAILING_ZIP") or "").strip()
            is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
            absentee_status = "Out of State" if (m.get("MAILING_STATE") and str(m.get("MAILING_STATE")).strip().upper() not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

            lead_row = {
                "Match_Status": "MATCHED",
                "Match_Confidence": 100.0,
                "Match_Method": "DIRECT_PARCEL_ID",
                "Match_Notes": f"FEMA/County Assessed Substantial Damage ({dmg_str}) - Inspection #{insp_id}",
                "Clean_First_Name": "",
                "Clean_Last_Name": "",
                "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
                "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
                "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
                "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
                "County_Owner_2": clean_display_name(str(m.get("OWNER2") or "")),
                "Secondary_Owner": clean_display_name(str(m.get("OWNER2") or "")),
                "Property_Address": clean_display_address(str(m.get("SITE_ADDRESS") or "")),
                "Property_City": clean_display_city(str(m.get("STR_CITY") or "")),
                "Property_Zip": site_zip,
                "Parcel_ID": str(m.get("PARCEL_NUMBER") or pid),
                "Strap": str(m.get("STRAP") or ""),
                "Mailing_Address": clean_display_address(str(m.get("MAILING_ADDRESS_1") or "")),
                "Mailing_City": clean_display_city(str(m.get("MAILING_CITY") or "")),
                "Mailing_State": str(m.get("MAILING_STATE") or "FL").strip(),
                "Mailing_Zip": mail_zip,
                "Absentee_Status": absentee_status,
                "Is_Absentee": is_absentee,
                "Absentee_Priority": "High" if absentee_status == "Out of State" else ("Medium" if is_absentee == "Yes" else "Standard"),
                "Homestead_Exemption": "No",
                "Market_Value": float(m.get("CNTY_JST_VALUE") or 0.0),
                "Assessed_Value": float(m.get("CNTY_ASD_VALUE") or 0.0),
                "Taxable_Value": float(m.get("CNTY_TAXABLE_VALUE") or 0.0),
                "Year_Built": float(m.get("YEAR_BUILT") or 0.0),
                "Living_Sqft": float(m.get("TOTAL_LIVING_SQFT") or 0.0),
                "Property_Type": "Single Family" if "01" in str(m.get("PROPERTY_USE") or "") else "Residential",
                "Property_Use": str(m.get("PROPERTY_USE") or "Residential"),
                "County_Book_Page": str(m.get("OR_BOOK_PAGE") or ""),
                "Legal_Description": str(m.get("LEGAL") or ""),
                "Lead_Type": "Substantial Damage (Accela)",
                "Distress_Type": f"Hurricane/Storm Substantial Damage ({dmg_str})",
                "Subject_Case_Number": f"INSP-{insp_id}" if insp_id else "",
                "Subject_Status": "Determined Substantial Damage",
                "Subject_Comments": f"Physical Damage: {dmg_str}. FEMA Substantial Damage evaluation recorded.",
                "Source_File": "Pinellas_Accela_SubstantialDamage_API",
                "Is_Stacked_Distress": "No",
                "Distress_Stack_Notes": ""
            }
            matched_accela_rows.append(lead_row)

    print(f"[Pinellas API Sync] Accela matched leads: {len(matched_accela_rows):,}")

    # 4. Process SeeClickFix Leads
    matched_scf_rows = []
    if scf_records:
        print("[Pinellas API Sync] Matching SeeClickFix issues against master parcels...")
        city_strip_regex = re.compile(
            r"\b(ST\.?\s*PETERSBURG|SAINT\s*PETERSBURG|CLEARWATER|LARGO|PINELLAS\s*PARK|SEMINOLE|"
            r"DUNEDIN|TARPON\s*SPRINGS|SAFETY\s*HARBOR|GULFPORT|OLDSMAR|KENNETH\s*CITY|SOUTH\s*PASADENA|"
            r"MADEIRA\s*BEACH|INDIAN\s*ROCKS\s*BEACH|TREASURE\s*ISLAND|BELLEAIR)\b.*$",
            re.IGNORECASE
        )

        master_by_norm_addr = master_df.drop_duplicates(subset=["NORM_ADDR"]).set_index("NORM_ADDR")

        for item in scf_records:
            raw_addr = item.get("Case Address", "")
            # Strip trailing city / state / zip
            street_candidate = city_strip_regex.sub("", raw_addr).strip(" ,")
            if not street_candidate:
                street_candidate = raw_addr.split(",")[0].strip()

            norm_s = normalize_address(street_candidate)
            if norm_s and norm_s in master_by_norm_addr.index:
                m = master_by_norm_addr.loc[norm_s]
                if isinstance(m, pd.DataFrame):
                    m = m.iloc[0]

                pid = str(m.get("CLEAN_PARCEL") or "")
                site_addr = str(m.get("SITE_ADDRESS") or "").strip().upper()
                mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
                site_zip = str(m.get("STR_ZIP") or "").strip()
                mail_zip = str(m.get("MAILING_ZIP") or "").strip()
                is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
                absentee_status = "Out of State" if (m.get("MAILING_STATE") and str(m.get("MAILING_STATE")).strip().upper() not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

                lead_row = {
                    "Match_Status": "MATCHED",
                    "Match_Confidence": 95.0,
                    "Match_Method": "EXACT_STREET_ADDRESS",
                    "Match_Notes": f"Live Citizen/Inspector Code Issue: {item.get('Summary', '')}",
                    "Clean_First_Name": "",
                    "Clean_Last_Name": "",
                    "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
                    "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
                    "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
                    "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
                    "County_Owner_2": clean_display_name(str(m.get("OWNER2") or "")),
                    "Secondary_Owner": clean_display_name(str(m.get("OWNER2") or "")),
                    "Property_Address": clean_display_address(str(m.get("SITE_ADDRESS") or "")),
                    "Property_City": clean_display_city(str(m.get("STR_CITY") or "")),
                    "Property_Zip": site_zip,
                    "Parcel_ID": str(m.get("PARCEL_NUMBER") or pid),
                    "Strap": str(m.get("STRAP") or ""),
                    "Mailing_Address": clean_display_address(str(m.get("MAILING_ADDRESS_1") or "")),
                    "Mailing_City": clean_display_city(str(m.get("MAILING_CITY") or "")),
                    "Mailing_State": str(m.get("MAILING_STATE") or "FL").strip(),
                    "Mailing_Zip": mail_zip,
                    "Absentee_Status": absentee_status,
                    "Is_Absentee": is_absentee,
                    "Absentee_Priority": "High" if absentee_status == "Out of State" else ("Medium" if is_absentee == "Yes" else "Standard"),
                    "Homestead_Exemption": "No",
                    "Market_Value": float(m.get("CNTY_JST_VALUE") or 0.0),
                    "Assessed_Value": float(m.get("CNTY_ASD_VALUE") or 0.0),
                    "Taxable_Value": float(m.get("CNTY_TAXABLE_VALUE") or 0.0),
                    "Year_Built": float(m.get("YEAR_BUILT") or 0.0),
                    "Living_Sqft": float(m.get("TOTAL_LIVING_SQFT") or 0.0),
                    "Property_Type": "Single Family" if "01" in str(m.get("PROPERTY_USE") or "") else "Residential",
                    "Property_Use": str(m.get("PROPERTY_USE") or "Residential"),
                    "County_Book_Page": str(m.get("OR_BOOK_PAGE") or ""),
                    "Legal_Description": str(m.get("LEGAL") or ""),
                    "Lead_Type": "Code Violation",
                    "Distress_Type": "Live Municipal Code Violation / Neglect",
                    "Subject_Case_Number": f"SCF-{item.get('Issue_ID', '')}",
                    "Subject_Status": item.get("Status", "Open"),
                    "Subject_Comments": f"{item.get('Summary', '')}: {item.get('Description', '')}",
                    "Source_File": "Pinellas_SeeClickFix_Live_API",
                    "Photo_Url": item.get("Photo_Url", ""),
                    "Is_Stacked_Distress": "No",
                    "Distress_Stack_Notes": ""
                }
                matched_scf_rows.append(lead_row)

        print(f"[Pinellas API Sync] SeeClickFix matched leads: {len(matched_scf_rows):,}")

    # 5. Merge with existing leads in cache
    print("[Pinellas API Sync] Merging with existing cache...")
    if os.path.exists(cache_file):
        existing_df = pd.read_parquet(cache_file)
    else:
        existing_df = pd.DataFrame()

    new_leads_df = pd.DataFrame(matched_accela_rows + matched_scf_rows)

    if not existing_df.empty:
        # Keep legal filings (Probate, Lis Pendens) untouched
        legal_leads = existing_df[~existing_df["Lead_Type"].isin(["Substantial Damage (Accela)", "Code Violation"])].copy()
        prior_code = existing_df[existing_df["Lead_Type"] == "Code Violation"].copy()

        # Combine
        combined = pd.concat([legal_leads, prior_code, new_leads_df], ignore_index=True)
    else:
        combined = new_leads_df

    # Deduplicate by Parcel_ID and Lead_Type
    combined = combined.drop_duplicates(subset=["Parcel_ID", "Lead_Type"], keep="last")

    # 6. Recompute Double & Triple Distress Stacking
    print("[Pinellas API Sync] Recomputing Double & Triple Distress Stacks...")
    pids_sd = set(combined[combined["Lead_Type"] == "Substantial Damage (Accela)"]["Parcel_ID"].dropna())
    pids_code = set(combined[combined["Lead_Type"] == "Code Violation"]["Parcel_ID"].dropna())
    pids_lp = set(combined[combined["Lead_Type"].str.contains("lis|foreclose", case=False, na=False)]["Parcel_ID"].dropna())
    pids_probate = set(combined[combined["Lead_Type"].str.contains("probate|death", case=False, na=False)]["Parcel_ID"].dropna())

    def evaluate_distress(row):
        pid = row.get("Parcel_ID")
        lt = (row.get("Lead_Type") or "").lower()
        sig = []

        if "substantial damage" in lt:
            if pid in pids_lp: sig.append("Lis Pendens Foreclosure")
            if pid in pids_probate: sig.append("Probate Court Case")
            if pid in pids_code: sig.append("Municipal Code Violation")
            if len(sig) >= 2:
                return ("Yes", f"💥 TRIPLE DISTRESS: Substantial Damage + {' + '.join(sig)}")
            elif len(sig) == 1:
                return ("Yes", f"🔥 DOUBLE DISTRESS: Substantial Damage + {sig[0]}")
            return ("No", "")
        elif "code" in lt:
            if pid in pids_sd: sig.append("FEMA Substantial Damage Assessment")
            if pid in pids_lp: sig.append("Lis Pendens Foreclosure")
            if pid in pids_probate: sig.append("Probate Court Case")
            if len(sig) >= 2:
                return ("Yes", f"💥 TRIPLE DISTRESS: Code Violation + {' + '.join(sig)}")
            elif len(sig) == 1:
                return ("Yes", f"🔥 DOUBLE DISTRESS: Code Violation + {sig[0]}")
            return ("No", "")
        elif "lis" in lt:
            if pid in pids_sd: sig.append("FEMA Substantial Damage Assessment")
            if pid in pids_code: sig.append("Municipal Code Violation")
            if pid in pids_probate: sig.append("Probate Court Case")
            if len(sig) >= 2:
                return ("Yes", f"💥 TRIPLE DISTRESS: Lis Pendens + {' + '.join(sig)}")
            elif len(sig) == 1:
                return ("Yes", f"🔥 DOUBLE DISTRESS: Lis Pendens + {sig[0]}")
            return ("No", "")
        elif "probate" in lt:
            if pid in pids_sd: sig.append("FEMA Substantial Damage Assessment")
            if pid in pids_code: sig.append("Municipal Code Violation")
            if pid in pids_lp: sig.append("Lis Pendens Foreclosure")
            if len(sig) >= 2:
                return ("Yes", f"💥 TRIPLE DISTRESS: Probate + {' + '.join(sig)}")
            elif len(sig) == 1:
                return ("Yes", f"🔥 DOUBLE DISTRESS: Probate + {sig[0]}")
            return ("No", "")

        return ("No", "")

    stacks = [evaluate_distress(row) for _, row in combined.iterrows()]
    combined["Is_Stacked_Distress"] = [s[0] for s in stacks]
    combined["Distress_Stack_Notes"] = [s[1] for s in stacks]

    # Harmonize pyarrow column types
    for col in combined.columns:
        if col in ["Market_Value", "Assessed_Value", "Taxable_Value", "Living_Sqft", "Year_Built", "Match_Confidence"]:
            combined[col] = pd.to_numeric(combined[col], errors="coerce").fillna(0.0)
        else:
            combined[col] = combined[col].astype(str).replace({"nan": "", "None": "", "<NA>": ""})

    # Save to parquet cache
    combined.to_parquet(cache_file, index=False)
    print(f"[Pinellas API Sync] Saved {len(combined):,} total indexed records to {cache_file}.")

    # Save CSV export
    combined.to_csv(csv_file, index=False)

    double_distress_count = int((combined["Is_Stacked_Distress"] == "Yes").sum())
    sd_count = int((combined["Lead_Type"] == "Substantial Damage (Accela)").sum())
    code_count = int((combined["Lead_Type"] == "Code Violation").sum())

    return {
        "status": "success",
        "accela_records_fetched": len(accela_records),
        "accela_matched_leads": len(matched_accela_rows),
        "scf_issues_fetched": len(scf_records),
        "scf_matched_leads": len(matched_scf_rows),
        "total_pinellas_leads": len(combined),
        "substantial_damage_leads": sd_count,
        "code_violation_leads": code_count,
        "double_distress_count": double_distress_count
    }


if __name__ == "__main__":
    res = sync_pinellas_live_apis()
    print("Sync Result:\n", json.dumps(res, indent=2))
