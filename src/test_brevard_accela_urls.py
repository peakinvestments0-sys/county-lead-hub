import urllib.request

headers = {'User-Agent': 'Mozilla/5.0'}

urls = [
    "https://aca-prod.accela.com/brevard/Default.aspx",
    "https://aca-prod.accela.com/brevardco/Default.aspx",
    "https://aca-prod.accela.com/palmbay/Default.aspx",
    "https://aca-prod.accela.com/melbourne/Default.aspx",
    "https://aca-prod.accela.com/cocoa/Default.aspx",
    "https://aca-prod.accela.com/titusville/Default.aspx"
]

for u in urls:
    try:
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as r:
            print(f"URL: {u} -> Status {r.status}")
    except Exception as e:
        print(f"URL: {u} -> Error: {e}")
