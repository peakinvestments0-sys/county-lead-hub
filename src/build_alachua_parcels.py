"""
Build Alachua County Master Parcels
Combines:
1. Alachua Property Appraiser Public Parcels (ArcGIS FeatureServer) for site address & city
2. ACPA_CAMAData.zip (Owners.txt, HistoryRE.txt, Improvements.txt, Legals.txt)
   for owner names, mailing addresses, market values, and sqft.

Outputs standardized data/FL/alachua/RP_PROPERTY_INFO.parquet
"""

import os
import sys
import io
import zipfile
import json
import urllib.request
import urllib.parse
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALACHUA_DIR = os.path.join(BASE_DIR, "data", "FL", "alachua")
ZIP_PATH = os.path.join(ALACHUA_DIR, "ACPA_CAMAData.zip")
OUT_PARQUET = os.path.join(ALACHUA_DIR, "RP_PROPERTY_INFO.parquet")

PUBLIC_PARCEL_URL = "https://services.arcgis.com/cNo3jpluyt69V8Ek/arcgis/rest/services/PublicParcel/FeatureServer/0/query"

def fetch_alachua_address_map():
    """Fetch parcel addresses from Alachua PublicParcel FeatureServer."""
    print("[Alachua Master] Fetching parcel address map from ArcGIS...")
    headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}
    all_features = []
    offset = 0
    batch_size = 2000

    while True:
        params = {
            "where": "1=1",
            "outFields": "Name,Prop_ID,FULLADDR,INC_MUNI,POST_CODE",
            "returnGeometry": "false",
            "resultOffset": offset,
            "resultRecordCount": batch_size,
            "f": "json"
        }
        url = f"{PUBLIC_PARCEL_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
                features = data.get("features", [])
                if not features:
                    break
                all_features.extend([f.get("attributes", {}) for f in features])
                if len(features) < batch_size:
                    break
                offset += batch_size
                if offset % 20000 == 0:
                    print(f"[Alachua Master] Fetched {len(all_features):,} address records...")
        except Exception as e:
            print(f"[Alachua Master] Error at offset {offset}: {e}")
            break

    print(f"[Alachua Master] Total addresses fetched: {len(all_features):,}")
    df_addr = pd.DataFrame(all_features)
    if not df_addr.empty:
        df_addr = df_addr.rename(columns={
            "Name": "PARCEL_NUMBER",
            "Prop_ID": "PROP_ID",
            "FULLADDR": "SITE_ADDRESS",
            "INC_MUNI": "SITE_CITY",
            "POST_CODE": "SITE_ZIP"
        })
        df_addr["PARCEL_NUMBER"] = df_addr["PARCEL_NUMBER"].astype(str).str.strip()
        df_addr = df_addr.drop_duplicates(subset=["PARCEL_NUMBER"])
    return df_addr

