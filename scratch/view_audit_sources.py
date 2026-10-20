import json

with open(r"C:\Projects\Apps\link-zone\data\florida-booking-report-audit.json", "r", encoding="utf-8") as f:
    d = json.load(f)

sources = d.get("sources", [])
print(f"Total sources found by Codex: {len(sources)}\n")

for s in sources:
    county = s.get("County", "Unknown")
    name = s.get("Source_Name", "")
    fmt = s.get("Format", "")
    url = s.get("URL", "")
    access = s.get("Access_Type", "")
    is_down = s.get("Is_Downloadable_Named_Report", "NO")
    print(f"[{county:<14}] ({fmt:<6}) [{access:<15}] DownloadableNamed={is_down:<3} | {name:<35} -> {url}")
