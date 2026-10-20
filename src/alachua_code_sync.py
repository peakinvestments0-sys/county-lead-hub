"""
Alachua County Live Code Enforcement & Distress API Sync Service
Direct integration with official Gainesville / Alachua County Code Enforcement ArcGIS REST Service:
https://services2.arcgis.com/Zzhtlau4ccHkQgTu/arcgis/rest/services/Gainesville_Code_Cases_Layer/FeatureServer/4/query

Pulls live municipal code enforcement cases, property maintenance orders,
dangerous structure warnings, and neglect citations across Gainesville,
Alachua, High Springs, Newberry, Hawthorne, and Archer.

Matches directly against Alachua Master Tax Parcels by Parcel_Number,
extracts owner names, mailing addresses, market values, and flags absentee status.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json
import re
import urllib.request
import urllib.parse
import pandas as pd

from src.normalizer import clean_display_address, clean_display_name, clean_display_city, normalize_address

ALACHUA_CODE_ENDPOINT = (
    "https://services2.arcgis.com/Zzhtlau4ccHkQgTu/arcgis/rest/services/"
    "Gainesville_Code_Cases_Layer/FeatureServer/4/query"
)

# Neglect & distress keywords (filter out roadside signs)
DISTRESS_KEYWORDS = [
    "maintenance", "building", "unsafe", "damage", "tree", "hazard", "weed",
    "grass", "overgrown", "derelict", "vacant", "abandon", "trash", "debris",
    "junk", "roof", "electrical", "heat", "unfit", "blight", "complaint"
]

def fetch_alachua_code_cases(max_records=5000):
    """Fetch recent property distress code cases from Alachua GIS API."""
    all_features = []
    offset = 0
    batch_size = 1000
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

    # Exclude signs; filter for 2024 through 2026 cases
    where_clause = "Type NOT LIKE 'Signs%' AND (File_Number LIKE '26-%' OR File_Number LIKE '25-%' OR File_Number LIKE '24-%' OR Status = 'Open')"

    print("[Alachua Code API] Fetching live cases from Gainesville / Alachua GIS...")
    while offset < max_records:
        params = {
            "where": where_clause,
            "outFields": "File_Number,Type,Description,Address,Parcel_Number,Status,Open_Date,Close_Date",
            "resultOffset": offset,
            "resultRecordCount": batch_size,
            "f": "json"
        }
        url = f"{ALACHUA_CODE_ENDPOINT}?{urllib.parse.urlencode(params)}"
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
            print(f"[Alachua Code API] Error at offset {offset}: {e}")
            break

    print(f"[Alachua Code API] Total records fetched: {len(all_features):,}")

    filtered = []
    for item in all_features:
        vtype = str(item.get("Type") or "").strip()
        desc = str(item.get("Description") or "").strip()
        full_text = f"{vtype} {desc}".lower()

        if any(kw in full_text for kw in DISTRESS_KEYWORDS) or item.get("Status") == "Open":
            pid = str(item.get("Parcel_Number") or "").strip()
            addr = str(item.get("Address") or "").strip()
            date_str = str(item.get("Open_Date") or "").strip()

            filtered.append({
                "File_Number": item.get("File_Number") or "",
                "Type": vtype,
                "Description": desc[:250],
                "Address": addr,
                "Parcel_Number": pid,
                "Status": item.get("Status") or "Active",
                "Open_Date": date_str
            })

    print(f"[Alachua Code API] Filtered to {len(filtered):,} property distress leads.")
    return filtered


def sync_alachua_live_apis():
    """
    Orchestrate Alachua County live distress sync:
    1. Fetch live code cases.
    2. Match against Alachua master parcels by Parcel_Number or Address.
    3. Persist to matched_leads_cache.parquet.
    """
    alachua_dir = os.path.join(BASE_DIR, "data", "FL", "alachua")
    cache_file = os.path.join(alachua_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(alachua_dir, "Alachua_Live_API_Distress_Leads.csv")

    cases = fetch_alachua_code_cases(max_records=5000)
    if not cases:
        return {"status": "warning", "message": "No live cases fetched from Alachua API."}

    parquet_path = os.path.join(alachua_dir, "RP_PROPERTY_INFO.parquet")
    if not os.path.exists(parquet_path):
        return {"status": "error", "message": f"Master parcel file not found at {parquet_path}"}

    print(f"[Alachua API Sync] Loading Alachua Master Parcels from {parquet_path}...")
    master_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    master_df = pd.read_parquet(parquet_path, columns=master_cols)
    master_df["PARCEL_NUMBER"] = master_df["PARCEL_NUMBER"].astype(str).str.strip()
    master_by_pid = master_df.drop_duplicates(subset=["PARCEL_NUMBER"]).set_index("PARCEL_NUMBER")

    master_df["NORM_ADDR"] = master_df["SITE_ADDRESS"].apply(normalize_address)
    master_by_addr = master_df.drop_duplicates(subset=["NORM_ADDR"]).set_index("NORM_ADDR")

    matched_rows = []
    for item in cases:
        pid = item.get("Parcel_Number", "").strip()
        m = None
        match_method = "EXACT_PARCEL_ID"

        if pid and pid in master_by_pid.index:
            m = master_by_pid.loc[pid]
        else:
            raw_addr = item.get("Address", "")
            norm_a = normalize_address(raw_addr.split("APT")[0].split("UNIT")[0].strip())
            if norm_a and norm_a in master_by_addr.index:
                m = master_by_addr.loc[norm_a]
                match_method = "EXACT_STREET_ADDRESS"

        if m is not None:
            actual_pid = str(m.get("PARCEL_NUMBER") or pid)
            site_addr = str(m.get("SITE_ADDRESS") or "").strip().upper()
            mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
            site_zip = str(m.get("SITE_ZIP") or "").strip()
            mail_zip = str(m.get("MAILING_ZIP") or "").strip()
            is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
            absentee_status = "Out of State" if (m.get("MAILING_STATE") and str(m.get("MAILING_STATE")).strip().upper() not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

            display_addr = clean_display_address(site_addr or item.get("Address", ""))
            lead_row = {
                "Match_Status": "MATCHED",
                "Match_Confidence": 100.0 if match_method == "EXACT_PARCEL_ID" else 95.0,
                "Match_Method": match_method,
                "Match_Notes": f"Alachua Code Case #{item.get('File_Number', '')}: {item.get('Type', '')}",
                "Clean_First_Name": "",
                "Clean_Last_Name": "",
                "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
                "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
                "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
                "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
                "County_Owner_2": clean_display_name(str(m.get("OWNER2") or "")),
                "Secondary_Owner": clean_display_name(str(m.get("OWNER2") or "")),
                "Property_Address": display_addr,
                "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Gainesville")),
                "Property_Zip": site_zip,
                "Parcel_ID": actual_pid,
                "Strap": str(m.get("STRAP") or actual_pid),
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
                "Property_Type": "Single Family" if "01" in str(m.get("PROPERTY_USE") or "") or "SINGLE" in str(m.get("PROPERTY_USE") or "").upper() else "Residential",
                "Property_Use": str(m.get("PROPERTY_USE") or "Residential"),
                "Legal_Description": str(m.get("LEGAL") or ""),
                "Lead_Type": "Code Violation",
                "Distress_Type": f"Code Violation / {item.get('Type', '')}",
                "Subject_Case_Number": item.get("File_Number", ""),
                "Subject_Status": item.get("Status", "Active"),
                "Subject_Comments": f"{item.get('Type', '')}: {item.get('Description', '')}",
                "Source_File": "Gainesville_Code_Enforcement_Live_API",
                "Photo_Url": "",
                "Is_Stacked_Distress": "No",
                "Distress_Stack_Notes": "",
                "Subject_Date": item.get("Open_Date", "")
            }
            matched_rows.append(lead_row)

    print(f"[Alachua API Sync] Total matched leads: {len(matched_rows):,}")

    combined = pd.DataFrame(matched_rows)
    if combined.empty:
        return {"status": "warning", "message": "No matched parcels found in current batch."}

    # Deduplicate by Parcel_ID
    combined = combined.drop_duplicates(subset=["Parcel_ID", "Lead_Type"], keep="last")

    # Harmonize pyarrow column types
    for col in combined.columns:
        if col in ["Market_Value", "Assessed_Value", "Taxable_Value", "Living_Sqft", "Year_Built", "Match_Confidence"]:
            combined[col] = pd.to_numeric(combined[col], errors="coerce").fillna(0.0)
        else:
            combined[col] = combined[col].astype(str).replace({"nan": "", "None": "", "<NA>": ""})

    combined.to_parquet(cache_file, index=False)
    combined.to_csv(csv_file, index=False)
    print(f"[Alachua API Sync] Saved {len(combined):,} leads to {cache_file}.")

    return {
        "status": "success",
        "cases_fetched": len(cases),
        "matched_leads": len(matched_rows),
        "total_alachua_leads": len(combined)
    }

if __name__ == "__main__":
    res = sync_alachua_live_apis()
    print("Sync Result:\n", json.dumps(res, indent=2))
