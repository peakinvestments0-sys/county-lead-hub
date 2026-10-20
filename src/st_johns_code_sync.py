"""
St. Johns County (St. Augustine, Ponte Vedra Beach, St. Augustine Beach, Hastings, Fruit Cove, Nocatee)
Live Code Enforcement & Distress API Sync Service.

Direct integration with:
- St. Johns County Code Enforcement Non-Compliance & Unpermitted Property Registry (STR & CE Violations).
- St. Johns County Municipalities SeeClickFix Filtered Property Distress Feeds.
- Matches against ~152k St. Johns County Master Parcels.
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

ST_JOHNS_SEECLICKFIX_CENTERS = [
    ("St. Augustine", 29.8947, -81.3145),
    ("St. Augustine Beach", 29.8436, -81.2720),
    ("Ponte Vedra Beach", 30.2397, -81.3856),
    ("Hastings", 29.7189, -81.5090),
    ("Fruit Cove", 30.1064, -81.6212),
    ("Nocatee", 30.0988, -81.3888)
]

ST_JOHNS_CITIES = [
    'ST AUGUSTINE', 'SAINT AUGUSTINE', 'ST AUGUSTINE BEACH', 'SAINT AUGUSTINE BEACH',
    'PONTE VEDRA', 'PONTE VEDRA BEACH', 'HASTINGS', 'FRUIT COVE', 'NOCATEE',
    'ELKTON', 'SWITZERLAND', 'ST JOHNS', 'SAINT JOHNS'
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
    clean = re.sub(r'\b32\d{3}\b', '', clean)
    clean = clean.replace('USA', '').replace('United States', '')
    clean = clean.strip().rstrip(',')
    u_clean = clean.upper()
    for city in ST_JOHNS_CITIES:
        if u_clean.endswith(city):
            clean = clean[:len(clean) - len(city)].strip().rstrip(',')
            break
        if u_clean.endswith(", " + city) or u_clean.endswith("," + city):
            clean = clean.split(city)[0].strip().rstrip(',')
            break
    return clean.strip()

def fetch_st_johns_compliance_distress():
    """Fetch official St. Johns County Code Enforcement Non-Compliance & Distress violations."""
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    params = {
        'where': "Compliance_Status LIKE '%NON-COMPLIANT%'",
        'outFields': '*',
        'resultRecordCount': '2000',
        'f': 'json'
    }
    url = f"https://services1.arcgis.com/t2yugAJW83eUIFui/arcgis/rest/services/STR_Properties/FeatureServer/0/query?{urllib.parse.urlencode(params)}"
    records = []
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            features = data.get("features", [])
            for f in features:
                records.append(f.get("attributes", {}))
    except Exception as e:
        print(f"[St. Johns API Sync] Error fetching St. Johns compliance distress: {e}", flush=True)
    print(f"[St. Johns API Sync] St. Johns County Non-Compliance violations retrieved: {len(records):,}", flush=True)
    return records

def fetch_st_johns_seeclickfix_distress():
    """Fetch and filter genuine property distress from SeeClickFix across St. Johns County."""
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

    for name, lat, lng in ST_JOHNS_SEECLICKFIX_CENTERS:
        for page in range(1, 2):
            url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=50&page={page}"
            try:
                time.sleep(0.8)
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
                print(f"[St. Johns API Sync] Error fetching SeeClickFix for {name}: {e}", flush=True)
                break

    print(f"[St. Johns API Sync] SeeClickFix filtered distress issues: {len(total_issues):,}", flush=True)
    return list(total_issues.values())

def sync_st_johns_leads(force_refresh=False):
    st_johns_dir = os.path.join(BASE_DIR, "data", "FL", "st._johns")
    master_parquet = os.path.join(st_johns_dir, "RP_PROPERTY_INFO.parquet")
    leads_parquet = os.path.join(st_johns_dir, "matched_leads_cache.parquet")

    if not os.path.exists(master_parquet):
        return {
            "status": "error",
            "message": f"Master parcel file not found at {master_parquet}. Run build_st_johns_parcels.py first."
        }

    print("[St. Johns API Sync] Loading St. Johns County Master Parcels...", flush=True)
    master_cols = [
        "PARCEL_NUMBER", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    df_master = pd.read_parquet(master_parquet, columns=master_cols)
    print(f"[St. Johns API Sync] Loaded {len(df_master):,} master parcels.", flush=True)

    print("[St. Johns API Sync] Indexing master parcel addresses and parcel IDs...", flush=True)
    df_master["NORM_ADDR"] = df_master["SITE_ADDRESS"].apply(norm_addr)
    df_dedup = df_master[df_master["NORM_ADDR"] != ""].drop_duplicates(subset=["NORM_ADDR"])
    addr_lookup = df_dedup.set_index("NORM_ADDR").to_dict(orient="index")

    df_pids = df_master[df_master["PARCEL_NUMBER"] != ""].drop_duplicates(subset=["PARCEL_NUMBER"])
    pid_lookup = df_pids.set_index("PARCEL_NUMBER").to_dict(orient="index")
    # Also index without leading zeros
    pid_lstrip_lookup = {k.lstrip('0'): v for k, v in pid_lookup.items()}
    print(f"[St. Johns API Sync] Indexed {len(addr_lookup):,} addresses and {len(pid_lookup):,} parcel IDs.", flush=True)

    matched_rows = []
    seen_lead_keys = set()

    # 1. St. Johns County Non-Compliance Violations
    comp_cases = fetch_st_johns_compliance_distress()
    for rec in comp_cases:
        raw_pn = str(rec.get("Parcel_Number") or "").strip()
        clean_pn = raw_pn.lstrip('0')
        raw_addr = str(rec.get("Address") or "").strip()
        na = norm_addr(clean_scf_address(raw_addr))

        m = None
        if raw_pn and raw_pn in pid_lookup:
            m = pid_lookup[raw_pn]
        elif clean_pn and clean_pn in pid_lstrip_lookup:
            m = pid_lstrip_lookup[clean_pn]
        elif na and na in addr_lookup:
            m = addr_lookup[na]

        if not m:
            continue

        pid = str(m.get("PARCEL_NUMBER") or raw_pn).strip()
        lead_key = f"{pid}_ce"
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

        comments = str(rec.get("Comments") or "").strip()
        notes = f"St. Johns Code Non-Compliance Violation (Unregistered / Unpermitted Property). {comments}".strip()
        if len(notes) > 180:
            notes = notes[:177] + "..."

        reg_num = rec.get("Registration_Number") or f"CE-{pid[:10]}"

        lead_row = {
            "Match_Status": "MATCHED",
            "Match_Confidence": 98.0,
            "Match_Method": "PARCEL_ID_PIN_MATCH",
            "Match_Notes": notes,
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "St. Augustine")),
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
            "Distress_Stack_Notes": notes,
            "Is_Stacked_Distress": "No",
            "Case_Number": str(reg_num),
            "Source_File": "St_Johns_Code_Enforcement_Live_API",
            "Filing_Date": datetime.date.today().isoformat(),
            "Photo_Url": ""
        }
        matched_rows.append(lead_row)

    # 2. SeeClickFix
    scf_cases = fetch_st_johns_seeclickfix_distress()
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
            "Match_Notes": f"St. Johns Code Distress #{scf_id}: {scf_summary}",
            "Clean_First_Name": "",
            "Clean_Last_Name": "",
            "Clean_Full_Name": clean_display_name(str(m.get("OWNER1") or "")),
            "Owner_Entity_Type": "Individual" if "LLC" not in str(m.get("OWNER1") or "").upper() and "INC" not in str(m.get("OWNER1") or "").upper() else "Corporate",
            "Is_Trust_Or_Estate": "Yes" if any(w in str(m.get("OWNER1") or "").upper() for w in ["TRUST", "ESTATE", "TR", "TRS"]) else "No",
            "County_Owner_1": clean_display_name(str(m.get("OWNER1") or "")),
            "County_Owner_2": "",
            "Secondary_Owner": "",
            "Property_Address": clean_display_address(site_addr),
            "Property_City": clean_display_city(str(m.get("SITE_CITY") or "St. Augustine")),
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
            "Distress_Stack_Notes": f"St. Johns Property Distress: {scf_summary}",
            "Is_Stacked_Distress": "No",
            "Case_Number": f"SCF-{scf_id}",
            "Source_File": "St_Johns_SeeClickFix_Live_API",
            "Filing_Date": created_at,
            "Photo_Url": media_url
        }
        matched_rows.append(lead_row)

    print(f"[St. Johns API Sync] Matched leads generated: {len(matched_rows):,}", flush=True)

    target_columns = [
        "Match_Status", "Match_Confidence", "Match_Method", "Match_Notes",
        "Clean_First_Name", "Clean_Last_Name", "Clean_Full_Name", "Owner_Entity_Type",
        "Is_Trust_Or_Estate", "County_Owner_1", "County_Owner_2", "Secondary_Owner",
        "Property_Address", "Property_City", "Property_Zip", "Parcel_ID", "Strap",
        "Mailing_Address", "Mailing_City", "Mailing_State", "Mailing_Zip",
        "Absentee_Status", "Is_Absentee", "Homestead_Exemption",
        "Market_Value", "Assessed_Value", "Year_Built", "Living_Sqft",
        "Legal_Description", "Lead_Type", "All_Lead_Types", "Distress_Stack_Notes",
        "Is_Stacked_Distress", "Case_Number", "Source_File", "Filing_Date", "Photo_Url"
    ]

    if not matched_rows:
        if os.path.exists(leads_parquet) and os.path.getsize(leads_parquet) > 1000:
            existing_df = pd.read_parquet(leads_parquet)
            return {
                "status": "success",
                "county": os.path.basename(os.path.dirname(leads_parquet)),
                "total_leads": len(existing_df),
                "unique_properties": len(existing_df["Parcel_ID"].unique()) if "Parcel_ID" in existing_df.columns else len(existing_df),
                "cache_file": leads_parquet,
                "message": "No new leads in live poll; preserved existing verified cache."
            }
        empty_df = pd.DataFrame(columns=target_columns)
        empty_df.to_parquet(leads_parquet, index=False)
        return {
            "status": "success",
            "county": os.path.basename(os.path.dirname(leads_parquet)),
            "total_leads": 0,
            "cache_file": leads_parquet,
            "message": "Initialized empty matched leads cache."
        }

    leads_df = pd.DataFrame(matched_rows)

    pid_counts = leads_df["Parcel_ID"].value_counts()
    stacked_pids = set(pid_counts[pid_counts > 1].index)
    leads_df["Is_Stacked_Distress"] = leads_df["Parcel_ID"].apply(lambda x: "Yes" if x in stacked_pids else "No")

    for p_id in stacked_pids:
        sub = leads_df[leads_df["Parcel_ID"] == p_id]
        types_combined = sorted(list(set(sub["Lead_Type"].tolist())))
        for idx in sub.index:
            leads_df.at[idx, "All_Lead_Types"] = types_combined

    if os.path.exists(leads_parquet) and os.path.getsize(leads_parquet) > 1000:


        try:


            _existing_df = pd.read_parquet(leads_parquet)


            if len(_existing_df) > 0 and "Parcel_ID" in _existing_df.columns:


                leads_df = pd.concat([_existing_df, leads_df], ignore_index=True).drop_duplicates(subset=["Parcel_ID"]).reset_index(drop=True)


        except Exception:


            pass


    leads_df.to_parquet(leads_parquet, index=False)
    file_size_kb = os.path.getsize(leads_parquet) / 1024

    stats = {
        "status": "success",
        "county": "st._johns",
        "county_name": "St. Johns County",
        "total_leads": len(leads_df),
        "unique_properties": len(leads_df["Parcel_ID"].unique()),
        "stacked_distress_count": len(stacked_pids),
        "absentee_owners": int((leads_df["Is_Absentee"] == "Yes").sum()),
        "cache_file": leads_parquet,
        "cache_size_kb": round(file_size_kb, 1),
        "sync_timestamp": datetime.datetime.now().isoformat()
    }

    print(f"[St. Johns API Sync] COMPLETE: {stats['total_leads']:,} leads saved to {leads_parquet} ({file_size_kb:.1f} KB)", flush=True)
    return stats

if __name__ == "__main__":
    res = sync_st_johns_leads(force_refresh=True)
    print(json.dumps(res, indent=2))
