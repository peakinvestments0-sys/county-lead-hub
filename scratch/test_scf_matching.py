import sys, os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
import urllib.request
import json
import pandas as pd
from src.normalizer import clean_display_address
from src.matcher import CrossReferenceEngine

# Fetch 2 pages (200 records) of bounding box issues
all_issues = []
for page in [1, 2]:
    url = f"https://seeclickfix.com/api/v2/issues?min_lat=27.65&max_lat=28.17&min_lng=-82.88&max_lng=-82.55&per_page=100&page={page}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            all_issues.extend(data.get('issues', []))
    except Exception as e:
        print(f"Error fetching page {page}: {e}")

print(f"Fetched {len(all_issues)} total issues.")

neglect_rows = []
for i in all_issues:
    text = f"{i.get('summary', '')} {i.get('description', '')} {i.get('request_type', {}).get('title', '')}".lower()
    addr = i.get('address', '')
    if any(k in text for k in ['trash', 'dump', 'grass', 'weed', 'board', 'overgrown', 'debris', 'derelict', 'fence', 'roof', 'damage', 'tree', 'abandon', 'code', 'neglect', 'unfit', 'blight', 'clean']):
        # Clean address: remove city, state, zip suffix if present
        # e.g., '2636 37th Ave N St Petersburg, FL, 33713, USA' -> extract street
        neglect_rows.append({
            'Issue_ID': i.get('id'),
            'Raw_Address': addr,
            'Case Address': addr,
            'Summary': i.get('summary'),
            'Description': (i.get('description') or '')[:200],
            'Status': i.get('status'),
            'Created_At': i.get('created_at'),
            'Lat': i.get('lat'),
            'Lng': i.get('lng'),
            'Source': 'Pinellas_SeeClickFix_Live_API'
        })

print(f"Neglect/Distress candidates: {len(neglect_rows)}")
neglect_df = pd.DataFrame(neglect_rows)
print(neglect_df[['Raw_Address', 'Summary']].head(10))
