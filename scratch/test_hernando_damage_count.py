import urllib.request
import urllib.parse
import json

p = {
    'where': "Degree_of IN ('Destroyed', 'Major', 'Minor', 'Affected')",
    'returnCountOnly': 'true',
    'f': 'json'
}
url = f"https://services2.arcgis.com/x5zvhhxfUuRDntRe/arcgis/rest/services/2024_HurricanesMiltonAndHeleneDamageAssessementData/FeatureServer/0/query?{urllib.parse.urlencode(p)}"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 FloridaLeadHub/2.0'})
with urllib.request.urlopen(req) as r:
    print("Hernando damaged structures:", r.read().decode())
