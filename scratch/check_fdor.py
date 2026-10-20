import urllib.request
import re

url = "https://floridarevenue.com/property/Pages/DataPortal_RequestAssessmentRollGISData.aspx"
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
    print("Page fetched! Length:", len(html))
    links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', html, re.I)
    interesting = [l for l in links if any(k in l.lower() for k in ['nal', 'gis', 'data', 'download', 'zip', 'ftp'])]
    for i in interesting[:15]:
        print("  ->", i)
except Exception as e:
    print("Error:", e)
