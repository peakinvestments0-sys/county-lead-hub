import os
import re
import io
import urllib.request
import pypdf
import pandas as pd
from datetime import datetime

DATA_DIR = r"C:\Projects\Apps\Pinellas-county-app\data\FL\Seminole"
PARQUET_PATH = os.path.join(DATA_DIR, "RP_PROPERTY_INFO.parquet")
CACHE_PATH = os.path.join(DATA_DIR, "matched_leads_cache.parquet")
CSV_OUTPUT_PATH = os.path.join(DATA_DIR, "Seminole_County_Legal_Distress_Leads.csv")
INDEX_URL = "https://www.seminolesheriff.org/reports/List.aspx?mediareporttypeid=2"

FELONY_KEYWORDS = [
    'FELONY', 'AGGRAVATED', 'BURGLARY', 'ROBBERY', 'CHILD NEGLECT', 'TRAFFICKING',
    'GRAND THEFT', 'POSSESS CONTROLLED SUBSTANCE', 'FLEEING', 'FIREARM', 'WEAPON',
    'BATTERY ON LAW ENFORCEMENT', 'LEWD', 'ESCAPE', 'FRAUD', 'FORGERY', 'UTTERING'
]

FELONY_STATUTE_PREFIXES = [
    '827.03', '893.13', '812.014', '784.021', '784.041', '784.045', '784.07',
    '810.02', '812.13', '790.23', '790.01', '316.1935', '843.01', '817.568', '831.01'
]

def is_felony_charge(text, statute=""):
    t = (text or '').upper()
    s = str(statute or '').strip()
    if any(k in t for k in FELONY_KEYWORDS):
        return True
    if any(s.startswith(p) for p in FELONY_STATUTE_PREFIXES):
        return True
    return False

