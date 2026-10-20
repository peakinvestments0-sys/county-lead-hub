import json

with open("src/county_portals.json", "r", encoding="utf-8") as f:
    portals = json.load(f)["FL"]

for name in sorted(portals.keys()):
    p = portals[name]
    print(f"### {name} County")
    print(f"- **Master Parcel Download**: [{p.get('master_parcel_download_url', 'N/A')}]({p.get('master_parcel_download_url', '')}) ({p.get('master_parcel_access', 'N/A')})")
    print(f"- **Lis Pendens Portal**: [{p.get('clerk_lis_pendens_url', 'N/A')}]({p.get('clerk_lis_pendens_url', '')})")
    print(f"- **Probate Portal**: [{p.get('clerk_probate_url', 'N/A')}]({p.get('clerk_probate_url', '')})")
    print(f"- **Code Enforcement**: [{p.get('code_enforcement_url', 'N/A')}]({p.get('code_enforcement_url', '')})")
    print(f"- **Tax Liens**: [{p.get('tax_liens_url', 'N/A')}]({p.get('tax_liens_url', '')})\n")
