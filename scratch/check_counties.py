import os
import json

lz_path = r"C:\Projects\Apps\link-zone\data\florida.json"
fb_path = r".\data\sources_catalog\florida.json"
path_to_use = lz_path if os.path.exists(lz_path) else fb_path

with open(path_to_use, "r", encoding="utf-8") as f:
    counties_data = json.load(f)

print(f"Total counties in Florida Link Zone: {len(counties_data)}\n")

existing_dirs = os.listdir(r".\data\FL") if os.path.exists(r".\data\FL") else []

summary_list = []

for c in counties_data:
    name = c.get("county")
    sources = c.get("sources", [])
    
    # Identify sources
    cama_sources = [s for s in sources if any(k in s.get("notes", "").lower() or k in s.get("url", "").lower() for k in ["cama", "parcel", "property appraiser", "gis", "roll"]) or s.get("format") in ["ZIP", "CSV"]]
    clerk_lp = [s for s in sources if any(k in s.get("notes", "").lower() or k in s.get("url", "").lower() for k in ["lis pendens", "official records", "foreclosure", "clerk"])]
    probate = [s for s in sources if any(k in s.get("notes", "").lower() or k in s.get("url", "").lower() for k in ["probate", "court", "cp "])]
    code = [s for s in sources if any(k in s.get("notes", "").lower() or k in s.get("url", "").lower() for k in ["code", "violation", "enforcement"])]
    tax = [s for s in sources if any(k in s.get("notes", "").lower() or k in s.get("url", "").lower() for k in ["tax", "delinquent", "tax collector"])]

    # Check local files
    has_local_master = False
    local_files = []
    for ed in existing_dirs:
        if ed.lower() == name.lower():
            target_p = os.path.join(r".\data\FL", ed)
            local_files = os.listdir(target_p)
            has_local_master = any("rp_property_info" in f.lower() or "master" in f.lower() for f in local_files)
            break

    # Determine best CAMA download URL
    best_cama = None
    for s in cama_sources:
        if s.get("access") == "DIRECT_DOWNLOAD":
            best_cama = s
            break
    if not best_cama and cama_sources:
        best_cama = cama_sources[0]

    summary_list.append({
        "name": name,
        "has_local_master": has_local_master,
        "local_files": local_files,
        "cama": best_cama,
        "clerk_lp": clerk_lp[0] if clerk_lp else None,
        "probate": probate[0] if probate else None,
        "code": code[0] if code else None,
        "tax": tax[0] if tax else None,
        "total_sources": len(sources)
    })

print(f"{'County':<15} | {'Master Status':<15} | {'CAMA Download Type':<20} | {'CAMA URL'}")
print("-" * 110)
for s in summary_list:
    cama_type = s['cama'].get('access', 'UNKNOWN') if s['cama'] else 'NONE'
    cama_url = (s['cama'].get('url', '') if s['cama'] else '')[:55]
    status_str = "ACTIVE (Ready)" if s['has_local_master'] else "NEEDS PARCEL"
    print(f"{s['name']:<15} | {status_str:<15} | {cama_type:<20} | {cama_url}")

# Let's also check which ones have DIRECT_DOWNLOAD for CAMA
direct_cama = [s for s in summary_list if s['cama'] and s['cama'].get('access') == 'DIRECT_DOWNLOAD']
print(f"\nCounties with DIRECT_DOWNLOAD CAMA in Link Zone: {len(direct_cama)}")
for dc in direct_cama:
    print(f"  - {dc['name']}: {dc['cama']['url']}")
