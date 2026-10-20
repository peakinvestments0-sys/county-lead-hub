import urllib.request
import re

url = "https://www.leepa.org/Roll/TaxRoll.aspx"
headers = {'User-Agent': 'Mozilla/5.0'}

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode('utf-8', errors='ignore')
        
    links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', html)
    print("Links on TaxRoll.aspx:")
    for l in links:
        print(" ", l)
        
    zips = re.findall(r'[\w\-./%]+\.(?:zip|csv|txt)', html, re.I)
    print("Files found:", set(zips))
except Exception as e:
    print("Error:", e)
