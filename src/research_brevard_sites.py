import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0'}

urls = [
    "https://www.palmbayflorida.org/government/city-departments/growth-management/code-compliance",
    "https://www.palmbayflorida.org/government/city-departments/information-technology/geographic-information-systems-gis",
    "https://www.melbourneflorida.org/departments/community-development/code-compliance",
    "https://www.bcpao.us/downloads/",
    "https://www.bcpao.us/DataFiles.aspx"
]

for u in urls:
    try:
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            print(f"URL: {u} -> Status {r.status}")
            html = r.read().decode('utf-8', errors='ignore')
            # Look for arcgis or map or api links
            arc_links = re.findall(r'https?://[^\s\'"<>]+(?:arcgis|rest|services|mapserver|featureserver|opendata|seeclickfix)[^\s\'"<>]*', html, re.I)
            if arc_links:
                print(f"  Found GIS links on {u}:")
                for al in set(arc_links)[:5]:
                    print(f"    - {al}")
    except Exception as e:
        print(f"URL: {u} -> Error: {e}")
