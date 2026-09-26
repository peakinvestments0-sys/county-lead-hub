# County Records Engine - Public Records & Real Estate Acquisitions Platform

A high-performance real estate acquisitions platform built for multi-state investors (Florida, Texas, and expanding). It cross-references master property appraiser databases across counties against raw distressed lead files (Lis Pendens, Code Violations, Tax Delinquent, Probate, Pre-Foreclosure).

---

## Supported Florida Counties

All county parcel databases and data files are unified inside the `data/` directory:

| County | Directory | Master Parcel File | Live Status |
| :--- | :--- | :--- | :---: |
| **Pinellas** | `data/pinellas/` | `RP_PROPERTY_INFO.parquet` | ✅ Installed (~437,500 parcels) |
| **Orange** | `data/orange/` | `RP_PROPERTY_INFO.parquet` | ✅ Installed (~496,700 parcels) |
| **Hillsborough** | `data/hillsborough/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |
| **Pasco** | `data/pasco/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |
| **Manatee** | `data/manatee/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |
| **Polk** | `data/polk/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |
| **Sarasota** | `data/sarasota/` | `RP_PROPERTY_INFO.parquet` | Ready for Download |

---

## Key Features

1. **High-Speed FastAPI Backend & Modern Glass UI**:
   - High-throughput asynchronous backend (`server.py`).
   - Clean, modern, responsive interface (`frontend/index.html` + `frontend/app.js`).
   - Dynamic real-time search, category distress filtering, and CSV export.

2. **Automated Human Defendant & Entity Filtering**:
   - Automatically detects bundled Clerk Lis Pendens filings.
   - Filters out institutional corporate entities (HOAs, Condo Associations, Banks, LLCs, Trusts).
   - Eliminates standard foreclosure placeholders (`JOHN DOE`, `UNKNOWN HEIRS`).
   - Isolates actual individual homeowners and heirs for wholesaling outreach.

3. **Multi-Tier Matching Engine**:
   - **Tier 1**: Exact Parcel ID / Strap number lookup.
   - **Tier 2**: Normalized Physical Street Address.
   - **Tier 3**: Exact Normalized Owner Name (`LAST FIRST` or `FIRST LAST`).
   - **Tier 4**: Legal Description Lot / Block / Unit / Subdivision matching.
   - **Tier 5**: Fuzzy Owner Name matching (via RapidFuzz).

4. **Multi-Channel $0.00 Outreach Suite**:
   - **📱 Android SMS Gateway**: Sends cellular SMS cash offers directly through your phone line for free.
   - **✉️ SMTP2GO Email Gateway**: Sends responsive HTML offer letters via `mail.smtp2go.com` (Port 2525) from `john@407flips.com`.
   - **🔄 Chrome Extension Helper**: 1-click TruePeopleSearch scraper pulling both phone numbers and emails straight into your leads table.

---

## How to Run

### Option 1: Batch Script (Recommended)
Double-click **`run_hub.bat`** to start Florida Lead Hub at `http://localhost:8505`.  
To stop the server, double-click **`stop_hub.bat`**.

### Option 2: Command Line (PowerShell)
```bash
python server.py
```
The application runs on `http://localhost:8505`.
