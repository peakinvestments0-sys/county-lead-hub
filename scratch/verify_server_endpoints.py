import urllib.request
import json

stats = json.loads(urllib.request.urlopen('http://127.0.0.1:8505/api/stats').read())
counties = json.loads(urllib.request.urlopen('http://127.0.0.1:8505/api/counties').read())

print("=== GLOBAL STATS ===")
print("Total Records Indexed:", stats.get("total_records"))
print("Counties Status:", stats.get("counties_available"))

print("\n=== TOP COUNTIES IN APP ===")
for c in counties[:12]:
    name = c.get('name')
    st = c.get('status')
    hm = c.get('has_master')
    recs = c.get('records_formatted', c.get('records'))
    print(f"{name:<14} | Status: {st:<15} | Master: {str(hm):<5} | {recs}")
