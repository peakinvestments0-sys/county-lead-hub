import json

with open(r"C:\Projects\Apps\link-zone\data\florida-booking-report-audit.json", "r", encoding="utf-8") as f:
    d = json.load(f)

sources = d.get("sources", [])

# Let's filter primary sources or deduplicate by county (excluding purely RECORDS_REQUEST unless that's all there is)
non_request = [s for s in sources if s.get("Source_Type") != "RECORDS_REQUEST"]
request_only = [s for s in sources if s.get("Source_Type") == "RECORDS_REQUEST"]

print(f"Total non-request primary arrest sources: {len(non_request)}")
print(f"Total request fallback sources: {len(request_only)}\n")

for s in non_request:
    county = s.get("County")
    url = s.get("Direct_Download_URL") or s.get("Report_Portal_URL") or s.get("Booking_Search_URL") or "N/A"
    fmt = s.get("File_Format")
    wf = s.get("Daily_Workflow_Potential")
    captcha = s.get("CAPTCHA_Required")
    auth = s.get("Authentication_Required")
    agency = s.get("Agency_Name")
    src_type = s.get("Source_Type")
    print(f"[{county:<14}] Type: {src_type:<22} | Fmt: {fmt:<8} | WF: {wf:<25} | Captcha: {captcha:<3} | URL: {url}")
