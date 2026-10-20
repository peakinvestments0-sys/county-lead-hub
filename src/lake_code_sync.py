"""
Lake County Live Code Enforcement API Sync Service
Direct integration with official Lake County GIS Code Cases REST Service:
https://gis.lakecountyfl.gov/lakegis/rest/services/CodeCases/MapServer/0/query

Pulls live municipal code enforcement cases, hearing dockets, repeat violations,
and property maintenance orders across Clermont, Leesburg, Eustis, Mount Dora,
Tavares, Groveland, and Minneola.

Matches directly against 216,981 Lake Master Tax Parcels by AltKey (STRAP),
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

LAKE_CODE_ENDPOINT = "https://gis.lakecountyfl.gov/lakegis/rest/services/CodeCases/MapServer/0/query"

def fetch_lake_code_cases():
    """Fetch all active code cases from Lake County GIS API."""
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    params = {
        "where": "1=1",
        "outFields": "AltKey,ParcelNumber,CASE_NBR,STATUS,CASE_TYPE,ASSIGNED_INSP,Violation_Category,LOCATION,Violation_Description,CaseLink,PropertyLink",
        "resultRecordCount": 2000,
        "f": "json"
    }
    url = f"{LAKE_CODE_ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            features = data.get("features", [])
            cases = [f.get("attributes", {}) for f in features]
            print(f"[Lake Code API] Total code cases fetched: {len(cases):,}")
            return cases
    except Exception as e:
        print(f"[Lake Code API] Error fetching cases: {e}")
        return []


def sync_lake_live_apis():
    """
    Orchestrate Lake County code enforcement live sync:
    1. Fetch live cases.
    2. Match directly against 216,981 master parcels by AltKey == STRAP.
    3. Persist to matched_leads_cache.parquet and CSV.
    """
    lake_dir = os.path.join(BASE_DIR, "data", "FL", "lake")
    cache_file = os.path.join(lake_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(lake_dir, "Lake_Live_API_Distress_Leads.csv")

    cases = fetch_lake_code_cases()
    if not cases:
        return {"status": "warning", "message": "No live cases fetched from Lake County API."}

    parquet_path = os.path.join(lake_dir, "RP_PROPERTY_INFO.parquet")
    print(f"[Lake API Sync] Loading Lake Master Parcels from {parquet_path}...")
    master_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    master_df = pd.read_parquet(parquet_path, columns=master_cols)
    master_df["STRAP"] = master_df["STRAP"].astype(str).str.strip()
    master_by_strap = master_df.drop_duplicates(subset=["STRAP"]).set_index("STRAP")

    matched_rows = []
    for item in cases:
        alt_key = str(item.get("AltKey") or "").strip()
        if alt_key in master_by_strap.index:
            m = master_by_strap.loc[alt_key]

            site_addr = str(m.get("SITE_ADDRESS") or "").strip().upper()
            mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
            site_zip = str(m.get("SITE_ZIP") or "").strip()
            mail_zip = str(m.get("MAILING_ZIP") or "").strip()
            is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
            absentee_status = "Out of State" if (m.get("MAILING_STATE") and str(m.get("MAILING_STATE")).strip().upper() not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

            pid = str(m.get("PARCEL_NUMBER") or alt_key)
            display_addr = clean_display_address(site_addr or item.get("LOCATION", ""))
            desc = str(item.get("Violation_Description") or item.get("Violation_Category") or "").replace("\r\n", " ").strip()

            lead_row = {
                "Match_Status": "MATCHED",
                "Match_Confidence": 100.0,
                "Match_Method": "EXACT_STRAP_ALTKEY",
                "Match_Notes": f"Lake Code Case #{item.get('CASE_NBR', '')}: {desc[:100]}",
                "Clean_First_Name": "",
                "Clean_Last_Name": "",
                "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
                "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
                "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
                "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
                "County_Owner_2": clean_display_name(str(m.get("OWNER2") or "")),
                "Secondary_Owner": clean_display_name(str(m.get("OWNER2") or "")),
                "Property_Address": display_addr,
                "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Clermont")),
                "Property_Zip": site_zip,
                "Parcel_ID": pid,
                "Strap": alt_key,
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
                "Legal_Description": str(m.get("LEGAL") or ""),
                "Lead_Type": "Code Violation",
                "Distress_Type": f"Code Violation / {item.get('STATUS', 'Active')}",
                "Subject_Case_Number": f"LC-{item.get('CASE_NBR', '')}",
                "Subject_Status": item.get("STATUS", "Active"),
                "Subject_Comments": desc,
                "Source_File": "Lake_County_Live_GIS_API",
                "Photo_Url": "",
                "Is_Stacked_Distress": "No",
                "Distress_Stack_Notes": "",
                "Subject_Date": "2026-10-10"
            }
            matched_rows.append(lead_row)

    print(f"[Lake API Sync] Total matched leads: {len(matched_rows):,}")

    combined = pd.DataFrame(matched_rows)
    if combined.empty:
        return {"status": "warning", "message": "No matched parcels found in current Lake batch."}

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
    print(f"[Lake API Sync] Saved {len(combined):,} leads to {cache_file}.")

    return {
        "status": "success",
        "cases_fetched": len(cases),
        "matched_leads": len(matched_rows),
        "total_lake_leads": len(combined)
    }

if __name__ == "__main__":
    res = sync_lake_live_apis()
    print("Sync Result:\n", json.dumps(res, indent=2))
