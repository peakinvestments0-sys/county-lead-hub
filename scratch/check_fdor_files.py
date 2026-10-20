import urllib.request
import re

url = "https://floridarevenue.com/property/dataportal/Pages/default.aspx?path=/property/dataportal/Documents/PTO%20Data%20Portal/Tax%20Roll%20Data%20Files"
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
    links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', html, re.I)
    print("Fetched! Total links:", len(links))
    for l in links[:20]:
        if 'tax roll' in l.lower() or 'nal' in l.lower() or 'documents' in l.lower():
            print("  ->", l)
except Exception as e:
    print("Error:", e)
