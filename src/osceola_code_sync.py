"""
Osceola County Live Structural Damage & Property Distress API Sync Service
Direct integration with official Osceola County & City of Kissimmee Emergency Management FeatureServers:
- Geocoding_IDAresidentialdata: https://services2.arcgis.com/fwC5h1qdAfuCSfet/arcgis/rest/services/Geocoding_IDAresidentialdata/FeatureServer/0/query
- Geocoding_residentialmajor: https://services2.arcgis.com/fwC5h1qdAfuCSfet/arcgis/rest/services/Geocoding_residentialmajor/FeatureServer/0/query

Pulls official post-storm municipal structural damage inspections, uninhabitable units,
damaged roofs, flooding impacts, and major distress across Kissimmee, St. Cloud, Poinciana, and Celebration.
Matches directly against Osceola Master Parcels (210,878 properties) by Parcel_Ide (Strap).
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
from datetime import datetime
import pandas as pd

from src.normalizer import clean_display_address, clean_display_name, clean_display_city, normalize_address

OSCEOLA_IDA_ENDPOINT = (
    "https://services2.arcgis.com/fwC5h1qdAfuCSfet/arcgis/rest/services/"
    "Geocoding_IDAresidentialdata/FeatureServer/0/query"
)

OSCEOLA_MAJOR_ENDPOINT = (
    "https://services2.arcgis.com/fwC5h1qdAfuCSfet/arcgis/rest/services/"
    "Geocoding_residentialmajor/FeatureServer/0/query"
)

def fetch_osceola_damage_records(max_records=10000):
    """Fetch official municipal structural damage assessments from Osceola County services."""
    all_features = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # 1. Fetch IDA residential data
    offset = 0
    batch_size = 2000
    print("[Osceola Damage API] Fetching live residential inspections from Osceola County...")
    while offset < max_records:
        params = {
            "where": "Parcel_Ide IS NOT NULL",
            "outFields": "Parcel_Ide,Damage_Lev,Estimated,Improved_V,Owner_Name,Address,City_1,Comments,Inspector",
            "resultOffset": str(offset),
            "resultRecordCount": str(batch_size),
            "f": "json"
        }
        url = f"{OSCEOLA_IDA_ENDPOINT}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                features = data.get("features", [])
                if not features:
                    break
                records = [f.get("attributes", {}) for f in features]
                all_features.extend(records)
                print(f"[Osceola Damage API] Retrieved {len(records):,} records (offset {offset:,})")
                if len(features) < batch_size:
                    break
                offset += batch_size
        except Exception as e:
            print(f"[Osceola Damage API] Error fetching offset {offset}: {e}")
            break

    # 2. Fetch Major residential damage data
    try:
        params = {
            "where": "PropertyID IS NOT NULL",
            "outFields": "PropertyID,Damage_Lev,Estimated,Improved_V,OwnerName,Address,City_1,ResidenceT",
            "resultRecordCount": "2000",
            "f": "json"
        }
        url = f"{OSCEOLA_MAJOR_ENDPOINT}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for f in data.get("features", []):
                attr = f.get("attributes", {})
                all_features.append({
                    "Parcel_Ide": attr.get("PropertyID"),
                    "Damage_Lev": attr.get("Damage_Lev", "Major"),
                    "Estimated": attr.get("Estimated"),
                    "Improved_V": attr.get("Improved_V"),
                    "Owner_Name": attr.get("OwnerName"),
                    "Address": attr.get("Address"),
                    "City_1": attr.get("City_1", "Kissimmee"),
                    "Comments": f"Major Residential Damage: {attr.get('ResidenceT', '')}",
                    "Inspector": "Osceola OEM / Appraiser"
                })
    except Exception as e:
        print(f"[Osceola Damage API] Error querying Major damage endpoint: {e}")

    print(f"[Osceola Damage API] Total records downloaded: {len(all_features):,}")

    filtered = []
    for item in all_features:
        pid = str(item.get("Parcel_Ide") or "").strip()
        damage_type = str(item.get("Damage_Lev") or "").strip()
        raw_est = str(item.get("Estimated") or "0").replace(",", "").strip()
        try:
            est_loss = float(raw_est)
        except Exception:
            est_loss = 0.0

        if not pid or pid in ["None", ""]:
            continue

        comments = str(item.get("Comments") or "").strip()
        desc = f"{damage_type} structural damage"
        if est_loss > 0:
            desc += f" (Est. Loss: ${est_loss:,.0f})"
        if comments:
            desc += f" | {comments}"

        filtered.append({
            "Parcel_Number": pid,
            "Damage_Type": damage_type or "Affected",
            "Description": desc[:300],
            "Loss_Amount": est_loss,
            "Address": str(item.get("Address") or "").strip(),
            "City": str(item.get("City_1") or "Kissimmee").strip(),
            "Source": "Osceola_County_Damage_Assessments_API"
        })

    print(f"[Osceola Damage API] Filtered to {len(filtered):,} actionable distress cases.")
    return filtered


def sync_osceola_live_apis():
    """
    Orchestrate Osceola County live distress sync:
    1. Fetch live structural damage inspections from Osceola API.
    2. Match against Osceola master parcels by Strap (Parcel_Ide).
    3. Persist to matched_leads_cache.parquet and CSV.
    """
    osceola_dir = os.path.join(BASE_DIR, "data", "FL", "osceola")
    osceola_cache = os.path.join(osceola_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(osceola_dir, "Osceola_Live_API_Distress_Leads.csv")

    cases = fetch_osceola_damage_records()
    if not cases:
        return {"status": "warning", "message": "No live damage cases fetched from Osceola API."}

    parquet_path = os.path.join(osceola_dir, "RP_PROPERTY_INFO.parquet")
    if not os.path.exists(parquet_path):
        return {"status": "error", "message": f"Master parcel file not found at {parquet_path}"}

    print(f"[Osceola API Sync] Loading Osceola Master Parcels from {parquet_path}...")
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
        pid = item.get("Parcel_Number", "").strip()
        m = None

        if pid and pid in master_by_pid.index:
            m = master_by_pid.loc[pid]

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
                "Match_Confidence": 100.0,
                "Match_Method": "EXACT_PARCEL_ID",
                "Match_Notes": f"Osceola Structural Damage: {item.get('Damage_Type', '')} (${item.get('Loss_Amount', 0):,.0f} loss)",
                "Clean_First_Name": "",
                "Clean_Last_Name": "",
                "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
                "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
                "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
                "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
                "County_Owner_2": clean_display_name(str(m.get("OWNER2") or "")),
                "Secondary_Owner": clean_display_name(str(m.get("OWNER2") or "")),
                "Property_Address": display_addr,
                "Property_City": clean_display_city(str(m.get("SITE_CITY") or item.get("City", "Kissimmee"))),
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
                "Property_Type": "Single Family" if "11" in str(m.get("PROPERTY_USE") or "") or "SINGLE" in str(m.get("PROPERTY_USE") or "").upper() else "Residential",
                "Property_Use": str(m.get("PROPERTY_USE") or "Residential"),
                "Legal_Description": str(m.get("LEGAL") or ""),
                "Lead_Type": "Substantial Damage",
                "Distress_Type": f"Structural Damage / {item.get('Damage_Type', '')}",
                "Subject_Case_Number": actual_pid,
                "Subject_Status": f"Damage: {item.get('Damage_Type', 'Active')}",
                "Subject_Comments": item.get("Description", ""),
                "Source_File": "Osceola_County_Damage_Assessments_API",
                "Photo_Url": "",
                "Is_Stacked_Distress": "Yes" if item.get("Damage_Type", "").lower() in ["major", "destroyed"] else "No",
                "Distress_Stack_Notes": f"FEMA / Municipal Damage Assessment: {item.get('Damage_Type', '')} (${item.get('Loss_Amount', 0):,.0f} loss)",
                "Subject_Date": ""
            }
            matched_rows.append(lead_row)

    print(f"[Osceola API Sync] Total matched leads: {len(matched_rows):,}")

    combined = pd.DataFrame(matched_rows)
    if combined.empty:
        return {"status": "warning", "message": "No matched parcels found in current batch."}

    # Deduplicate by Parcel_ID
    combined = combined.drop_duplicates(subset=["Parcel_ID", "Lead_Type"], keep="last")

    # Harmonize column data types
    for col in combined.columns:
        if col in ["Market_Value", "Assessed_Value", "Taxable_Value", "Living_Sqft", "Year_Built", "Match_Confidence"]:
            combined[col] = pd.to_numeric(combined[col], errors="coerce").fillna(0.0)
        else:
            combined[col] = combined[col].astype(str).replace({"nan": "", "None": "", "<NA>": ""})

    combined.to_parquet(osceola_cache, index=False)
    combined.to_csv(csv_file, index=False)
    print(f"[Osceola API Sync] Successfully saved {len(combined):,} leads to {osceola_cache}.")

    return {
        "status": "success",
        "cases_fetched": len(cases),
        "matched_leads": len(matched_rows),
        "total_osceola_leads": len(combined)
    }

if __name__ == "__main__":
    res = sync_osceola_live_apis()
    print("Sync Result:\n", json.dumps(res, indent=2))
