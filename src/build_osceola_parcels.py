"""
Build unified Master Parcel parquet for Osceola County, FL (Kissimmee, St. Cloud, Celebration, Poinciana).
Parses the certified NAL CAMA roll from 2025_CertifiedData_OCPA.zip:
vw_nalf10232025_NoConf.csv
"""

import os
import sys
import io
import zipfile
import pandas as pd

# Reconfigure stdout/stderr to utf-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSCEOLA_DIR = os.path.join(BASE_DIR, "data", "FL", "osceola")
ZIP_PATH = os.path.join(OSCEOLA_DIR, "2025_CertifiedData_OCPA.zip")
OUT_PARQUET = os.path.join(OSCEOLA_DIR, "RP_PROPERTY_INFO.parquet")

def build_osceola_master():
    """Extract and build standardized RP_PROPERTY_INFO.parquet for Osceola County."""
    if not os.path.exists(ZIP_PATH):
        print(f"[Osceola Master] Error: {ZIP_PATH} not found.")
        return 0

    print(f"[Osceola Master] Opening {ZIP_PATH}...")
    with zipfile.ZipFile(ZIP_PATH, 'r') as z:
        target_csv = "2025_CertifiedData_OCPA/vw_nalf10232025_NoConf.csv"
        if target_csv not in z.namelist():
            print(f"[Osceola Master] Error: {target_csv} not found in zip.")
            return 0

        print(f"[Osceola Master] Reading {target_csv} (pipe-delimited)...")
        with z.open(target_csv) as f:
            df = pd.read_csv(f, sep="|", dtype=str, on_bad_lines="skip", encoding="latin1")

    print(f"[Osceola Master] Loaded {len(df):,} raw parcels. Standardizing schema...")

    # Standardize column mappings
    # Strap: Osceola standard parcel number (e.g. '12528502600011217')
    # AltKey: County alternate key
    df["PARCEL_NUMBER"] = df["Strap"].fillna(df.get("AltKey", "")).astype(str).str.strip()
    df["STRAP"] = df.get("AltKey", df["Strap"]).fillna(df["PARCEL_NUMBER"]).astype(str).str.strip()
    df["SITE_ADDRESS"] = df.get("SitusAddr1", "").fillna("").astype(str).str.strip()
    df["SITE_CITY"] = df.get("SitusCity", "Kissimmee").fillna("Kissimmee").astype(str).str.strip()
    df["SITE_ZIP"] = df.get("SitusZip", "").fillna("").astype(str).str.strip()

    df["OWNER1"] = df.get("Name", "").fillna("").astype(str).str.strip()
    df["OWNER2"] = ""
    df["MAILING_ADDRESS_1"] = df.get("MailAddr1", "").fillna("").astype(str).str.strip()
    df["MAILING_CITY"] = df.get("MailCity", "").fillna("").astype(str).str.strip()
    df["MAILING_STATE"] = df.get("MailState", "FL").fillna("FL").astype(str).str.strip()
    df["MAILING_ZIP"] = df.get("MailZip", "").fillna("").astype(str).str.strip()

    df["LEGAL"] = df.get("LegalDscr", "").fillna("").astype(str).str.strip()
    df["PROPERTY_USE"] = df.get("LandUseCode", df.get("DORCode", "Residential")).fillna("Residential").astype(str).str.strip()
    df["TOTAL_LIVING_SQFT"] = pd.to_numeric(df.get("TotLivArea", 0), errors="coerce").fillna(0.0)
    df["YEAR_BUILT"] = pd.to_numeric(df.get("ActYrBlt", 0), errors="coerce").fillna(0.0)

    df["CNTY_JST_VALUE"] = pd.to_numeric(df.get("TotalJust", 0), errors="coerce").fillna(0.0)
    df["CNTY_ASD_VALUE"] = pd.to_numeric(df.get("SchoolAsd", df["CNTY_JST_VALUE"]), errors="coerce").fillna(df["CNTY_JST_VALUE"])
    df["CNTY_TAXABLE_VALUE"] = pd.to_numeric(df.get("SchoolTaxable", df["CNTY_JST_VALUE"]), errors="coerce").fillna(df["CNTY_JST_VALUE"])

    target_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]

    df = df.drop_duplicates(subset=["PARCEL_NUMBER"])
    df = df[target_cols]

    print(f"[Osceola Master] Saving {len(df):,} parcels to {OUT_PARQUET}...")
    df.to_parquet(OUT_PARQUET, index=False)
    print(f"Successfully generated {OUT_PARQUET} ({os.path.getsize(OUT_PARQUET) / (1024*1024):.2f} MB)")
    return len(df)

if __name__ == "__main__":
    build_osceola_master()
