import urllib.request
import urllib.parse
import json
import time

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

centers = {
    "Inverness (Citrus)": (28.8358, -82.3304),
    "Crystal River (Citrus)": (28.9008, -82.5926),
    "Homosassa (Citrus)": (28.7830, -82.6079),
    "Brooksville (Hernando)": (28.5553, -82.3879),
    "Spring Hill (Hernando)": (28.4764, -82.5254),
    "Weeki Wachee (Hernando)": (28.5164, -82.5768),
    "The Villages (Sumter)": (28.9264, -81.9723),
    "Wildwood (Sumter)": (28.8639, -82.0390),
    "Bushnell (Sumter)": (28.6653, -82.1129)
}

print("Testing SeeClickFix hubs for Batch 4 (Citrus, Hernando, Sumter)...")
for name, (lat, lng) in centers.items():
    time.sleep(0.8)
    url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=20"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            issues = data.get("issues", [])
            print(f"[{name}]: {len(issues)} issues found.")
            if issues:
                sample = issues[0]
                print(f"   Sample: #{sample.get('id')} - {sample.get('summary')} | {sample.get('address')}")
    except Exception as e:
        print(f"[{name}] error: {e}")
