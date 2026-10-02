import os
import json
from typing import Dict, Any

try:
    from src.link_zone_service import link_zone_service
except ImportError:
    try:
        from link_zone_service import link_zone_service
    except ImportError:
        link_zone_service = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(BASE_DIR, "src", "county_portals.json")

DEFAULT_COUNTIES = {
    "Pinellas": {
        "full_name": "Pinellas County",
        "folder_name": "pinellas",
        "csv_name": "RP_PROPERTY_INFO.csv",
        "parquet_name": "RP_PROPERTY_INFO.parquet",
        "sample_lp": "pinellas_lis_pendens_20260920.csv",
        "sample_code": "pinellas_code_violations_20260920.csv",
        "sample_probate": "pinellas_probate_20260920.csv",
        "master_parcel_download_url": "https://www.pcpao.gov/tools-data/data-downloads/raw-database-files",
        "clerk_lis_pendens_url": "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType",
        "code_enforcement_url": "https://aca-prod.accela.com/PINELLAS/Cap/CapHome.aspx?module=Enforcement&TabName=Home",
        "tax_liens_url": "https://pinellas.county-taxes.com/public",
        "clerk_probate_url": "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType"
    },
    "Hillsborough": {
        "full_name": "Hillsborough County",
        "folder_name": "hillsborough",
        "csv_name": "RP_PROPERTY_INFO.csv",
        "parquet_name": "RP_PROPERTY_INFO.parquet",
        "sample_lp": "",
        "sample_code": "",
        "sample_probate": "",
        "master_parcel_download_url": "https://www.hcpafl.org/Property-Search/Data-Downloads",
        "clerk_lis_pendens_url": "https://pubrec3.hillsclerk.com/oncore/",
        "code_enforcement_url": "https://hcfl.gov/residents/property-owners-and-renters/code-violations",
        "tax_liens_url": "https://hillsborough.county-taxes.com/public",
        "clerk_probate_url": "https://pubrec3.hillsclerk.com/oncore/"
    },
    "Pasco": {
        "full_name": "Pasco County",
        "folder_name": "pasco",
        "csv_name": "RP_PROPERTY_INFO.csv",
        "parquet_name": "RP_PROPERTY_INFO.parquet",
        "sample_lp": "",
        "sample_code": "",
        "sample_probate": "",
        "master_parcel_download_url": "https://www.pascopa.com/resources/data-downloads/",
        "clerk_lis_pendens_url": "https://www.pascoclerk.com/161/Official-Records",
        "code_enforcement_url": "https://www.pascocountyfl.net/227/Code-Compliance",
        "tax_liens_url": "https://pasco.county-taxes.com/public",
        "clerk_probate_url": "https://www.pascoclerk.com/161/Official-Records"
    },
    "Manatee": {
        "full_name": "Manatee County",
        "folder_name": "manatee",
        "csv_name": "RP_PROPERTY_INFO.csv",
        "parquet_name": "RP_PROPERTY_INFO.parquet",
        "sample_lp": "",
        "sample_code": "",
        "sample_probate": "",
        "master_parcel_download_url": "https://www.manateepao.gov/data-downloads/",
        "clerk_lis_pendens_url": "https://records.manateeclerk.com/",
        "code_enforcement_url": "https://www.mymanatee.org/departments/code_enforcement",
        "tax_liens_url": "https://manatee.county-taxes.com/public",
        "clerk_probate_url": "https://records.manateeclerk.com/"
    },
    "Sarasota": {
        "full_name": "Sarasota County",
        "folder_name": "sarasota",
        "csv_name": "RP_PROPERTY_INFO.csv",
        "parquet_name": "RP_PROPERTY_INFO.parquet",
        "sample_lp": "",
        "sample_code": "",
        "sample_probate": "",
        "master_parcel_download_url": "https://www.sc-pa.com/downloads/",
        "clerk_lis_pendens_url": "https://clerk.sarasotaclerk.com/",
        "code_enforcement_url": "https://www.scgov.net/government/planning-and-development-services/code-enforcement",
        "tax_liens_url": "https://sarasotataxcollector.eswtax.com/",
        "clerk_probate_url": "https://clerk.sarasotaclerk.com/"
    },
    "Polk": {
        "full_name": "Polk County",
        "folder_name": "polk",
        "csv_name": "RP_PROPERTY_INFO.csv",
        "parquet_name": "RP_PROPERTY_INFO.parquet",
        "sample_lp": "",
        "sample_code": "",
        "sample_probate": "",
        "master_parcel_download_url": "https://www.polkpa.org/downloads/",
        "clerk_lis_pendens_url": "https://pro.polkcountyclerk.net/",
        "code_enforcement_url": "https://www.polk-county.net/services/code-enforcement/",
        "tax_liens_url": "https://polktaxes.com/",
        "clerk_probate_url": "https://pro.polkcountyclerk.net/"
    },
    "Orange": {
        "full_name": "Orange County",
        "folder_name": "orange",
        "csv_name": "RP_PROPERTY_INFO.csv",
        "parquet_name": "RP_PROPERTY_INFO.parquet",
        "sample_lp": "",
        "sample_code": "",
        "sample_probate": "",
        "master_parcel_download_url": "https://www.ocpafl.org/searches/DataDownloads.aspx",
        "clerk_lis_pendens_url": "https://selfservice.or.occompt.com/ssweb/search/DOCSEARCH2950S3",
        "code_enforcement_url": "https://netapps.ocfl.net/CETitleViolationSearch/",
        "tax_liens_url": "https://octaxcol.com/",
        "clerk_probate_url": "https://www.myorangeclerk.com/"
    },
    "Osceola": {
        "full_name": "Osceola County",
        "folder_name": "osceola",
        "csv_name": "RP_PROPERTY_INFO.csv",
        "parquet_name": "RP_PROPERTY_INFO.parquet",
        "sample_lp": "",
        "sample_code": "",
        "sample_probate": "",
        "master_parcel_download_url": "https://www.property-appraiser.org/data/?utm_source=gemini",
        "clerk_lis_pendens_url": "https://officialrecords.osceolaclerk.org/browserview/",
        "code_enforcement_url": "https://www.osceola.org/agencies-departments/community-development/code-enforcement/",
        "code_enforcement_note": "Choose Board of County Commissioners (BOCC) Records for code enforcement by email request only",
        "tax_liens_url": "https://osceola.county-taxes.com/public",
        "clerk_probate_url": "https://records.osceolaclerk.org/"
    }
}