def sync_seminole_county_jail_leads(max_reports=7):
    """
    Downloads recent daily jail PDF reports from Seminole County Sheriff's Office,
    extracts arrestees and charges, filters for felonies, matches against the 181k Seminole
    parcels, and writes matched_leads_cache.parquet.
    """
    print("=================================================================")
    print("SEMINOLE COUNTY JAIL LEGAL DISTRESS LEADS AGENT")
    print("=================================================================")
    os.makedirs(DATA_DIR, exist_ok=True)
    
    if not os.path.exists(PARQUET_PATH):
        raise FileNotFoundError(f"Seminole County Master Parquet not found at {PARQUET_PATH}")
        
    print(f"Fetching report index from {INDEX_URL}...")
    req = urllib.request.Request(INDEX_URL, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    html = urllib.request.urlopen(req).read().decode('utf-8', errors='ignore')
    
    pdf_paths = re.findall(r'href=[\x22\x27](/output/mediareports/\d+/\d+\.pdf)[\x22\x27]', html)
    if not pdf_paths:
        print("No PDF links found on Seminole index page.")
        return {"status": "error", "message": "No reports found on index"}
        
    pdf_paths = pdf_paths[:max_reports]
    print(f"Found {len(pdf_paths)} recent daily reports to process.")
    
    arrestees = []
    
    for p_url in pdf_paths:
        full_url = "https://www.seminolesheriff.org" + p_url
        try:
            p_req = urllib.request.Request(full_url, headers={'User-Agent': 'Mozilla/5.0'})
            pdf_bytes = urllib.request.urlopen(p_req).read()
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            full_text = "\n".join([p.extract_text() for p in reader.pages])
            
            # Extract date of report
            m_date = re.search(r'Booked Report Summary For Dates:\s*(\d{1,2}/\d{1,2}/\d{4})', full_text)
            report_date = m_date.group(1) if m_date else datetime.now().strftime("%m/%d/%Y")
            
            # Split into person blocks: blocks start with "LAST, FIRST"
            lines = [l.strip() for l in full_text.splitlines() if l.strip()]
            current_person = None
            
            for line in lines:
                if (
                    "Page " in line
                    or "Seminole County Sheriff" in line
                    or "Booked Report Summary" in line
                    or "Printed On:" in line
                    or "Public Version" in line
                    or "Arrestee's Name:" in line
                    or line in ["DOB:", "Sex:", "Race:", "Adult", "Count", "Description", "Statute", "Arrest Date"]
                ):
                    continue
                    
                # Header match: "LAST, FIRST MIDDLE"
                m_name = re.match(r'^([A-Z\s\-]+),\s+([A-Z\s\-]+)$', line)
                if m_name and not line.startswith("REVOKED") and not line.startswith("PRINTED"):
                    if current_person:
                        arrestees.append(current_person)
                        
                    raw_name = line.strip()
                    parts = raw_name.split(",")
                    last_name = parts[0].strip()
                    first_name = parts[1].strip().split()[0] if len(parts) > 1 else ""
                    
                    current_person = {
                        "raw_name": raw_name,
                        "last_name": last_name,
                        "first_name": first_name,
                        "report_date": report_date,
                        "bkg_num": "",
                        "inc_num": "",
                        "agency": "Seminole County Sheriff's Office",
                        "charges": [],
                        "statutes": [],
                        "is_felony": False
                    }
                    continue
                    
                if not current_person:
                    continue
                    
                # Booking #
                m_bkg = re.search(r'Bkg#:\s*(\d+)', line)
                if m_bkg and not current_person["bkg_num"]:
                    current_person["bkg_num"] = m_bkg.group(1).strip()
                    continue
                    
                # Incident #
                m_inc = re.search(r'Inc#:\s*(\d+)', line)
                if m_inc and not current_person["inc_num"]:
                    current_person["inc_num"] = m_inc.group(1).strip()
                    continue
                    
                # Agency
                if "Arresting Agency:" in line:
                    agency_clean = line.replace("Arresting Agency:", "").strip()
                    if agency_clean:
                        current_person["agency"] = agency_clean
                    continue
                    
                # Florida Statute line: e.g. "827.03-2d" or "316.193-1a"
                m_stat = re.search(r'\b(\d{3}\.\d+[\-\w]*)\b', line)
                if m_stat:
                    st = m_stat.group(1)
                    current_person["statutes"].append(st)
                    if is_felony_charge(line, st):
                        current_person["is_felony"] = True
                    continue
                    
                # Charge description line
                if len(line) > 4 and not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', line) and not re.match(r'^\d+$', line):
                    current_person["charges"].append(line)
                    if is_felony_charge(line):
                        current_person["is_felony"] = True
                        
            if current_person:
                arrestees.append(current_person)
                
        except Exception as e:
            print(f"Error processing {p_url}: {e}")
            
    print(f"Extracted {len(arrestees)} total arrest records across {len(pdf_paths)} reports.")
    felonies = [a for a in arrestees if a["is_felony"]]
    print(f"-> {len(felonies)} are facing FELONY criminal charges.")
    
    print("Loading Seminole County Master Parcel roll...")
    parcels = pd.read_parquet(PARQUET_PATH)
    
    def clean_name(s):
        if not isinstance(s, str): return ""
        return re.sub(r'[^A-Z\s]', '', s.upper()).strip()
        
    parcels['O1_CLEAN'] = parcels['OWNER1'].astype(str).str.upper().apply(clean_name)
    parcels['O2_CLEAN'] = parcels['OWNER2'].astype(str).str.upper().apply(clean_name)
    
    matched_rows = []
    
    for r in felonies:
        last = clean_name(r["last_name"])
        first = clean_name(r["first_name"])
        if len(last) < 2 or len(first) < 2:
            continue
            
        pat = f"^{last}\\b.*\\b{first}"
        mask1 = parcels['O1_CLEAN'].str.contains(pat, regex=True, na=False)
        mask2 = parcels['O2_CLEAN'].str.contains(pat, regex=True, na=False)
        hits = parcels[mask1 | mask2]
        
        for _, p in hits.iterrows():
            charges_str = " | ".join(r["charges"][:3]) if r["charges"] else "Criminal Felony Charge"
            statutes_str = " | ".join(r["statutes"][:3]) if r["statutes"] else ""
            bkg = r["bkg_num"] or "BKG-PENDING"
            
            # Calculate absentee status
            is_absentee = "No"
            abs_status = "Owner-Occupied"
            mail_addr = str(p.get("MAILING_ADDRESS_1", "")).strip().upper()
            site_addr = str(p.get("SITE_ADDRESS", "")).strip().upper()
            if mail_addr and site_addr and mail_addr != site_addr:
                is_absentee = "Yes"
                if str(p.get("MAILING_STATE", "FL")).strip().upper() != "FL":
                    abs_status = "Absentee (Out-of-State)"
                else:
                    abs_status = "Absentee (In-State)"
                    
            matched_rows.append({
                "Match_Status": "MATCHED",
                "Match_Confidence": "HIGH",
                "Match_Method": "Homeowner Name Cross-Reference (Seminole Sheriff Daily Booking PDF)",
                "Match_Notes": f"Arrest Booking #{bkg} - {r['agency']}",
                "Clean_First_Name": first,
                "Clean_Last_Name": last,
                "Clean_Full_Name": f"{first} {last}",
                "Owner_Entity_Type": "Individual",
                "Is_Trust_Or_Estate": "No",
                "County_Owner_1": p["OWNER1"],
                "County_Owner_2": p["OWNER2"] if pd.notna(p["OWNER2"]) else "",
                "Secondary_Owner": p["OWNER2"] if pd.notna(p["OWNER2"]) else "",
                "Property_Address": p["SITE_ADDRESS"],
                "Property_City": p["SITE_CITY"],
                "Property_Zip": str(p["SITE_ZIP"]) if pd.notna(p["SITE_ZIP"]) else "",
                "Parcel_ID": str(p["PARCEL_NUMBER"]),
                "Strap": str(p.get("STRAP", p["PARCEL_NUMBER"])),
                "Mailing_Address": p.get("MAILING_ADDRESS_1", ""),
                "Mailing_City": p.get("MAILING_CITY", ""),
                "Mailing_State": p.get("MAILING_STATE", "FL"),
                "Mailing_Zip": str(p.get("MAILING_ZIP", "")),
                "Absentee_Status": abs_status,
                "Is_Absentee": is_absentee,
                "Absentee_Priority": "High" if is_absentee == "Yes" else "Standard",
                "Homestead_Exemption": "Yes" if is_absentee == "No" else "No",
                "Market_Value": p["CNTY_JST_VALUE"],
                "Assessed_Value": p["CNTY_ASD_VALUE"],
                "Taxable_Value": p["CNTY_TAXABLE_VALUE"],
                "Year_Built": p["YEAR_BUILT"],
                "Living_Sqft": p["TOTAL_LIVING_SQFT"],
                "Property_Type": "Residential",
                "Property_Use": p["PROPERTY_USE"],
                "County_Book_Page": "",
                "Legal_Description": p.get("LEGAL", ""),
                "Subject_First Name": first,
                "Subject_Last Name": last,
                "Subject_Middle Name": "",
                "Subject_Suffix": "",
                "Subject_Full Name": r["raw_name"],
                "Subject_Recording Date": r["report_date"],
                "Subject_Document #": bkg,
                "Subject_Legal Description": "",
                "Subject_EXTRACTED_PARCEL": str(p["PARCEL_NUMBER"]),
                "Lead_Type": "Legal Distress (Felony)",
                "Source_File": INDEX_URL,
                "Subject_Case Number": statutes_str,
                "Subject_Case Status": "Held / Booking Processed",
                "Subject_Case Name": charges_str,
                "Subject_Resolution Code": "",
                "Subject_Source": r["agency"],
                "Subject_Case Comments": f"Charges: {charges_str} | Statutes: {statutes_str} | Booking #{bkg}",
                "Subject_Case Open Date": r["report_date"],
                "Document_Number": bkg,
                "Recording_Date": r["report_date"],
                "Case_Number": statutes_str,
                "Is_Stacked_Distress": "No",
                "Distress_Stack_Notes": f"⚖️ FELONY ARREST: {charges_str[:120]}"
            })
            
    print(f"Successfully matched {len(matched_rows)} property records for felony defendants!")
    df_new = pd.DataFrame(matched_rows)
    
    if len(df_new) > 0:
        # Deduplicate by Parcel_ID
        df_new = df_new.drop_duplicates(subset=["Parcel_ID"])
        df_new.to_csv(CSV_OUTPUT_PATH, index=False)
        print(f"Saved standalone CSV to {CSV_OUTPUT_PATH}")
        
        # Save to cache parquet
        for col in df_new.columns:
            if df_new[col].dtype == 'object':
                df_new[col] = df_new[col].fillna('').astype(str)
                
        df_new.to_parquet(CACHE_PATH, index=False)
        print(f"Saved matched leads cache to {CACHE_PATH}")
        
    return {
        "status": "success",
        "county": "Seminole",
        "reports_processed": len(pdf_paths),
        "total_arrestees": len(arrestees),
        "felony_arrestees": len(felonies),
        "matched_properties": len(df_new) if len(df_new) > 0 else 0,
        "csv_path": CSV_OUTPUT_PATH
    }

if __name__ == "__main__":
    res = sync_seminole_county_jail_leads(max_reports=7)
    print("\nSYNC RESULT:", res)
