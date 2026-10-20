import urllib.request
import re

headers = {'User-Agent': 'Mozilla/5.0'}
url = "https://aca-prod.accela.com/brevard/Default.aspx"

try:
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as r:
        html = r.read().decode('utf-8', errors='ignore')
        print("Page title or snippet:")
        m = re.search(r'<title>(.*?)</title>', html, re.I)
        if m:
            print("  Title:", m.group(1))
        
        # Look for modules / tabs
        tabs = re.findall(r'href=[\'"]([^\'"]*TabName=[^\'"]*)[\'"]', html, re.I)
        print("Tabs found:")
        for t in set(tabs):
            print("  -", t)
            
        links = re.findall(r'href=[\'"]([^\'"]*Cap[^\'"]*)[\'"]', html, re.I)
        print("Cap links:")
        for cl in list(set(links))[:10]:
            print("  -", cl)
except Exception as e:
    print("Error:", e)
