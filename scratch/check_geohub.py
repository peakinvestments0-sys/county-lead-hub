import urllib.request
import json

url = 'https://geohub-stpete.opendata.arcgis.com/api/v3/datasets'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
        items = data.get('data', [])
        print(f"Total datasets in GeoHub St Pete: {len(items)}")
        for d in items:
            attrs = d.get('attributes', {})
            name = attrs.get('name', '')
            record_count = attrs.get('recordCount')
            url = attrs.get('url', '')
            # Filter for interesting ones: code, permit, building, parcel, property, tax, lien, violation, demolish, etc.
            lower_name = name.lower()
            if any(k in lower_name for k in ['code', 'violation', 'permit', 'parcel', 'property', 'demol', 'historic', 'address', 'case', 'board', 'unsafe']):
                print(f"- {name} (records: {record_count}) -> {url}")
except Exception as e:
    print(f"Error: {e}")
