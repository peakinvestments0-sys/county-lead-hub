"""
Sarasota County Live SeeClickFix API Sync Service
Direct integration with seeclickfix.com REST API (place_url: sarasota-county)
Pulls real-time citizen & inspector reported flooding, storm drainage intrusion,
illegal dumping, debris, hazardous trees, and property neglect across
Sarasota, Venice, North Port, Englewood, and Nokomis.

Matches directly against 325,358 Sarasota Master Tax Parcels,
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

SARASOTA_SCF_ENDPOINT = "https://seeclickfix.com/api/v2/issues"

NEGLECT_KEYWORDS = [
    "dump", "trash", "debris", "drainage", "flood", "tree", "damage",
    "board", "weed", "grass", "overgrown", "derelict", "unfit", "hazard",
    "code", "blight", "water", "unsafe", "abandon", "vacant", "junk"
]

CITY_STRIP_REGEX = re.compile(
    r"\b(VENICE|SARASOTA|NORTH\s*PORT|ENGLEWOOD|NOKOMIS|OSPREY|LONGBOAT\s*KEY|SIESTA\s*KEY)\b.*$",
    re.IGNORECASE
)

def fetch_sarasota_seeclickfix_issues(max_pages=5):
    """Fetch live issues from Sarasota County SeeClickFix API."""
    all_issues = []
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

    print("[Sarasota SeeClickFix API] Fetching live issues for Sarasota County...")
    for page in range(1, max_pages + 1):
        params = {
            "place_url": "sarasota-county",
            "per_page": 100,
            "page": page
        }
        url = f"{SARASOTA_SCF_ENDPOINT}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                issues = data.get("issues", [])
                if not issues:
                    break
                all_issues.extend(issues)
        except Exception as e:
            print(f"[Sarasota SeeClickFix API] Error on page {page}: {e}")
            break

    print(f"[Sarasota SeeClickFix API] Total issues retrieved: {len(all_issues):,}")

    filtered = []
    for item in all_issues:
        summary = item.get("summary") or ""
        desc = item.get("description") or ""
        req_title = (item.get("request_type") or {}).get("title") or ""
        full_text = f"{summary} {desc} {req_title}".lower()

        if any(kw in full_text for kw in NEGLECT_KEYWORDS):
            addr = item.get("address") or ""
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
                    "Source": "Sarasota_SeeClickFix_Live_API"
                })

    print(f"[Sarasota SeeClickFix API] Filtered to {len(filtered):,} property neglect/distress issues.")
    return filtered


def sync_sarasota_live_apis():
    """
    Orchestrate Sarasota County SeeClickFix live sync:
    1. Fetch live issues.
    2. Match against 325,358 master parcels.
    3. Persist to matched_leads_cache.parquet.
    """
    sarasota_dir = os.path.join(BASE_DIR, "data", "FL", "sarasota")
    cache_file = os.path.join(sarasota_dir, "matched_leads_cache.parquet")
    csv_file = os.path.join(sarasota_dir, "Sarasota_Live_API_Distress_Leads.csv")

    issues = fetch_sarasota_seeclickfix_issues(max_pages=5)
    if not issues:
        return {"status": "warning", "message": "No live issues fetched from Sarasota API."}

    parquet_path = os.path.join(sarasota_dir, "RP_PROPERTY_INFO.parquet")
    print(f"[Sarasota API Sync] Loading Sarasota Master Parcels from {parquet_path}...")
    master_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    master_df = pd.read_parquet(parquet_path, columns=master_cols)
    master_df["NORM_ADDR"] = master_df["SITE_ADDRESS"].apply(normalize_address)
    master_by_addr = master_df.drop_duplicates(subset=["NORM_ADDR"]).set_index("NORM_ADDR")

    matched_rows = []
    for item in issues:
        raw_addr = item.get("Case Address", "")
        street_candidate = CITY_STRIP_REGEX.sub("", raw_addr).strip(" ,")
        if not street_candidate:
            street_candidate = raw_addr.split(",")[0].strip()

        norm_s = normalize_address(street_candidate)
        if norm_s and norm_s in master_by_addr.index:
            m = master_by_addr.loc[norm_s]
            pid = str(m.get("PARCEL_NUMBER") or "")

            site_addr = str(m.get("SITE_ADDRESS") or "").strip().upper()
            mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
            site_zip = str(m.get("SITE_ZIP") or "").strip()
            mail_zip = str(m.get("MAILING_ZIP") or "").strip()
            is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
            absentee_status = "Out of State" if (m.get("MAILING_STATE") and str(m.get("MAILING_STATE")).strip().upper() not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

            lead_row = {
                "Match_Status": "MATCHED",
                "Match_Confidence": 95.0,
                "Match_Method": "EXACT_STREET_ADDRESS",
                "Match_Notes": f"Live Citizen/Inspector Report: {item.get('Summary', '')}",
                "Clean_First_Name": "",
                "Clean_Last_Name": "",
                "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
                "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
                "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
                "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
                "County_Owner_2": clean_display_name(str(m.get("OWNER2") or "")),
                "Secondary_Owner": clean_display_name(str(m.get("OWNER2") or "")),
                "Property_Address": clean_display_address(str(m.get("SITE_ADDRESS") or "")),
                "Property_City": clean_display_city(str(m.get("SITE_CITY") or "")),
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
                "Property_Type": "Single Family" if "01" in str(m.get("PROPERTY_USE") or "") else "Residential",
                "Property_Use": str(m.get("PROPERTY_USE") or "Residential"),
                "Legal_Description": str(m.get("LEGAL") or ""),
                "Lead_Type": "Code Violation",
                "Distress_Type": f"Live Municipal Distress / {item.get('Summary', '')}",
                "Subject_Case_Number": f"SCF-{item.get('Issue_ID', '')}",
                "Subject_Status": item.get("Status", "Open"),
                "Subject_Comments": f"{item.get('Summary', '')}: {item.get('Description', '')}",
                "Source_File": "Sarasota_SeeClickFix_Live_API",
                "Photo_Url": item.get("Photo_Url", ""),
                "Is_Stacked_Distress": "No",
                "Distress_Stack_Notes": "",
                "Subject_Date": item.get("Created_At", "")
            }
            matched_rows.append(lead_row)

    print(f"[Sarasota API Sync] Total matched leads: {len(matched_rows):,}")

    combined = pd.DataFrame(matched_rows)
    if combined.empty:
        return {"status": "warning", "message": "No matched addresses found in current Sarasota batch."}

    # Deduplicate by Parcel_ID
    combined = combined.drop_duplicates(subset=["Parcel_ID", "Lead_Type"], keep="last")

    # Harmonize pyarrow types
    for col in combined.columns:
        if col in ["Market_Value", "Assessed_Value", "Taxable_Value", "Living_Sqft", "Year_Built", "Match_Confidence"]:
            combined[col] = pd.to_numeric(combined[col], errors="coerce").fillna(0.0)
        else:
            combined[col] = combined[col].astype(str).replace({"nan": "", "None": "", "<NA>": ""})

    combined.to_parquet(cache_file, index=False)
    combined.to_csv(csv_file, index=False)
    print(f"[Sarasota API Sync] Saved {len(combined):,} leads to {cache_file}.")

    return {
        "status": "success",
        "issues_fetched": len(issues),
        "matched_leads": len(matched_rows),
        "total_sarasota_leads": len(combined)
    }

if __name__ == "__main__":
    res = sync_sarasota_live_apis()
    print("Sync Result:\n", json.dumps(res, indent=2))
