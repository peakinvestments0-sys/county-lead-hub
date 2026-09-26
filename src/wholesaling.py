import pandas as pd
from typing import Dict, Any
from src.normalizer import parse_owner_name, normalize_address

PINELLAS_CITIES = {
    'ST PETERSBURG', 'SAINT PETERSBURG', 'CLEARWATER', 'LARGO', 'DUNEDIN',
    'PINELLAS PARK', 'TARPON SPRINGS', 'SEMINOLE', 'SAFETY HARBOR', 'OLDSMAR',
    'GULFPORT', 'ST PETE BEACH', 'TREASURE ISLAND', 'INDIAN ROCKS BEACH',
    'MADEIRA BEACH', 'BELLEAIR', 'BELLEAIR BLUFFS', 'BELLEAIR BEACH',
    'SOUTH PASADENA', 'KENNETH CITY', 'INDIAN SHORES', 'REDINGTON SHORES',
    'NORTH REDINGTON BEACH', 'REDINGTON BEACH', 'PALM HARBOR', 'EAST LAKE'
}

def determine_absentee_status(site_addr: str, site_city: str, site_zip: str,
                              mail_addr: str, mail_city: str, mail_state: str, mail_zip: str,
                              has_homestead: bool) -> Dict[str, Any]:
    """
    Determines whether a property is Owner-Occupied or Absentee-Owned (Local, Out of County, Out of State).
    Crucial signal for real estate wholesalers and direct marketing response rates.
    """
    clean_site_addr = normalize_address(site_addr)
    clean_mail_addr = normalize_address(mail_addr)
    
    mail_state_clean = str(mail_state).strip().upper() if mail_state and str(mail_state) != 'nan' else ""
    mail_city_clean = str(mail_city).strip().upper() if mail_city and str(mail_city) != 'nan' else ""
    
    # 1. Out of State Absentee
    if mail_state_clean and mail_state_clean != 'FL':
        return {
            'Absentee_Status': 'Absentee Out-of-State',
            'Is_Absentee': 'Yes',
            'Absentee_Priority': 'High'
        }
        
    # 2. Check address match
    addresses_match = False
    if clean_site_addr and clean_mail_addr:
        # Check if identical or street number and first word of street name match
        if clean_site_addr == clean_mail_addr:
            addresses_match = True
        else:
            site_parts = clean_site_addr.split()
            mail_parts = clean_mail_addr.split()
            if len(site_parts) >= 2 and len(mail_parts) >= 2:
                if site_parts[0] == mail_parts[0] and site_parts[1] == mail_parts[1]:
                    addresses_match = True
                    
    if addresses_match:
        return {
            'Absentee_Status': 'Owner Occupied',
            'Is_Absentee': 'No',
            'Absentee_Priority': 'Standard'
        }
        
    # If addresses don't match:
    # Check if city is outside Pinellas
    if mail_city_clean and mail_city_clean not in PINELLAS_CITIES:
        return {
            'Absentee_Status': 'Absentee Out-of-County (FL)',
            'Is_Absentee': 'Yes',
            'Absentee_Priority': 'High'
        }
        
    # Same county, different address
    if clean_mail_addr and not addresses_match:
        return {
            'Absentee_Status': 'Absentee In-County',
            'Is_Absentee': 'Yes',
            'Absentee_Priority': 'Medium'
        }
        
    # Fallback to homestead exemption status
    if has_homestead:
        return {
            'Absentee_Status': 'Owner Occupied',
            'Is_Absentee': 'No',
            'Absentee_Priority': 'Standard'
        }
        
    return {
        'Absentee_Status': 'Likely Absentee / Unknown',
        'Is_Absentee': 'Yes',
        'Absentee_Priority': 'Medium'
    }