DEFAULT_STATES = {
    "FL": {
        "code": "FL",
        "name": "Florida",
        "icon": "🌴",
        "tagline": "Opportunity Lives Here",
        "script_text": "Florida",
        "default_county": "Pinellas"
    }
}

def load_available_states() -> list:
    """Return all active states (discovers folders in data/ matching active state codes)."""
    states = []
    for code, info in DEFAULT_STATES.items():
        state_dir = os.path.join(DATA_DIR, code)
        if os.path.exists(state_dir) or code == "FL":
            states.append({
                "code": code,
                "name": info["name"],
                "icon": info["icon"],
                "tagline": info["tagline"],
                "script_text": info["script_text"],
                "default_county": info["default_county"]
            })
    return states

def load_county_portals(state: str = "FL") -> Dict[str, Any]:
    """Load county registry via Live Link Zone service, falling back to CONFIG_FILE."""
    state = (state or "FL").upper()
    registry = {}

    # 1. Try Live Link Zone Service first (direct read from C:\Projects\Apps\link-zone\data)
    if link_zone_service:
        try:
            live = link_zone_service.get_state_portals(state=state)
            if live and isinstance(live, dict) and len(live) > 0:
                registry = {k: dict(v) for k, v in live.items()}
        except Exception:
            registry = {}

    # 2. Fallback to local CONFIG_FILE if live link returns nothing
    if not registry and os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                if state in raw and isinstance(raw[state], dict):
                    registry = raw[state]
                else:
                    registry = {k: v for k, v in raw.items() if v.get("state", "FL") == state}
        except Exception:
            registry = {k: dict(v) for k, v in DEFAULT_COUNTIES.items()}

    if not registry:
        registry = {k: dict(v) for k, v in DEFAULT_COUNTIES.items()}

    # Ensure Pinellas has local file paths preserved when state is FL
    if state == "FL" and "Pinellas" in registry:
        registry["Pinellas"]["sample_lp"] = "pinellas_lis_pendens_20260920.csv"
        registry["Pinellas"]["sample_code"] = "pinellas_code_violations_20260920.csv"
        registry["Pinellas"]["sample_probate"] = "pinellas_probate_20260920.csv"
        registry["Pinellas"]["folder_name"] = "pinellas"

    for k in registry:
        registry[k]["state"] = state

    # Auto-discover any new county directories in data/<state>/ and data/
    modified = False
    existing_folders = {v.get("folder_name", k.lower()) for k, v in registry.items()}
    state_dir = os.path.join(DATA_DIR, state)
    dirs_to_check = [state_dir, DATA_DIR]

    for d in dirs_to_check:
        if os.path.exists(d):
            for item in sorted(os.listdir(d)):
                item_path = os.path.join(d, item)
                if os.path.isdir(item_path) and not item.startswith('.') and item.upper() not in DEFAULT_STATES:
                    folder_lower = item.lower()
                    if folder_lower not in existing_folders:
                        clean_name = item.replace('_', ' ').replace('-', ' ').title()
                        registry[clean_name] = {
                            "full_name": f"{clean_name} County",
                            "folder_name": item,
                            "state": state,
                            "csv_name": "RP_PROPERTY_INFO.csv",
                            "parquet_name": "RP_PROPERTY_INFO.parquet",
                            "sample_lp": "",
                            "sample_code": "",
                            "sample_probate": "",
                            "clerk_lis_pendens_url": "",
                            "code_enforcement_url": "",
                            "master_parcel_download_url": ""
                        }
                        existing_folders.add(folder_lower)
                        modified = True

    if modified or not os.path.exists(CONFIG_FILE):
        save_county_portals(registry, state=state)

    return registry

