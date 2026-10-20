"""
Marion County (Ocala, Belleview, Dunnellon) Live Code Enforcement & Municipal Liens Sync Service
Direct integration with:
1. City of Ocala Recorded Municipal Liens & Code Enforcement FeatureServer (Lien_Data_Update)
   - Real-time recorded property liens, exact lien amounts, property values, and code citations.
2. Marion County & Municipalities SeeClickFix Filtered Property Distress Feeds
   - (Ocala, Belleview, Dunnellon, Silver Springs, Summerfield).

Matches against ~286k Marion County Master Parcels (Ocala, Belleview, Dunnellon).
Strictly filters out municipal infrastructure noise (potholes, streetlights, traffic signs).
Retains genuine open code enforcement citations, recorded municipal liens, property neglect, and derelict structures.
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

OCALA_LIEN_URL = "https://services1.arcgis.com/Xt7esznjGcR11P3w/arcgis/rest/services/Lien_Data_Update/FeatureServer/0/query"

MARION_SEECLICKFIX_CENTERS = [
    ("Ocala", 29.1872, -82.1401),
    ("Belleview", 29.0575, -82.0601),
    ("Dunnellon", 29.0494, -82.4612),
    ("Silver Springs", 29.2158, -82.0573),
    ("Summerfield", 28.9897, -82.0368)
]

MARION_CITIES = [
    'SILVER SPRINGS', 'SUMMERFIELD', 'BELLEVIEW', 'DUNNELLON', 'OCALA', 'MARION'
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
    clean = re.sub(r'\b34\d{3}\b', '', clean)
    clean = clean.replace('USA', '').replace('United States', '')
    clean = clean.strip().rstrip(',')
    u_clean = clean.upper()
    for city in MARION_CITIES:
        if u_clean.endswith(city):
            clean = clean[:len(clean) - len(city)].strip().rstrip(',')
            break
        if u_clean.endswith(", " + city) or u_clean.endswith("," + city):
            clean = clean.split(city)[0].strip().rstrip(',')
            break
    return clean.strip()

def fetch_ocala_recorded_liens():
    """Fetch all active recorded municipal liens from City of Ocala FeatureServer."""
    params = {
        'where': '1=1',
        'outFields': '*',
        'resultRecordCount': '2000',
        'f': 'json'
    }
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    url = f"{OCALA_LIEN_URL}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            features = data.get('features', [])
            records = [f.get('attributes', {}) for f in features]
            print(f"[Marion API Sync] City of Ocala Recorded Liens fetched: {len(records):,}", flush=True)
            return records
    except Exception as e:
        print(f"[Marion API Sync] Error fetching Ocala municipal liens: {e}", flush=True)
        return []

def fetch_marion_seeclickfix_distress():
    """Fetch and filter genuine property distress from SeeClickFix across Marion County."""
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

    for name, lat, lng in MARION_SEECLICKFIX_CENTERS:
        for page in range(1, 3):
            url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=100&page={page}"
            try:
                time.sleep(0.3)  # Gentle pacing
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

                        if any(n in full_text for n in noise_keywords):
                            continue
                        if any(d in full_text for d in distress_indicators):
                            total_issues[iid] = issue
            except Exception as e:
                print(f"[Marion API Sync] Error fetching SeeClickFix for {name}: {e}", flush=True)
                break

    print(f"[Marion API Sync] SeeClickFix filtered distress issues: {len(total_issues):,}", flush=True)
    return list(total_issues.values())

def sync_marion_leads(force_refresh=False):
    """
    Synchronize Marion County Recorded Liens & Distress feeds, join with Master Parcels,
    and persist into matched_leads_cache.parquet.
    """
    marion_dir = os.path.join(BASE_DIR, "data", "FL", "marion")
    master_parquet = os.path.join(marion_dir, "RP_PROPERTY_INFO.parquet")
    leads_parquet = os.path.join(marion_dir, "matched_leads_cache.parquet")

    if not os.path.exists(master_parquet):
        return {
            "status": "error",
            "message": f"Master parcel file not found at {master_parquet}. Run build_marion_parcels.py first."
        }

    print("[Marion API Sync] Loading Marion County Master Parcels...", flush=True)
    master_cols = [
        "PARCEL_NUMBER", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    df_master = pd.read_parquet(master_parquet, columns=master_cols)
    print(f"[Marion API Sync] Loaded {len(df_master):,} master parcels.", flush=True)

    # Build primary Parcel Number index and normalized address index
    print("[Marion API Sync] Indexing master parcels by PARCEL_NUMBER...", flush=True)
    df_master["NORM_ADDR"] = df_master["SITE_ADDRESS"].apply(norm_addr)
    pid_lookup = df_master.drop_duplicates(subset=["PARCEL_NUMBER"]).set_index("PARCEL_NUMBER").to_dict(orient="index")
    addr_lookup = df_master[df_master["NORM_ADDR"] != ""].drop_duplicates(subset=["NORM_ADDR"]).set_index("NORM_ADDR").to_dict(orient="index")
    print(f"[Marion API Sync] Indexed {len(pid_lookup):,} parcel IDs and {len(addr_lookup):,} addresses.", flush=True)

    matched_rows = []
    seen_lead_keys = set()

    # 1. Process City of Ocala Recorded Municipal Liens
    ocala_liens = fetch_ocala_recorded_liens()
    for lien in ocala_liens:
        p_num = str(lien.get("parcel") or "").strip()
        m = pid_lookup.get(p_num)
        if not m:
            # Fallback to address match
            situs = norm_addr(lien.get("situs_1") or "")
            if situs in addr_lookup:
                m = addr_lookup[situs]

        if not m:
            continue

        pid = str(m.get("PARCEL_NUMBER") or p_num).strip()
        lead_key = f"{pid}_lien_{lien.get('OBJECTID')}"
        if lead_key in seen_lead_keys:
            continue
        seen_lead_keys.add(lead_key)

        site_addr = str(m.get("SITE_ADDRESS") or lien.get("situs_1") or "").strip().upper()
        mail_addr = str(m.get("MAILING_ADDRESS_1") or "").strip().upper()
        site_zip = str(m.get("SITE_ZIP") or lien.get("zip") or "").strip()
        mail_zip = str(m.get("MAILING_ZIP") or "").strip()

        is_absentee = "Yes" if (mail_addr and site_addr and mail_addr != site_addr) else "No"
        mail_state = str(m.get("MAILING_STATE") or "FL").strip().upper()
        absentee_status = "Out of State" if (mail_state and mail_state not in ["FL", "FLORIDA"]) else ("Absentee Owner" if is_absentee == "Yes" else "Owner Occupied")

        lien_amt = float(lien.get("LienAmount") or 0.0)
        tot_val = int(m.get("CNTY_JST_VALUE") or lien.get("tot_val") or 0)

        lead_row = {
            "Match_Status": "MATCHED",
            "Match_Confidence": 99.0,
            "Match_Method": "OCALA_LIEN_PARCEL_MATCH",
            "Match_Notes": f"Recorded Municipal Lien: ${lien_amt:,.2f} encumbrance",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or lien.get("name") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Ocala")),
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
            "Market_Value": tot_val,
            "Assessed_Value": int(m.get("CNTY_ASD_VALUE") or 0),
            "Year_Built": int(m.get("YEAR_BUILT") or lien.get("yrblt1") or 0),
            "Living_Sqft": int(m.get("TOTAL_LIVING_SQFT") or lien.get("bld1_sf") or 0),
            "Legal_Description": str(m.get("LEGAL") or ""),
            "Lead_Type": "Code Violation",
            "All_Lead_Types": ["Code Violation", "Municipal Lien"],
            "Distress_Stack_Notes": f"Recorded Municipal Lien: ${lien_amt:,.2f}",
            "Is_Stacked_Distress": "Yes",
            "Case_Number": f"LIEN-{p_num}",
            "Source_File": "Ocala_Municipal_Liens_Live_API",
            "Filing_Date": str(lien.get("app_date") or datetime.date.today().isoformat()),
            "Photo_Url": ""
        }
        matched_rows.append(lead_row)

    # 2. Process SeeClickFix issues
    scf_cases = fetch_marion_seeclickfix_distress()
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
            "Match_Notes": f"Marion Code Distress #{scf_id}: {scf_summary}",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "Ocala")),
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
            "Distress_Stack_Notes": f"Marion Property Distress: {scf_summary}",
            "Is_Stacked_Distress": "No",
            "Case_Number": f"SCF-{scf_id}",
            "Source_File": "Marion_SeeClickFix_Live_API",
            "Filing_Date": created_at,
            "Photo_Url": media_url
        }
        matched_rows.append(lead_row)

    print(f"[Marion API Sync] Matched leads generated: {len(matched_rows):,}", flush=True)

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
        "county": "marion",
        "county_name": "Marion County",
        "total_leads": len(leads_df),
        "unique_properties": len(leads_df["Parcel_ID"].unique()),
        "stacked_distress_count": len(stacked_pids),
        "absentee_owners": int((leads_df["Is_Absentee"] == "Yes").sum()),
        "cache_file": leads_parquet,
        "cache_size_kb": round(file_size_kb, 1),
        "sync_timestamp": datetime.datetime.now().isoformat()
    }

    print(f"[Marion API Sync] COMPLETE: {stats['total_leads']:,} leads ({stats['unique_properties']:,} properties) saved to {leads_parquet} ({file_size_kb:.1f} KB)", flush=True)
    return stats

if __name__ == "__main__":
    res = sync_marion_leads(force_refresh=True)
    print(json.dumps(res, indent=2))