def enrich_wholesale_record(county_row: Dict[str, Any], subject_row: Dict[str, Any],
                           match_meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enriches matched record with wholesaling metadata:
    - Clean individual first & last names
    - Property site address & mailing address
    - Absentee classification
    - Value & equity signals
    - Retains all subject columns (lis pendens case/comments, dates, etc.)
    """
    # 1. Parse Owner Name from county record
    owner1 = str(county_row.get('OWNER1', '')) if pd.notna(county_row.get('OWNER1')) else ''
    parsed_owner = parse_owner_name(owner1)
    
    # 2. Extract Addresses
    site_address = str(county_row.get('SITE_ADDRESS', '')).strip() if pd.notna(county_row.get('SITE_ADDRESS')) else ''
    site_cityzip = str(county_row.get('SITE_CITYZIP', '')).strip() if pd.notna(county_row.get('SITE_CITYZIP')) else ''
    
    # Parse city and zip from site_cityzip if needed
    site_city = str(county_row.get('STR_CITY', '')).strip() if pd.notna(county_row.get('STR_CITY')) else ''
    site_zip = str(county_row.get('STR_ZIP', '')).strip() if pd.notna(county_row.get('STR_ZIP')) else ''
    if not site_city and ',' in site_cityzip:
        site_city = site_cityzip.split(',')[0].strip()
        
    mail_address = str(county_row.get('MAILING_ADDRESS_1', '')).strip() if pd.notna(county_row.get('MAILING_ADDRESS_1')) else ''
    mail_city = str(county_row.get('MAILING_CITY', '')).strip() if pd.notna(county_row.get('MAILING_CITY')) else ''
    mail_state = str(county_row.get('MAILING_STATE', '')).strip() if pd.notna(county_row.get('MAILING_STATE')) else ''
    mail_zip = str(county_row.get('MAILING_ZIP', '')).strip() if pd.notna(county_row.get('MAILING_ZIP')) else ''
    
    # 3. Homestead Exemption
    hx_cap = str(county_row.get('HX_CAP', '')).strip().lower()
    has_homestead = hx_cap == 'yes'
    
    # 4. Absentee Status
    absentee_info = determine_absentee_status(
        site_addr=site_address,
        site_city=site_city,
        site_zip=site_zip,
        mail_addr=mail_address,
        mail_city=mail_city,
        mail_state=mail_state,
        mail_zip=mail_zip,
        has_homestead=has_homestead
    )
    
    # 5. Financial & Property Characteristics
    def _safe_float(val, default=0.0):
        try:
            if pd.isna(val) or val == '' or val is None:
                return default
            if isinstance(val, str):
                val = val.replace('$', '').replace(',', '').strip()
            return float(val)
        except (ValueError, TypeError):
            return default

    just_val = _safe_float(county_row.get('CNTY_JST_VALUE', 0))
    asd_val = _safe_float(county_row.get('CNTY_ASD_VALUE', 0))
    tax_val = _safe_float(county_row.get('CNTY_TAXABLE_VALUE', 0))
    
    result = {
        # Match Info
        'Match_Status': match_meta.get('status', 'MATCHED'),
        'Match_Confidence': match_meta.get('confidence', 100),
        'Match_Method': match_meta.get('method', ''),
        'Match_Notes': match_meta.get('notes', ''),
        
        # Clean Names for Direct Outreach (Cold Call, SMS, Postcard)
        'Clean_First_Name': parsed_owner['Clean_First_Name'],
        'Clean_Last_Name': parsed_owner['Clean_Last_Name'],
        'Clean_Full_Name': parsed_owner['Clean_Full_Name'],
        'Owner_Entity_Type': parsed_owner['Owner_Entity_Type'],
        'Is_Trust_Or_Estate': parsed_owner['Is_Trust_Or_Estate'],
        'County_Owner_1': owner1,
        'County_Owner_2': str(county_row.get('OWNER2', '')) if pd.notna(county_row.get('OWNER2')) else '',
        'Secondary_Owner': parsed_owner['Secondary_Owner'],
        
        # Physical Property Location
        'Property_Address': site_address,
        'Property_City': site_city,
        'Property_Zip': site_zip,
        'Parcel_ID': str(county_row.get('PARCEL_NUMBER', '')),
        'Strap': str(county_row.get('STRAP', '')),
        
        # Mailing Address for Mailers
        'Mailing_Address': mail_address,
        'Mailing_City': mail_city,
        'Mailing_State': mail_state,
        'Mailing_Zip': mail_zip,
        'Absentee_Status': absentee_info['Absentee_Status'],
        'Is_Absentee': absentee_info['Is_Absentee'],
        'Absentee_Priority': absentee_info['Absentee_Priority'],
        
        # Wholesale Equity & Metrics
        'Homestead_Exemption': 'Yes' if has_homestead else 'No',
        'Market_Value': just_val,
        'Assessed_Value': asd_val,
        'Taxable_Value': tax_val,
        'Year_Built': county_row.get('YEAR_BUILT', ''),
        'Living_Sqft': county_row.get('TOTAL_LIVING_SQFT', ''),
        'Property_Type': str(county_row.get('PARCEL_TYPE', '')),
        'Property_Use': str(county_row.get('PROPERTY_USE', '')),
        'County_Book_Page': str(county_row.get('OR_BOOK_PAGE', '')),
        'Legal_Description': str(county_row.get('LEGAL', '')).strip()
    }
    
    # 6. Append all original Subject columns with prefix to prevent collision
    for k, v in subject_row.items():
        if k not in result:
            result[f"Subject_{k}"] = v
            
    return result