def save_county_portals(data: Dict[str, Any], state: str = "FL"):
    """Save county registry to JSON file, preserving state structure."""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    all_portals = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                all_portals = json.load(f)
        except Exception:
            all_portals = {}

    state = (state or "FL").upper()
    all_portals[state] = data
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_portals, f, indent=4)

def update_county_portal_urls(county_key: str, portal_dict: Dict[str, str], state: str = "FL") -> Dict[str, Any]:
    """Update portal URLs for a specific county and save to CONFIG_FILE."""
    registry = load_county_portals(state=state)
    if county_key not in registry:
        registry[county_key] = dict(DEFAULT_COUNTIES.get(county_key, {}))
        registry[county_key]["state"] = state
    
    for k, v in portal_dict.items():
        if v is not None and k in [
            "master_parcel_download_url", 
            "clerk_lis_pendens_url", 
            "code_enforcement_url", 
            "tax_liens_url", 
            "clerk_probate_url"
        ]:
            registry[county_key][k] = str(v).strip()
            
    save_county_portals(registry, state=state)
    return registry[county_key]

def get_county_paths(county_key: str, state: str = "FL") -> Dict[str, Any]:
    """Resolve directory paths and check parcel file status for a given county and state."""
    state = (state or "FL").upper()
    registry = load_county_portals(state=state)
    info = registry.get(county_key, DEFAULT_COUNTIES.get(county_key, {}))
    folder = info.get("folder_name", county_key.lower())
    
    # Priority:
    # 1. data/<state>/<folder> (e.g. data/FL/pinellas/)
    # 2. data/<folder> (e.g. data/pinellas/)
    # 3. root /<folder> (e.g. pinellas/)
    dir_path_state = os.path.join(DATA_DIR, state, folder)
    dir_path_data = os.path.join(DATA_DIR, folder)
    dir_path_root = os.path.join(BASE_DIR, folder)
    
    if os.path.exists(dir_path_state):
        target_dir = dir_path_state
    elif os.path.exists(dir_path_data) and any(os.scandir(dir_path_data)):
        target_dir = dir_path_data
    elif os.path.exists(dir_path_root) and any(os.scandir(dir_path_root)):
        target_dir = dir_path_root
    else:
        target_dir = dir_path_state
        os.makedirs(target_dir, exist_ok=True)
    
    parquet_path = os.path.join(target_dir, info.get("parquet_name", "RP_PROPERTY_INFO.parquet"))
    csv_path = os.path.join(target_dir, info.get("csv_name", "RP_PROPERTY_INFO.csv"))

    # Fallback to check alternative location if not found in target_dir
    alt_dirs = [dir_path_state, dir_path_data, dir_path_root]
    if not os.path.exists(parquet_path):
        for ad in alt_dirs:
            if ad != target_dir and os.path.exists(ad):
                alt_p = os.path.join(ad, info.get("parquet_name", "RP_PROPERTY_INFO.parquet"))
                if os.path.exists(alt_p):
                    target_dir = ad
                    parquet_path = alt_p
                    csv_path = os.path.join(target_dir, info.get("csv_name", "RP_PROPERTY_INFO.csv"))
                    break
    
    # Auto-detect any .parquet file in folder if default named file is not found
    if not os.path.exists(parquet_path):
        p_files = [os.path.join(target_dir, f) for f in os.listdir(target_dir) if f.lower().endswith('.parquet')]
        if p_files:
            parquet_path = p_files[0]

    # Auto-detect any master .csv file in folder if default named file is not found
    if not os.path.exists(csv_path):
        exclude_kws = [
            'sample', 'lispendens', 'lis_pendens', 'record', 'search', 'result',
            'code', 'violation', 'violations', 'cases', 'leads', 'probate', 'estate', 'wills'
        ]
        c_files = [os.path.join(target_dir, f) for f in os.listdir(target_dir) 
                   if f.lower().endswith('.csv') and not any(k in f.lower() for k in exclude_kws)]
        if c_files:
            csv_path = c_files[0]
            
    # Check if either parquet or csv exists and is valid size
    has_master = (os.path.exists(parquet_path) and os.path.getsize(parquet_path) > 10000) or (os.path.exists(csv_path) and os.path.getsize(csv_path) > 10000)
    
    # Resolve sample Lis Pendens
    sample_lp = os.path.join(target_dir, info.get("sample_lp", "")) if info.get("sample_lp") else ""
    if not (sample_lp and os.path.exists(sample_lp)):
        lp_matches = [
            os.path.join(target_dir, f) for f in os.listdir(target_dir)
            if any(k in f.lower() for k in ['lis_pendens', 'lispendens', 'foreclosure', 'lp']) and f.lower().endswith(('.csv', '.xlsx'))
        ]
        sample_lp = lp_matches[0] if lp_matches else ""

    # Resolve sample Code Violations
    sample_code = os.path.join(target_dir, info.get("sample_code", "")) if info.get("sample_code") else ""
    if not (sample_code and os.path.exists(sample_code)):
        code_matches = [
            os.path.join(target_dir, f) for f in os.listdir(target_dir)
            if any(k in f.lower() for k in ['code', 'violation', 'recordlist']) and f.lower().endswith(('.csv', '.xlsx'))
        ]
        sample_code = code_matches[0] if code_matches else ""

    # Resolve sample Probate
    sample_probate = os.path.join(target_dir, info.get("sample_probate", "")) if info.get("sample_probate") else ""
    if not (sample_probate and os.path.exists(sample_probate)):
        probate_matches = [
            os.path.join(target_dir, f) for f in os.listdir(target_dir)
            if any(k in f.lower() for k in ['probate', 'estate', 'decedent', 'wills', 'letters_of_admin']) and f.lower().endswith(('.csv', '.xlsx'))
        ]
        sample_probate = probate_matches[0] if probate_matches else ""
    
    rel_dir = os.path.relpath(target_dir, BASE_DIR)
    
    return {
        "county_key": county_key,
        "full_name": info.get("full_name", f"{county_key} County"),
        "target_dir": target_dir,
        "relative_dir": rel_dir,
        "parquet_path": parquet_path,
        "csv_path": csv_path,
        "has_master": has_master,
        "sample_lp": sample_lp if (sample_lp and os.path.exists(sample_lp)) else "",
        "sample_code": sample_code if (sample_code and os.path.exists(sample_code)) else "",
        "sample_probate": sample_probate if (sample_probate and os.path.exists(sample_probate)) else "",
        "clerk_lis_pendens_url": info.get("clerk_lis_pendens_url", ""),
        "clerk_probate_url": info.get("clerk_probate_url", "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType"),
        "code_enforcement_url": info.get("code_enforcement_url", ""),
        "code_enforcement_note": info.get("code_enforcement_note", ""),
        "tax_liens_url": info.get("tax_liens_url", ""),
        "master_parcel_download_url": info.get("master_parcel_download_url", "")
    }

CUSTOM_CATEGORIES_FILE = os.path.join(BASE_DIR, "src", "custom_categories.json")

def load_custom_categories() -> list:
    """Load user-defined custom distress categories."""
    if os.path.exists(CUSTOM_CATEGORIES_FILE):
        try:
            with open(CUSTOM_CATEGORIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_custom_categories(categories: list):
    """Save user-defined custom categories."""
    os.makedirs(os.path.dirname(CUSTOM_CATEGORIES_FILE), exist_ok=True)
    with open(CUSTOM_CATEGORIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(categories, f, indent=4)

def add_custom_category(cat_dict: dict) -> list:
    """Add or update a custom category."""
    cats = load_custom_categories()
    cat_id = cat_dict.get("id") or cat_dict.get("name", "").lower().replace(" ", "_")
    cat_dict["id"] = cat_id
    cats = [c for c in cats if c.get("id") != cat_id]
    cats.append(cat_dict)
    save_custom_categories(cats)
    return cats

def delete_custom_category(cat_id: str) -> list:
    """Delete a custom category by id."""
    cats = load_custom_categories()
    cats = [c for c in cats if c.get("id") != cat_id]
    save_custom_categories(cats)
    return cats

