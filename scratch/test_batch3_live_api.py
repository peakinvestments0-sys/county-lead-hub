import urllib.request
import json

for c in ['St.+Johns', 'Nassau', 'Flagler']:
    u = f'http://localhost:8505/api/leads?county={c}'
    with urllib.request.urlopen(u) as r:
        d = json.loads(r.read().decode())
        print(f"{c}: total={d.get('total_records_in_db')}, records_returned={len(d.get('records', []))}, kpis={d.get('kpis')}")
