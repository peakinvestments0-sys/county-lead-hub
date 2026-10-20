import urllib.request
import json

endpoints = [
    '/api/stats',
    '/api/leads?county=Hernando',
    '/api/leads?county=Citrus',
    '/api/leads?county=Sumter'
]

for ep in endpoints:
    url = 'http://localhost:8505' + ep
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            if 'total' in data or 'total_records_in_db' in data:
                tot = data.get('total') or data.get('total_records_in_db')
                print(f"{ep} -> total: {tot}, records_returned: {len(data.get('records', []))}, kpis: {data.get('kpis')}")
            elif 'counties_available' in data:
                print(f"{ep} -> Available: {data.get('counties_available')}, Parcels: {data.get('total_records')}, Leads: {data.get('unique_properties')}")
            else:
                print(f"{ep} -> {data.keys()}")
    except Exception as e:
        print(f"{ep} -> Error: {e}")
