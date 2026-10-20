"""
Volusia County Live Code Enforcement & Distress API Sync Service
Direct integration with official City of Daytona Beach / Volusia County Code Enforcement ArcGIS REST Service:
https://services2.arcgis.com/2rIG17xLqeJd2jOX/arcgis/rest/services/CodeEnforcementData/FeatureServer/1/query
and SeeClickFix live municipal property distress feeds.

Pulls live municipal code violations, unmaintained vacant lots, condemned/unfit structures,
fire damage, water leaks/mold, and junk vehicle accumulation.
Matches directly against Volusia Master Parcels (313,548 properties) by ParcelNo and street address.
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime
import pandas as pd

from src.normalizer import clean_display_address, clean_display_name, clean_display_city, normalize_address

VOLUSIA_CODE_ENDPOINT = (
    "https://services2.arcgis.com/2rIG17xLqeJd2jOX/arcgis/rest/services/"
    "CodeEnforcementData/FeatureServer/1/query"
)

# Neglect, damage, unmaintained, structure hazard keywords
DISTRESS_KEYWORDS = [
    "overgrown", "grass", "weed", "trash", "debris", "unmaintained", "damage",
    "fire", "leak", "mold", "junk", "vehicle", "unfit", "uninhabitable",
    "disrepair", "vacant", "abandon", "roof", "electric", "sewage", "dilapidated",
    "hazard", "blight", "inoperable", "derelict", "tamper", "permit", "unpermitted",
    "condemn", "squatter", "unkept", "structural"
]

def fetch_daytona_code_cases():
    """Fetch live code enforcement cases from Daytona Beach / Volusia County ArcGIS REST service."""
    all_features = []
    offset = 0
    batch_size = 2000
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    print("[Volusia Code API] Fetching live cases from Daytona Beach ArcGIS service...")
    while True:
        params = {
            "where": "1=1",
            "outFields": "BaseNo,Milestone,ShortDescription,FullDescription,ParcelNo,Match_addr,SubmitDt,CreateDt",
            "resultOffset": str(offset),
            "resultRecordCount": str(batch_size),
            "f": "json"
        }
        url = f"{VOLUSIA_CODE_ENDPOINT}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                features = data.get("features", [])
                if not features:
                    break
                records = [f.get("attributes", {}) for f in features]
                all_features.extend(records)
                print(f"[Volusia Code API] Retrieved {len(records):,} records (offset {offset:,})")
                if len(features) < batch_size:
                    break
                offset += batch_size
        except Exception as e:
            print(f"[Volusia Code API] Error fetching offset {offset}: {e}")
            break

    print(f"[Volusia Code API] Total cases downloaded: {len(all_features):,}")

    filtered = []
    for item in all_features:
        short_desc = str(item.get("ShortDescription") or "").strip()
        full_desc = str(item.get("FullDescription") or "").strip()
        milestone = str(item.get("Milestone") or "").strip()
        combined_text = f"{short_desc} {full_desc}".lower()

        # Keep records matching physical property distress keywords
        if any(kw in combined_text for kw in DISTRESS_KEYWORDS):
            pid = str(item.get("ParcelNo") or "").strip()
            addr = str(item.get("Match_addr") or "").strip()
            dt_raw = item.get("SubmitDt") or item.get("CreateDt")
            date_str = ""
            if dt_raw:
                try:
                    date_str = datetime.fromtimestamp(dt_raw / 1000.0).strftime("%Y-%m-%d")
                except Exception:
                    pass

            desc_clean = full_desc if full_desc else short_desc
            filtered.append({
                "Case_Number": item.get("BaseNo") or "",
                "Milestone": milestone or "Active",
                "Description": desc_clean[:300],
                "Summary": short_desc[:120],
                "Address": addr,
                "Parcel_Number": pid,
                "Date": date_str,
                "Source": "Daytona_Beach_Code_Enforcement_API",
                "Photo_Url": ""
            })

    print(f"[Volusia Code API] Filtered to {len(filtered):,} property distress cases.")
    return filtered


def fetch_volusia_seeclickfix():
    """Fetch live distress issues from SeeClickFix for Daytona Beach & Volusia County."""
    scf_issues = []
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

    # Query 1: Daytona Beach place
    # Query 2: Volusia County bounding box
    queries = [
        "https://seeclickfix.com/api/v2/issues?place_url=daytona-beach&per_page=100",
        "https://seeclickfix.com/api/v2/issues?min_lat=28.85&max_lat=29.35&min_lng=-81.45&max_lng=-80.95&per_page=100"
    ]

    for q_url in queries:
        try:
            req = urllib.request.Request(q_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for iss in data.get("issues", []):
                    summary = str(iss.get("summary") or "").strip()
                    desc = str(iss.get("description") or "").strip()
                    text = f"{summary} {desc}".lower()

                    # Exclude street lighting, municipal water mains, potholes
                    if any(bad in text for bad in ["street light", "traffic light", "pothole", "manhole", "water main break"]):
                        continue

                    # Keep property distress
                    if any(kw in text for kw in ["trash", "debris", "overgrown", "grass", "weed", "lot", "vehicle", "abandon", "disrepair", "squatter", "unkept", "unmaintained"]):
                        photo_url = ""
                        media = iss.get("media")
                        if isinstance(media, dict):
                            photo_url = media.get("image_full") or media.get("representative_image_url") or ""

                        scf_issues.append({
                            "Case_Number": f"SCF-{iss.get('id', '')}",
                            "Milestone": iss.get("status", "Open").title(),
                            "Description": desc[:300] if desc else summary,
                            "Summary": summary[:120],
                            "Address": str(iss.get("address") or "").strip(),
                            "Parcel_Number": "",
                            "Date": (iss.get("created_at") or "")[:10],
                            "Source": "SeeClickFix_Volusia_Live",
                            "Photo_Url": photo_url
                        })
        except Exception as e:
            print(f"[Volusia SCF] Error querying SeeClickFix: {e}")

    print(f"[Volusia SCF] Filtered to {len(scf_issues):,} SeeClickFix distress leads with photos.")
    return scf_issues


def sync_volusia_live_apis():
    """
    Orchestrate Volusia County live distress sync:
    1. Fetch live Daytona Beach code cases + SeeClickFix issues.
    2. Match against Volusia master parcels by ParcelNo and normalized address.
    3. Persist to matched_leads_cache.parquet.
    """
    volusia_dir = os.path.join(BASE_DIR, "data", "FL", "volusia")
    os.makedirs(volusia_dir, exist_ok=True)
    cache_file = os.path.join(volusia_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(volusia_dir, "Volusia_Live_API_Distress_Leads.csv")

    ce_cases = fetch_daytona_code_cases()
    scf_cases = fetch_volusia_seeclickfix()
    all_cases = ce_cases + scf_cases

    if not all_cases:
        return {"status": "warning", "message": "No live cases fetched from Volusia APIs."}

    parquet_path = os.path.join(volusia_dir, "RP_PROPERTY_INFO.parquet")
    if not os.path.exists(parquet_path):
        return {"status": "error", "message": f"Master parcel file not found at {parquet_path}"}

    print(f"[Volusia API Sync] Loading Volusia Master Parcels from {parquet_path}...")
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
    master_by_addr = master_df[master_df["NORM_ADDR"].str.len() > 3].drop_duplicates(subset=["NORM_ADDR"]).set_index("NORM_ADDR")

    matched_rows = []
    for item in all_cases:
        pid = item.get("Parcel_Number", "").strip()
        m = None
        match_method = "EXACT_PARCEL_ID"

        if pid and pid in master_by_pid.index:
            m = master_by_pid.loc[pid]
        else:
            raw_addr = item.get("Address", "")
            # Clean common Daytona address formatting
            clean_raw = raw_addr.split(",")[0].split("APT")[0].split("UNIT")[0].strip()
            norm_a = normalize_address(clean_raw)
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
                "Match_Notes": f"Volusia Code Case #{item.get('Case_Number', '')}: {item.get('Summary', '')}",
                "Clean_First_Name": "",
                "Clean_Last_Name": "",
                "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
                "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
                "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
                "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
                "County_Owner_2": clean_display_name(str(m.get("OWNER2") or "")),
                "Secondary_Owner": clean_display_name(str(m.get("OWNER2") or "")),
                "Property_Address": display_addr,
                "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Daytona Beach")),
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
                "Lead_Type": "Code Violation",
                "Distress_Type": f"Code Violation / {item.get('Summary', '')}",
                "Subject_Case_Number": item.get("Case_Number", ""),
                "Subject_Status": item.get("Milestone", "Active"),
                "Subject_Comments": f"{item.get('Summary', '')}: {item.get('Description', '')}",
                "Source_File": item.get("Source", "Volusia_Code_Enforcement_Live_API"),
                "Photo_Url": item.get("Photo_Url", ""),
                "Is_Stacked_Distress": "No",
                "Distress_Stack_Notes": "",
                "Subject_Date": item.get("Date", "")
            }
            matched_rows.append(lead_row)

    print(f"[Volusia API Sync] Total matched leads: {len(matched_rows):,}")

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
    print(f"[Volusia API Sync] Successfully saved {len(combined):,} leads to {cache_file}.")

    return {
        "status": "success",
        "cases_fetched": len(all_cases),
        "matched_leads": len(matched_rows),
        "total_volusia_leads": len(combined)
    }

if __name__ == "__main__":
    res = sync_volusia_live_apis()
    print("Sync Result:\n", json.dumps(res, indent=2))
