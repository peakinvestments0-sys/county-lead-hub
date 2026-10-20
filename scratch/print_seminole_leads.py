import pandas as pd

df = pd.read_parquet("data/FL/Seminole/matched_leads_cache.parquet")
print(f"Total Leads: {len(df)}")
print(f"Total Unique Properties: {df['Parcel_ID'].nunique()}")
print(f"Average Market Value: ${df['Market_Value'].mean():,.0f}")
print(f"Absentee Owners: {(df['Is_Absentee'] == 'Yes').sum()}\n")

print(f"{'Owner Name':<22} | {'Address':<32} | {'City':<14} | {'Market Val':<11} | {'Case / Charge'}")
print("-" * 110)
for _, r in df.head(10).iterrows():
    name = str(r['Clean_Full_Name'])[:22]
    addr = str(r['Property_Address'])[:32]
    city = str(r['Property_City'])[:14]
    val = f"${r['Market_Value']:,.0f}"
    case = str(r.get('Subject_Case Comments', r.get('Case_Number', '')))[:45]
    print(f"{name:<22} | {addr:<32} | {city:<14} | {val:<11} | {case}")
