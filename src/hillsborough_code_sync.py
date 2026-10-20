"""
Hillsborough County Live Structural Damage & Property Distress API Sync Service
Direct integration with official Hillsborough County Structural Damage Assessments FeatureServer:
https://services.arcgis.com/apTfC6SUmnNfnxuF/arcgis/rest/services/HC_DamageAssessments2024_PublicView/FeatureServer/24/query

Pulls official post-storm municipal structural damage inspections, condemned/unfit buildings,
destroyed roofs, flood water intrusions, and severe distress across Tampa, Brandon, Plant City,
Temple Terrace, Lutz, Riverview, and Valrico.
Matches directly against Hillsborough Master Tax Parcels (531,612 properties) by PIN / PARCELID.
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

HILLSBOROUGH_DAMAGE_ENDPOINT = (
    "https://services.arcgis.com/apTfC6SUmnNfnxuF/arcgis/rest/services/"
    "HC_DamageAssessments2024_PublicView/FeatureServer/24/query"
)

def fetch_hillsborough_damage_records(max_records=20000):
    """Fetch official municipal structural damage assessments from Hillsborough County ArcGIS service."""
    all_features = []
    offset = 0
    batch_size = 2000
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    # Focus on verified structural damage with parcel ID
    where_clause = "PARCELID IS NOT NULL AND TYPDAMAGE IS NOT NULL"
    out_fields = "PARCELID,TYPDAMAGE,STRLOSS,DESCDAMAGE,FieldNotes,HOMETYPE,PREDISVAL,PRIMCAUSE,CreationDate"

    print("[Hillsborough Damage API] Fetching live municipal structural inspections from Hillsborough County...")
    while offset < max_records:
        params = {
            "where": where_clause,
            "outFields": out_fields,
            "resultOffset": str(offset),
            "resultRecordCount": str(batch_size),
            "f": "json"
        }
        url = f"{HILLSBOROUGH_DAMAGE_ENDPOINT}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                features = data.get("features", [])
                if not features:
                    break
                records = [f.get("attributes", {}) for f in features]
                all_features.extend(records)
                print(f"[Hillsborough Damage API] Retrieved {len(records):,} records (offset {offset:,})")
                if len(features) < batch_size:
                    break
                offset += batch_size
        except Exception as e:
            print(f"[Hillsborough Damage API] Error fetching offset {offset}: {e}")
            break

    print(f"[Hillsborough Damage API] Total records downloaded: {len(all_features):,}")

    filtered = []
    for item in all_features:
        pid = str(item.get("PARCELID") or "").strip()
        damage_type = str(item.get("TYPDAMAGE") or "").strip()
        desc = str(item.get("DESCDAMAGE") or "").strip()
        notes = str(item.get("FieldNotes") or "").strip()
        loss = float(item.get("STRLOSS") or 0.0)

        # Exclude inaccessible or zero loss if no damage description
        if damage_type.lower() in ["inaccessible", "none"] and loss == 0 and not desc:
            continue

        dt_raw = item.get("CreationDate")
        date_str = ""
        if dt_raw:
            try:
                date_str = datetime.fromtimestamp(dt_raw / 1000.0).strftime("%Y-%m-%d")
            except Exception:
                pass

        full_comments = desc if desc else f"{damage_type} structural damage"
        if notes:
            full_comments += f" | Notes: {notes}"
        if loss > 0:
            full_comments += f" | Est Loss: ${loss:,.0f}"

        filtered.append({
            "Parcel_Number": pid,
            "Damage_Type": damage_type,
            "Description": full_comments[:300],
            "Loss_Amount": loss,
            "Home_Type": str(item.get("HOMETYPE") or "Residential"),
            "Date": date_str,
            "Source": "Hillsborough_County_Damage_Assessments_API"
        })

    print(f"[Hillsborough Damage API] Filtered to {len(filtered):,} actionable structural damage distress cases.")
    return filtered


def sync_hillsborough_live_apis():
    """
    Orchestrate Hillsborough County live distress sync:
    1. Fetch live structural damage inspections from County API.
    2. Match against Hillsborough master parcels by PIN (PARCELID).
    3. Persist to matched_leads_cache.parquet and CSV.
    """
    hillsborough_dir = os.path.join(BASE_DIR, "data", "FL", "hillsborough")
    os.makedirs(hillsborough_dir, exist_ok=True)
    cache_file = os.path.join(hillsborough_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(hillsborough_dir, "Hillsborough_Live_API_Distress_Leads.csv")

    cases = fetch_hillsborough_damage_records()
    if not cases:
        return {"status": "warning", "message": "No live damage cases fetched from Hillsborough API."}

    parquet_path = os.path.join(hillsborough_dir, "RP_PROPERTY_INFO.parquet")
    if not os.path.exists(parquet_path):
        return {"status": "error", "message": f"Master parcel file not found at {parquet_path}"}

    print(f"[Hillsborough API Sync] Loading Hillsborough Master Parcels from {parquet_path}...")
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

            display_addr = clean_display_address(site_addr)
            lead_row = {
                "Match_Status": "MATCHED",
                "Match_Confidence": 100.0,
                "Match_Method": "EXACT_PARCEL_ID",
                "Match_Notes": f"Hillsborough Structural Damage: {item.get('Damage_Type', '')} (${item.get('Loss_Amount', 0):,.0f} loss)",
                "Clean_First_Name": "",
                "Clean_Last_Name": "",
                "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
                "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
                "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
                "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
                "County_Owner_2": clean_display_name(str(m.get("OWNER2") or "")),
                "Secondary_Owner": clean_display_name(str(m.get("OWNER2") or "")),
                "Property_Address": display_addr,
                "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Tampa")),
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
                "Property_Type": "Single Family" if "SINGLE" in str(m.get("PROPERTY_USE") or "").upper() or "CONDO" in str(m.get("PROPERTY_USE") or "").upper() else "Residential",
                "Property_Use": str(m.get("PROPERTY_USE") or "Residential"),
                "Legal_Description": str(m.get("LEGAL") or ""),
                "Lead_Type": "Substantial Damage",
                "Distress_Type": f"Structural Damage / {item.get('Damage_Type', '')}",
                "Subject_Case_Number": actual_pid,
                "Subject_Status": f"Damage: {item.get('Damage_Type', 'Active')}",
                "Subject_Comments": item.get("Description", ""),
                "Source_File": "Hillsborough_County_Damage_Assessments_API",
                "Photo_Url": "",
                "Is_Stacked_Distress": "Yes" if item.get("Damage_Type", "").lower() in ["major", "destroyed"] else "No",
                "Distress_Stack_Notes": f"FEMA / Municipal Damage Assessment: {item.get('Damage_Type', '')} (${item.get('Loss_Amount', 0):,.0f} structure loss)",
                "Subject_Date": item.get("Date", "")
            }
            matched_rows.append(lead_row)

    print(f"[Hillsborough API Sync] Total matched leads: {len(matched_rows):,}")

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

    combined.to_parquet(cache_file, index=False)
    combined.to_csv(csv_file, index=False)
    print(f"[Hillsborough API Sync] Successfully saved {len(combined):,} leads to {cache_file}.")

    return {
        "status": "success",
        "cases_fetched": len(cases),
        "matched_leads": len(matched_rows),
        "total_hillsborough_leads": len(combined)
    }

if __name__ == "__main__":
    res = sync_hillsborough_live_apis()
    print("Sync Result:\n", json.dumps(res, indent=2))
