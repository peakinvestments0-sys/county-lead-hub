import os
import json

lz_path = r"C:\Projects\Apps\link-zone\data\florida.json"
with open(lz_path, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"{'County':<15} | {'Property Appraiser Download URL':<60}")
print("-" * 80)
for c in data:
    name = c['county']
    pa_downloads = [s for s in c.get('sources', []) if 'property appraiser' in s.get('notes', '').lower() and ('download' in s.get('notes', '').lower() or 'cama' in s.get('notes', '').lower() or s.get('access') in ['DIRECT_DOWNLOAD', 'DOWNLOAD_PAGE'])]
    if not pa_downloads:
        pa_downloads = [s for s in c.get('sources', []) if s.get('format') in ['ZIP', 'CSV', 'ZIP / text', 'ZIP / CSV']]
    
    url = pa_downloads[0].get('url') if pa_downloads else 'None'
    notes = pa_downloads[0].get('notes', '')[:40] if pa_downloads else ''
    print(f"{name:<15} | {url:<60}")
