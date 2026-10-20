import urllib.request
import urllib.parse
import json

headers = {"User-Agent": "Mozilla/5.0 FloridaLeadHub/2.0"}

centers = {
    "St. Augustine (St. Johns)": (29.8947, -81.3145),
    "St. Augustine Beach": (29.8436, -81.2720),
    "Ponte Vedra": (30.2397, -81.3856),
    "Hastings": (29.7189, -81.5090),
    "Palm Coast (Flagler)": (29.5845, -81.2079),
    "Flagler Beach": (29.4744, -81.1270),
    "Bunnell": (29.4678, -81.2581),
    "Fernandina Beach (Nassau)": (30.6697, -81.4626),
    "Yulee (Nassau)": (30.6300, -81.5721),
    "Callahan (Nassau)": (30.5611, -81.8318)
}

print("Testing SeeClickFix hubs for Batch 3...")
for name, (lat, lng) in centers.items():
    url = f"https://seeclickfix.com/api/v2/issues?lat={lat}&lng={lng}&zoom=11&per_page=20"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            issues = data.get("issues", [])
            print(f"{name}: {len(issues)} issues found.")
            if issues:
                sample = issues[0]
                print(f"   Sample: #{sample.get('id')} - {sample.get('summary')} | {sample.get('address')}")
    except Exception as e:
        print(f"{name}: error {e}")
