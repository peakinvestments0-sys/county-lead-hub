import urllib.request
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

services = [
    "Sand_Erosion_Hurricane_Matthew",
    "PUD_Development_Activity",
    "STR_Properties"
]

for s in services:
    url = f"https://services1.arcgis.com/t2yugAJW83eUIFui/arcgis/rest/services/{s}/FeatureServer/0/query?where=1=1&returnCountOnly=true&f=json"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"{s}: {r.read().decode()}")
    except Exception as e:
        print(f"{s} error: {e}")
