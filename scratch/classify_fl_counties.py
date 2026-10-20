import json

with open("src/county_portals.json", "r", encoding="utf-8") as f:
    portals = json.load(f)

fl = portals.get("FL", {})
print(f"Total FL counties in county_portals.json: {len(fl)}\n")

direct_parcels = []
download_page_parcels = []
other_parcels = []

for c_name, c_data in fl.items():
    mp_url = c_data.get("master_parcel_download_url", "")
    mp_access = c_data.get("master_parcel_access", "")
    mp_format = c_data.get("master_parcel_format", "")
    entry = {
        "county": c_name,
        "master_url": mp_url,
        "access": mp_access,
        "format": mp_format,
        "clerk_lp": c_data.get("clerk_lis_pendens_url", ""),
        "code": c_data.get("code_enforcement_url", ""),
        "probate": c_data.get("clerk_probate_url", ""),
        "tax": c_data.get("tax_liens_url", "")
    }
    if mp_access == "DIRECT_DOWNLOAD":
        direct_parcels.append(entry)
    elif mp_access == "DOWNLOAD_PAGE" or "download" in mp_url.lower():
        download_page_parcels.append(entry)
    else:
        other_parcels.append(entry)

print("=== TIER 1: DIRECT DOWNLOAD PARCEL ROLLS (Agent can download & build now) ===")
for p in direct_parcels:
    print(f"- {p['county']:<14} | Format: {p['format']:<12} | URL: {p['master_url']}")

print("\n=== TIER 2: DOWNLOAD PAGE / FTP (Agent or Operator can fetch files) ===")
for p in download_page_parcels:
    print(f"- {p['county']:<14} | Format: {p['format']:<12} | URL: {p['master_url']}")

print("\n=== TIER 3: PORTAL / FDOR REQUEST ===")
for p in other_parcels:
    print(f"- {p['county']:<14} | Format: {p['format']:<12} | URL: {p['master_url'][:60]}")
