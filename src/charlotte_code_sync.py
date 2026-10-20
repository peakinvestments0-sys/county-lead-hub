"""
Charlotte County Live Code Enforcement & Distress API Sync Service
Direct integration with Charlotte County Community Development ArcGIS REST Service:
https://agis3.charlottecountyfl.gov/arcgis/rest/services/Internal/CCGIS_ComDev_Internal/MapServer/167/query

Pulls real-time municipal code violations, FEMA storm damage orders, unpermitted
structures, derelict properties, and lot neglect across Port Charlotte, Punta Gorda,
Englewood, Rotonda West, and Charlotte Harbor.

Matches directly against 223,248 Charlotte Master Tax Parcels by ACCOUNT (Parcel ID),
extracts owner names, mailing addresses, market values, and flags absentee status.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json
import re
import datetime
import urllib.request
import urllib.parse
import pandas as pd

from src.normalizer import clean_display_address, clean_display_name, clean_display_city, normalize_address

CHARLOTTE_CODE_ENDPOINT = (
    "https://agis3.charlottecountyfl.gov/arcgis/rest/services/"
    "Internal/CCGIS_ComDev_Internal/MapServer/167/query"
)

# Neglect & code violation keywords to keep only property distress
DISTRESS_KEYWORDS = [
    "damage", "hurricane", "fema", "roof", "permit", "shed", "unpermitted",
    "structure", "abandon", "vacant", "junk", "trash", "debris", "weed",
    "grass", "hazard", "unsafe", "unfit", "board", "overgrown", "derelict",
    "blight", "septic", "water", "camper", "trailer", "rv", "squatter", "demolition"
]

def fetch_charlotte_code_cases(max_records=5000):
    """Fetch recent code enforcement cases from Charlotte County GIS API."""
    all_features = []
    offset = 0
    batch_size = 1000
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

    # Filter for cases from 2024 through 2026
    where_clause = "RECORD_ID LIKE '%-26-%' OR RECORD_ID LIKE '%-25-%' OR RECORD_ID LIKE '%-24-%'"

    print("[Charlotte Code API] Fetching live cases from Charlotte County ComDev...")
    while offset < max_records:
        params = {
            "where": where_clause,
            "outFields": "RECORD_ID,DESCRIPTION,DATE_OPENED,RECORD_STATUS,RECORD_TYPE,ACCOUNT,STANDARD",
            "resultOffset": offset,
            "resultRecordCount": batch_size,
            "f": "json"
        }
        url = f"{CHARLOTTE_CODE_ENDPOINT}?{urllib.parse.urlencode(params)}"
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
            print(f"[Charlotte Code API] Error at offset {offset}: {e}")
            break

    print(f"[Charlotte Code API] Total records fetched: {len(all_features):,}")

    filtered = []
    for item in all_features:
        desc = str(item.get("DESCRIPTION") or "").strip()
        rtype = str(item.get("RECORD_TYPE") or "").strip()
        full_text = f"{desc} {rtype}".lower()

        # Retain actionable property distress leads
        if any(kw in full_text for kw in DISTRESS_KEYWORDS) or "not high grass only" in full_text:
            account = str(item.get("ACCOUNT") or "").strip()
            if account and account != "None":
                date_ms = item.get("DATE_OPENED")
                filing_date = ""
                if date_ms and str(date_ms).isdigit():
                    try:
                        filing_date = datetime.datetime.fromtimestamp(int(date_ms) / 1000).strftime("%Y-%m-%d")
                    except Exception:
                        filing_date = "2026-10-10"

                filtered.append({
                    "Record_ID": item.get("RECORD_ID") or "",
                    "Account": account,
                    "Address": item.get("STANDARD") or "",
                    "Description": desc[:250],
                    "Status": item.get("RECORD_STATUS") or "Active",
                    "Record_Type": rtype,
                    "Filing_Date": filing_date
                })

    print(f"[Charlotte Code API] Filtered to {len(filtered):,} property distress leads.")
    return filtered


def sync_charlotte_live_apis():
    """
    Orchestrate Charlotte County code enforcement live sync:
    1. Fetch live cases.
    2. Match directly against 223,248 master parcels by ACCOUNT == PARCEL_NUMBER.
    3. Persist to matched_leads_cache.parquet and CSV.
    """
    charlotte_dir = os.path.join(BASE_DIR, "data", "FL", "charlotte")
    cache_file = os.path.join(charlotte_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(charlotte_dir, "Charlotte_Live_API_Distress_Leads.csv")

    cases = fetch_charlotte_code_cases(max_records=5000)
    if not cases:
        return {"status": "warning", "message": "No live cases fetched from Charlotte API."}

    parquet_path = os.path.join(charlotte_dir, "RP_PROPERTY_INFO.parquet")
    print(f"[Charlotte API Sync] Loading Charlotte Master Parcels from {parquet_path}...")
    master_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    master_df = pd.read_parquet(parquet_path, columns=master_cols)
    master_df["PARCEL_NUMBER"] = master_df["PARCEL_NUMBER"].astype(str).str.strip()
    master_by_pid = master_df.drop_duplicates(subset=["PARCEL_NUMBER"]).set_index("PARCEL_NUMBER")

    matched_rows = []
    for item in cases:
        pid = item.get("Account", "").strip()
        if pid in master_by_pid.index:
            m = master_by_pid.loc[pid]

            site_addr = str(m.get("SITE_ADDRESS") or "").strip().upper()
            mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
            site_zip = str(m.get("SITE_ZIP") or "").strip()
            mail_zip = str(m.get("MAILING_ZIP") or "").strip()
            is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
            absentee_status = "Out of State" if (m.get("MAILING_STATE") and str(m.get("MAILING_STATE")).strip().upper() not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

            display_addr = clean_display_address(site_addr or item.get("Address", ""))
            lead_row = {
                "Match_Status": "MATCHED",
                "Match_Confidence": 100.0,
                "Match_Method": "EXACT_PARCEL_ID",
                "Match_Notes": f"Charlotte Code Case: {item.get('Description', '')}",
                "Clean_First_Name": "",
                "Clean_Last_Name": "",
                "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
                "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
                "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
                "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
                "County_Owner_2": clean_display_name(str(m.get("OWNER2") or "")),
                "Secondary_Owner": clean_display_name(str(m.get("OWNER2") or "")),
                "Property_Address": display_addr,
                "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Port Charlotte")),
                "Property_Zip": site_zip,
                "Parcel_ID": pid,
                "Strap": str(m.get("STRAP") or pid),
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
                "Property_Type": "Single Family" if "100" in str(m.get("PROPERTY_USE") or "") or "01" in str(m.get("PROPERTY_USE") or "") else "Residential",
                "Property_Use": str(m.get("PROPERTY_USE") or "Residential"),
                "Legal_Description": str(m.get("LEGAL") or ""),
                "Lead_Type": "Code Violation",
                "Distress_Type": f"Code Violation / {item.get('Record_Type', '')}",
                "Subject_Case_Number": item.get("Record_ID", ""),
                "Subject_Status": item.get("Status", "Active"),
                "Subject_Comments": item.get("Description", ""),
                "Source_File": "Charlotte_County_Live_GIS_API",
                "Photo_Url": "",
                "Is_Stacked_Distress": "No",
                "Distress_Stack_Notes": "",
                "Subject_Date": item.get("Filing_Date", "")
            }
            matched_rows.append(lead_row)

    print(f"[Charlotte API Sync] Total matched leads: {len(matched_rows):,}")

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
    print(f"[Charlotte API Sync] Saved {len(combined):,} leads to {cache_file}.")

    return {
        "status": "success",
        "cases_fetched": len(cases),
        "matched_leads": len(matched_rows),
        "total_charlotte_leads": len(combined)
    }

if __name__ == "__main__":
    res = sync_charlotte_live_apis()
    print("Sync Result:\n", json.dumps(res, indent=2))
