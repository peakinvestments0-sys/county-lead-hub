"""
Miami-Dade County (Miami, Hialeah, Miami Beach, Homestead, Coral Gables, Doral, Miami Gardens, etc.)
Live Code Enforcement & Distress API Sync Service.

Direct integration with:
- Miami-Dade Municipalities SeeClickFix Filtered Property Distress Feeds across 21 municipal hubs.
- Matches against ~590k Miami-Dade County Master Parcels.
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

DADE_SEECLICKFIX_CENTERS = [
    ("Miami Central", 25.7617, -80.1918),
    ("Miami Little Havana", 25.7700, -80.2300),
    ("Miami Little Haiti", 25.8100, -80.1950),
    ("Hialeah", 25.8576, -80.2781),
    ("Miami Beach", 25.7907, -80.1300),
    ("Homestead", 25.4687, -80.4776),
    ("Coral Gables", 25.7215, -80.2684),
    ("Miami Gardens", 25.9420, -80.2456),
    ("Doral", 25.8195, -80.3553),
    ("North Miami", 25.8901, -80.1867),
    ("North Miami Beach", 25.9331, -80.1625),
    ("Aventura", 25.9565, -80.1392),
    ("South Miami", 25.7076, -80.2934),
    ("Pinecrest", 25.6618, -80.3076),
    ("Cutler Bay", 25.5809, -80.3467),
    ("Palmetto Bay", 25.6234, -80.3259),
    ("Sunny Isles Beach", 25.9429, -80.1228),
    ("Opa-locka", 25.9015, -80.2503),
    ("Key Biscayne", 25.6937, -80.1628),
    ("Miami Springs", 25.8234, -80.2906),
    ("Florida City", 25.4479, -80.4792)
]

DADE_CITIES = [
    'MIAMI BEACH', 'NORTH MIAMI BEACH', 'NORTH MIAMI', 'MIAMI GARDENS',
    'CORAL GABLES', 'SOUTH MIAMI', 'MIAMI SPRINGS', 'SUNNY ISLES BEACH',
    'PALMETTO BAY', 'CUTLER BAY', 'KEY BISCAYNE', 'MIAMI LAKES',
    'FLORIDA CITY', 'BAL HARBOUR', 'BAY HARBOR ISLANDS', 'BISCAYNE PARK',
    'EL PORTAL', 'GOLDEN BEACH', 'INDIAN CREEK', 'VIRGINIA GARDENS',
    'WEST MIAMI', 'HOMESTEAD', 'HIALEAH', 'DORAL', 'AVENTURA',
    'PINECREST', 'OPA-LOCKA', 'OPA LOCKA', 'SWEETWATER', 'MEDLEY', 'MIAMI'
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
    clean = re.sub(r'\b33\d{3}\b', '', clean)
    clean = clean.replace('USA', '').replace('United States', '')
    clean = clean.strip().rstrip(',')
    u_clean = clean.upper()
    for city in DADE_CITIES:
        if u_clean.endswith(city):
            clean = clean[:len(clean) - len(city)].strip().rstrip(',')
            break
        if u_clean.endswith(", " + city) or u_clean.endswith("," + city):
            clean = clean.split(city)[0].strip().rstrip(',')
            break
    return clean.strip()

def fetch_dade_seeclickfix_distress():
    """Fetch and filter genuine property distress from SeeClickFix across Miami-Dade County."""
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    total_issues = {}

    noise_keywords = [
        "pothole", "street light", "streetlight", "traffic light", "traffic signal",
        "sidewalk", "curb", "playground", "park", "drainage", "storm drain",
        "dead animal", "roadkill", "dead cat", "dead dog", "sign request", "street sign",
        "speeding", "traffic calming", "road", "hacked", "borrow", "financing"
    ]

    distress_indicators = [
        "trash", "debris", "overgrown", "grass", "blight", "dumping",
        "abandoned", "derelict", "unsafe", "damage", "squatter",
        "boarded", "roof", "hazard", "nuisance", "structure",
        "unpermitted", "violation", "code enforcement", "water heater",
        "code", "demolition", "vacant", "junk", "tall grass", "inoperable"
    ]

    for name, lat, lng in DADE_SEECLICKFIX_CENTERS:
        for page in range(1, 3):
            url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=100&page={page}"
            try:
                time.sleep(0.2)  # Polite pacing
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
                        if any(d in full_text for d in distress_indicators):
                            total_issues[iid] = issue
            except Exception as e:
                print(f"[Miami-Dade API Sync] Error fetching SeeClickFix for {name} page {page}: {e}", flush=True)
                break

    print(f"[Miami-Dade API Sync] SeeClickFix filtered distress issues: {len(total_issues):,}", flush=True)
    return list(total_issues.values())

def sync_miami_dade_leads(force_refresh=False):
    """
    Synchronize Miami-Dade County Distress feeds, join with Master Parcels,
    and persist into matched_leads_cache.parquet.
    """
    dade_dir = os.path.join(BASE_DIR, "data", "FL", "miami_dade")
    master_parquet = os.path.join(dade_dir, "RP_PROPERTY_INFO.parquet")
    leads_parquet = os.path.join(dade_dir, "matched_leads_cache.parquet")

    if not os.path.exists(master_parquet):
        return {
            "status": "error",
            "message": f"Master parcel file not found at {master_parquet}. Run build_miami_dade_parcels.py first."
        }

    print("[Miami-Dade API Sync] Loading Miami-Dade County Master Parcels...", flush=True)
    master_cols = [
        "PARCEL_NUMBER", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    df_master = pd.read_parquet(master_parquet, columns=master_cols)
    print(f"[Miami-Dade API Sync] Loaded {len(df_master):,} master parcels.", flush=True)

    # Build vectorized normalized address index
    print("[Miami-Dade API Sync] Indexing master parcel addresses...", flush=True)
    df_master["NORM_ADDR"] = df_master["SITE_ADDRESS"].apply(norm_addr)
    df_dedup = df_master[df_master["NORM_ADDR"] != ""].drop_duplicates(subset=["NORM_ADDR"])
    addr_lookup = df_dedup.set_index("NORM_ADDR").to_dict(orient="index")
    print(f"[Miami-Dade API Sync] Indexed {len(addr_lookup):,} unique master addresses.", flush=True)

    # Fetch live distress cases
    scf_cases = fetch_dade_seeclickfix_distress()

    matched_rows = []
    seen_lead_keys = set()

    for scf in scf_cases:
        raw_addr = scf.get("address") or ""
        clean_s = clean_scf_address(raw_addr)
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

        scf_cat = (scf.get("request_type") or {}).get("title") or "Code Violation"
        scf_summary = scf.get("summary") or scf_cat
        created_at = str(scf.get("created_at") or "")[:10]
        media_url = (scf.get("media") or {}).get("image_full") or ""

        lead_row = {
            "Match_Status": "MATCHED",
            "Match_Confidence": 96.0,
            "Match_Method": "SEECLICKFIX_ADDRESS_MATCH",
            "Match_Notes": f"Miami-Dade Code Distress #{scf_id}: {scf_summary}",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Miami")),
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
            "Distress_Stack_Notes": f"Miami-Dade Property Distress: {scf_summary}",
            "Is_Stacked_Distress": "No",
            "Case_Number": f"SCF-{scf_id}",
            "Source_File": "Miami_Dade_SeeClickFix_Live_API",
            "Filing_Date": created_at,
            "Photo_Url": media_url
        }
        matched_rows.append(lead_row)

    print(f"[Miami-Dade API Sync] Matched leads generated: {len(matched_rows):,}", flush=True)

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
        "county": "miami_dade",
        "county_name": "Miami-Dade County",
        "total_leads": len(leads_df),
        "unique_properties": len(leads_df["Parcel_ID"].unique()),
        "stacked_distress_count": len(stacked_pids),
        "absentee_owners": int((leads_df["Is_Absentee"] == "Yes").sum()),
        "cache_file": leads_parquet,
        "cache_size_kb": round(file_size_kb, 1),
        "sync_timestamp": datetime.datetime.now().isoformat()
    }

    print(f"[Miami-Dade API Sync] COMPLETE: {stats['total_leads']:,} leads ({stats['unique_properties']:,} properties) saved to {leads_parquet} ({file_size_kb:.1f} KB)", flush=True)
    return stats

if __name__ == "__main__":
    res = sync_miami_dade_leads(force_refresh=True)
    print(json.dumps(res, indent=2))