def build_alachua_master():
    """Build unified RP_PROPERTY_INFO.parquet for Alachua County."""
    if not os.path.exists(ZIP_PATH):
        print(f"Error: {ZIP_PATH} not found.")
        return

    print(f"[Alachua Master] Reading CAMA tables from {ZIP_PATH}...")
    z = zipfile.ZipFile(ZIP_PATH)

    # 1. Owners
    print("- Reading Owners.txt...")
    df_owners = pd.read_csv(io.BytesIO(z.read("Owners.txt")), sep="\t", dtype=str, on_bad_lines="skip", encoding="latin1")
    df_owners = df_owners.rename(columns={
        "Parcel": "PARCEL_NUMBER",
        "Owner_Mail_Name": "OWNER1",
        "Owner_Mail_Addr1": "MAILING_ADDRESS_1",
        "Owner_Mail_City": "MAILING_CITY",
        "Owner_Mail_State": "MAILING_STATE",
        "Owner_Mail_Zip": "MAILING_ZIP"
    })
    df_owners["PARCEL_NUMBER"] = df_owners["PARCEL_NUMBER"].astype(str).str.strip()
    df_owners = df_owners.drop_duplicates(subset=["PARCEL_NUMBER"])

    # 2. HistoryRE (values & property use)
    print("- Reading HistoryRE.txt...")
    df_hist = pd.read_csv(io.BytesIO(z.read("HistoryRE.txt")), sep="\t", dtype=str, on_bad_lines="skip", encoding="latin1")
    # Keep latest tax year for each parcel
    df_hist["Hist_Tax_Year"] = pd.to_numeric(df_hist["Hist_Tax_Year"], errors="coerce").fillna(0)
    df_hist = df_hist.sort_values(by="Hist_Tax_Year").groupby("Parcel").last().reset_index()
    df_hist = df_hist.rename(columns={
        "Parcel": "PARCEL_NUMBER",
        "Prop_Use_Desc": "PROPERTY_USE",
        "Just_Value": "CNTY_JST_VALUE",
        "County_Assessed_Value": "CNTY_ASD_VALUE",
        "County_Taxable_Value": "CNTY_TAXABLE_VALUE",
        "Heated_SquareFeet": "TOTAL_LIVING_SQFT"
    })
    df_hist["PARCEL_NUMBER"] = df_hist["PARCEL_NUMBER"].astype(str).str.strip()

    # 3. Improvements (Year Built)
    print("- Reading Improvements.txt...")
    df_imp = pd.read_csv(io.BytesIO(z.read("Improvements.txt")), sep="\t", dtype=str, on_bad_lines="skip", encoding="latin1")
    df_imp = df_imp.sort_values(by="Actual_YrBlt", ascending=False).groupby("Parcel").first().reset_index()
    df_imp = df_imp.rename(columns={
        "Parcel": "PARCEL_NUMBER",
        "Actual_YrBlt": "YEAR_BUILT"
    })
    df_imp["PARCEL_NUMBER"] = df_imp["PARCEL_NUMBER"].astype(str).str.strip()

    # 4. Legals
    print("- Reading Legals.txt...")
    df_legals = pd.read_csv(io.BytesIO(z.read("Legals.txt")), sep="\t", dtype=str, on_bad_lines="skip", encoding="latin1")
    df_legals = df_legals.groupby("Parcel").first().reset_index().rename(columns={
        "Parcel": "PARCEL_NUMBER",
        "Legal_Desc": "LEGAL"
    })
    df_legals["PARCEL_NUMBER"] = df_legals["PARCEL_NUMBER"].astype(str).str.strip()

    # 5. Addresses from ArcGIS
    df_addr = fetch_alachua_address_map()

    # 6. Merge all
    print("[Alachua Master] Merging datasets...")
    base = df_owners[["PARCEL_NUMBER", "OWNER1", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP"]].copy()

    if not df_addr.empty:
        base = base.merge(df_addr[["PARCEL_NUMBER", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP"]], on="PARCEL_NUMBER", how="left")
    else:
        base["SITE_ADDRESS"] = ""
        base["SITE_CITY"] = "Gainesville"
        base["SITE_ZIP"] = ""

    base = base.merge(df_hist[["PARCEL_NUMBER", "PROPERTY_USE", "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE", "TOTAL_LIVING_SQFT"]], on="PARCEL_NUMBER", how="left")
    base = base.merge(df_imp[["PARCEL_NUMBER", "YEAR_BUILT"]], on="PARCEL_NUMBER", how="left")
    base = base.merge(df_legals[["PARCEL_NUMBER", "LEGAL"]], on="PARCEL_NUMBER", how="left")

    base["STRAP"] = base["PARCEL_NUMBER"]
    base["OWNER2"] = ""

    # Defaults and types
    num_cols = ["CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE", "TOTAL_LIVING_SQFT", "YEAR_BUILT"]
    for c in num_cols:
        base[c] = pd.to_numeric(base[c], errors="coerce").fillna(0.0)

    for c in base.columns:
        if c not in num_cols:
            base[c] = base[c].fillna("").astype(str)

    target_cols = [
        "PARCEL_NUMBER", "STRAP", "SITE_ADDRESS", "SITE_CITY", "SITE_ZIP",
        "OWNER1", "OWNER2", "MAILING_ADDRESS_1", "MAILING_CITY", "MAILING_STATE", "MAILING_ZIP",
        "LEGAL", "PROPERTY_USE", "TOTAL_LIVING_SQFT", "YEAR_BUILT",
        "CNTY_JST_VALUE", "CNTY_ASD_VALUE", "CNTY_TAXABLE_VALUE"
    ]
    base = base[target_cols]

    base.to_parquet(OUT_PARQUET, index=False)
    print(f"🎉 Successfully built {len(base):,} Alachua master parcels to {OUT_PARQUET}!")
    return len(base)

if __name__ == "__main__":
    build_alachua_master()
