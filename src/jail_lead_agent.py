import os
import re
import urllib.request
import pypdf
import pandas as pd
from datetime import datetime

PDF_URL = "https://netapps.ocfl.net/BestJail/PDF/bookings.pdf"
DATA_DIR = r"C:\Projects\Apps\Pinellas-county-app\data\FL\Orange"
PARQUET_PATH = os.path.join(DATA_DIR, "RP_PROPERTY_INFO.parquet")
CACHE_PATH = os.path.join(DATA_DIR, "matched_leads_cache.parquet")
CSV_OUTPUT_PATH = os.path.join(DATA_DIR, "Orange_County_Legal_Distress_Leads.csv")

def download_daily_pdf(save_path=None):
    if not save_path:
        save_path = os.path.join(DATA_DIR, "current_bookings.pdf")
    print(f"Downloading daily jail report from {PDF_URL}...")
    req = urllib.request.Request(PDF_URL, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(data)
    print(f"Downloaded {len(data):,} bytes to {save_path}.")
    return save_path

def parse_jail_pdf(pdf_path):
    reader = pypdf.PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n"

    # Extract report date if available
    report_date = datetime.now().strftime("%Y-%m-%d")
    m_rep_date = re.search(r"BEGINNING AT MIDNIGHT\s+(\d{1,2}/\d{1,2}/\d{4})", full_text)
    if m_rep_date:
        try:
            parsed_d = datetime.strptime(m_rep_date.group(1), "%m/%d/%Y")
            report_date = parsed_d.strftime("%Y-%m-%d")
        except Exception:
            pass

    records = []
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    current_person = None

    for line in lines:
        if (
            "ORANGE COUNTY JAIL BOOKING" in line
            or "BOOKINGS DURING THE" in line
            or "Page:" in line
            or "BEGINNING AT MIDNIGHT" in line
            or "Name Cell" in line
            or "Race/" in line
            or "Gender/" in line
            or "Ethnicity" in line
            or "Booking # Age" in line
        ):
            continue

        # Header match: "LAST, FIRST ... Booking # ..."
        m_head = re.match(r"^([A-Z\s\-]+,\s+[A-Z\s\-]+)\s+(.*?)\s*([WBAIOU]\s*/\s*[MF])\s*(\d{8})(.*)$", line)
        if m_head:
            if current_person:
                records.append(current_person)
            raw_name = m_head.group(1).strip()
            cell_info = m_head.group(2).strip()
            booking_num = m_head.group(4).strip()
            tail = m_head.group(5).strip()

            parts = raw_name.split(",")
            last_name = parts[0].strip()
            first_name = parts[1].strip().split()[0] if len(parts) > 1 else ""

            # Check if release date/time is in the tail
            m_rel = re.search(r"(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}(?:AM|PM))", tail)
            if m_rel:
                custody_status = "Released on Bond"
                release_datetime = m_rel.group(1)
            else:
                custody_status = "In Custody"
                release_datetime = ""

            current_person = {
                "raw_name": raw_name,
                "last_name": last_name,
                "first_name": first_name,
                "booking_number": booking_num,
                "cell": cell_info,
                "custody_status": custody_status,
                "release_datetime": release_datetime,
                "report_date": report_date,
                "city": "",
                "state": "FL",
                "zip": "",
                "age": "",
                "charges": [],
                "is_felony": False,
                "cases": [],
                "agencies": []
            }
            continue

        if not current_person:
            continue

        # City / State / ZIP line: "ORLANDO, FL  32835"
        m_addr = re.match(r"^([A-Z\s\-]+),\s*([A-Z]{2})\s*(\d{5})?$", line)
        if m_addr and not current_person["city"]:
            current_person["city"] = m_addr.group(1).strip()
            current_person["state"] = m_addr.group(2).strip()
            current_person["zip"] = m_addr.group(3).strip() if m_addr.group(3) else ""
            continue

        # Age line (number 16-99)
        if re.match(r"^\d{2}$", line) and not current_person["age"]:
            current_person["age"] = line
            continue

        # Case line
        if line.startswith("CASE:"):
            clean_case = line.replace("CASE:", "").strip()
            current_person["cases"].append(clean_case)
            if "CF" in clean_case.upper():
                current_person["is_felony"] = True
            continue

        # Charge lines
        if "FELONY" in line.upper():
            current_person["is_felony"] = True
            current_person["charges"].append(line)
        elif "MISDEMEANOR" in line.upper():
            current_person["charges"].append(line)

    if current_person:
        records.append(current_person)

    print(f"Extracted {len(records)} total arrestees from jail PDF for {report_date}.")
    felonies = [r for r in records if r["is_felony"]]
    print(f"-> {len(felonies)} are facing FELONY charges.")
    return records, report_date

def sync_orange_county_jail_leads(force_download=True):
    """
    Downloads or reads the Orange County daily jail PDF, filters for felonies,
    cross-references against 496k master parcels, and merges into matched_leads_cache.parquet.
    """
    pdf_path = os.path.join(DATA_DIR, "current_bookings.pdf")
    if force_download or not os.path.exists(pdf_path):
        download_daily_pdf(pdf_path)

    records, report_date = parse_jail_pdf(pdf_path)
    felonies = [r for r in records if r["is_felony"]]

    if not os.path.exists(PARQUET_PATH):
        raise FileNotFoundError(f"Orange County Master Parquet not found at {PARQUET_PATH}")

    print("Loading Orange County Master Parquet...")
    df_parcels = pd.read_parquet(PARQUET_PATH)

    def clean_name(s):
        if not isinstance(s, str): return ""
        return re.sub(r'[^A-Z\s]', '', s.upper()).strip()

    df_parcels['O1_CLEAN'] = df_parcels['OWNER1'].astype(str).str.upper().apply(clean_name)
    df_parcels['O2_CLEAN'] = df_parcels['OWNER2'].astype(str).str.upper().apply(clean_name)

    matched_rows = []

    for r in felonies:
        last = clean_name(r["last_name"])
        first = clean_name(r["first_name"])
        if len(last) < 2 or len(first) < 2:
            continue

        pat = f"^{last} {first}"
        mask1 = df_parcels['O1_CLEAN'].str.contains(pat, regex=True)
        mask2 = df_parcels['O2_CLEAN'].str.contains(pat, regex=True)
        hits = df_parcels[mask1 | mask2]

        for _, p in hits.iterrows():
            charges_str = " | ".join(r["charges"])
            cases_str = " | ".join(r["cases"])
            custody = r["custody_status"]
            if r["release_datetime"]:
                custody += f" ({r['release_datetime']})"

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
                "Match_Method": "Homeowner Name Cross-Reference (Orange County Daily Jail Booking PDF)",
                "Match_Notes": f"Arrest Booking #{r['booking_number']} - {custody}",
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
                "Property_Type": "Single Family Residential" if p["PROPERTY_USE"] in ["100", "103", "104"] else "Residential",
                "Property_Use": p["PROPERTY_USE"],
                "County_Book_Page": "",
                "Legal_Description": p.get("LEGAL", ""),
                "Subject_First Name": first,
                "Subject_Last Name": last,
                "Subject_Middle Name": "",
                "Subject_Suffix": "",
                "Subject_Full Name": r["raw_name"],
                "Subject_Recording Date": report_date,
                "Subject_Document #": r["booking_number"],
                "Subject_Legal Description": "",
                "Subject_EXTRACTED_PARCEL": str(p["PARCEL_NUMBER"]),
                "Lead_Type": "Legal Distress (Felony)",
                "Source_File": "https://netapps.ocfl.net/BestJail/PDF/bookings.pdf",
                "Subject_Case Number": cases_str,
                "Subject_Case Status": custody,
                "Subject_Case Name": charges_str,
                "Subject_Resolution Code": "",
                "Subject_Source": "Orange County Corrections Department",
                "Subject_Case Comments": f"Custody: {custody} | Charges: {charges_str} | Booking #{r['booking_number']}",
                "Subject_Case Open Date": report_date,
                "Document_Number": r["booking_number"],
                "Recording_Date": report_date,
                "Case_Number": cases_str,
                "Is_Stacked_Distress": "No",
                "Distress_Stack_Notes": f"⚖️ FELONY ARREST: {charges_str[:120]} ({custody})"
            })

    print(f"Matched {len(matched_rows)} property records for felony arrestees!")
    df_new_legal = pd.DataFrame(matched_rows)

    # Save standalone CSV
    df_new_legal.to_csv(CSV_OUTPUT_PATH, index=False)
    print(f"Saved {len(df_new_legal)} leads to {CSV_OUTPUT_PATH}")

    # Load existing matched leads cache and merge
    new_count = 0
    stacked_count = 0
    if os.path.exists(CACHE_PATH):
        try:
            df_cache = pd.read_parquet(CACHE_PATH)
            existing_pids = set(df_cache["Parcel_ID"].astype(str).dropna())
            
            # Identify which are stacked vs new
            for idx, row in df_new_legal.iterrows():
                pid = str(row["Parcel_ID"])
                if pid in existing_pids:
                    # Update existing record with stacked notes
                    stacked_mask = df_cache["Parcel_ID"].astype(str) == pid
                    df_cache.loc[stacked_mask, "Is_Stacked_Distress"] = "Yes"
                    existing_notes = df_cache.loc[stacked_mask, "Distress_Stack_Notes"].iloc[0] or ""
                    new_note = f" | ⚖️ FELONY ARREST: {row['Subject_Case Comments']}"
                    if "FELONY ARREST" not in str(existing_notes):
                        df_cache.loc[stacked_mask, "Distress_Stack_Notes"] = str(existing_notes) + new_note
                    stacked_count += 1
                else:
                    new_count += 1

            # Append the new unique legal distress leads
            # Drop any duplicates within the new leads by Parcel_ID
            df_new_unique = df_new_legal[~df_new_legal["Parcel_ID"].astype(str).isin(existing_pids)].drop_duplicates(subset=["Parcel_ID"])
            df_combined = pd.concat([df_new_unique, df_cache], ignore_index=True)
            for col in df_combined.columns:
                if df_combined[col].dtype == 'object':
                    df_combined[col] = df_combined[col].fillna('').astype(str)
            df_combined.to_parquet(CACHE_PATH, index=False)
            print(f"Successfully merged into cache: {len(df_new_unique)} brand new leads, {stacked_count} stacked existing leads updated.")
        except Exception as e:
            print(f"Error merging with cache: {e}")
            # If concat had an issue, re-run full cache rebuild to guarantee cache integrity
            try:
                from src.rebuild_orange_leads_cache import build_full_orange_cache as rebuild_orange_cache
                rebuild_orange_cache()
            except Exception as re_err:
                print(f"Rebuild cache failed: {re_err}")
    else:
        df_new_legal.to_parquet(CACHE_PATH, index=False)

    return {
        "status": "success",
        "report_date": report_date,
        "total_arrestees": len(records),
        "felony_arrestees": len(felonies),
        "matched_properties": len(matched_rows),
        "new_leads_added": new_count,
        "stacked_leads_updated": stacked_count,
        "csv_path": CSV_OUTPUT_PATH
    }

if __name__ == "__main__":
    result = sync_orange_county_jail_leads(force_download=False)
    print("\nSYNC RESULT:", result)
