import os
import json

lz_path = r"C:\Projects\Apps\link-zone\data\florida.json"
with open(lz_path, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total counties in Florida catalog: {len(data)}\n")

for c in data:
    name = c['county']
    sources = c.get('sources', [])
    print(f"=== {name} ({len(sources)} sources) ===")
    for s in sources:
        acc = s.get('access', 'PORTAL')
        notes = s.get('notes', '')
        url = s.get('url', '')
        fmt = s.get('format', '')
        print(f"  [{acc}] ({fmt}) {notes[:60]} -> {url}")
