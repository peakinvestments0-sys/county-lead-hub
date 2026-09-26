import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Pinellas directory located inside data/pinellas
PINELLAS_DIR = os.path.join(DATA_DIR, "pinellas")
if not os.path.exists(PINELLAS_DIR) and os.path.exists(os.path.join(BASE_DIR, "pinellas")):
    PINELLAS_DIR = os.path.join(BASE_DIR, "pinellas")


DEFAULT_MASTER_CSV = os.path.join(PINELLAS_DIR, "RP_PROPERTY_INFO.csv")
DEFAULT_MASTER_PARQUET = os.path.join(PINELLAS_DIR, "RP_PROPERTY_INFO.parquet")

# Resolve sample LP file
DEFAULT_SAMPLE_LP = os.path.join(PINELLAS_DIR, "pinellas_lis_pendens_20260920.csv")
if not os.path.exists(DEFAULT_SAMPLE_LP):
    alt_lp = os.path.join(PINELLAS_DIR, "lispendens_pinellas92026.csv")
    if os.path.exists(alt_lp):
        DEFAULT_SAMPLE_LP = alt_lp

# Resolve sample Code Violations file
DEFAULT_SAMPLE_CODE = os.path.join(PINELLAS_DIR, "pinellas_code_violations_20260920.csv")
if not os.path.exists(DEFAULT_SAMPLE_CODE):
    alt_code = os.path.join(PINELLAS_DIR, "RecordList20260920.csv")
    if os.path.exists(alt_code):
        DEFAULT_SAMPLE_CODE = alt_code

# County Parcel Columns to load from PCPAO
PCPAO_COLS = [
    'STRAP',
    'PARCEL_NUMBER',
    'PARCEL_TYPE',
    'PROPERTY_USE',
    'SITE_ADDRESS',
    'SITE_CITYZIP',
    'OWNER1',
    'OWNER2',
    'MAILING_ADDRESS_1',
    'MAILING_ADDRESS_2',
    'MAILING_CITY',
    'MAILING_STATE',
    'MAILING_ZIP',
    'LEGAL',
    'TOTAL_LIVING_SQFT',
    'YEAR_BUILT',
    'CNTY_JST_VALUE',
    'CNTY_ASD_VALUE',
    'CNTY_TAXABLE_VALUE',
    'HX_CAP',
    'OR_BOOK_PAGE',
    'STR_NUM',
    'STR_NAME',
    'STR_SFX',
    'STR_CITY',
    'STR_ZIP',
    'LATITUDE',
    'LONGITUDE'
]

# Wholesaling Preset Columns for Export
WHOLESALE_EXPORT_PRESET = [
    # Matched Status
    'Match_Status',
    'Match_Confidence',
    'Match_Method',
    # Primary Owner Info for Marketing / Skip-Tracing
    'Clean_First_Name',
    'Clean_Last_Name',
    'Clean_Full_Name',
    'Owner_Entity_Type',
    'Secondary_Owner',
    # Property Location (Situs)
    'Property_Address',
    'Property_City',
    'Property_Zip',
    'Parcel_ID',
    'Strap',
    # Mailing Location (for Absentee Mailers)
    'Mailing_Address',
    'Mailing_City',
    'Mailing_State',
    'Mailing_Zip',
    'Absentee_Status',
    'Is_Absentee',
    # Property Characteristics & Valuation
    'Homestead_Exemption',
    'Market_Value',
    'Assessed_Value',
    'Taxable_Value',
    'Year_Built',
    'Living_Sqft',
    'Property_Type',
    'Property_Use',
    'Legal_Description'
]
