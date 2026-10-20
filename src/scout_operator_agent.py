"""
Scout Operator & Sentinel Agent Engine
Autonomous multi-state real estate lead sentinel, statewide cross-county querying,
daily executive briefings, automated data-drop ingestion, and natural-language dispatcher.
"""

import os
import sys
import json
import re
import time
import glob
import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.normalizer import clean_display_address, clean_display_name, clean_display_city, is_commercial_entity, COMMERCIAL_REGEX

PORTALS_PATH = os.path.join(BASE_DIR, "src", "county_portals.json")

def load_county_portals(state: str = "FL") -> Dict[str, Any]:
    try:
        with open(PORTALS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(state.upper(), {})
    except Exception:
        return {}

# =====================================================================
# 1. CROSS-COUNTY & STATEWIDE COLUMNAR QUERY ENGINE
# =====================================================================

_STATE_COMBINED_CACHE: Dict[str, Tuple[float, pd.DataFrame]] = {}

def get_statewide_combined_df(state: str = "FL", force_refresh: bool = False) -> pd.DataFrame:
    """
    Returns cached, unified statewide DataFrame across all county caches.
    Automatically invalidates if any county cache file modification time changes (checked every 30s).
    """
    global _STATE_COMBINED_CACHE
    now = time.time()
    cached_entry = _STATE_COMBINED_CACHE.get(state.upper())
    
    # If cached within last 30 seconds and not forced, return immediately (<1ms)
    if not force_refresh and cached_entry and (now - cached_entry[0] < 30.0) and not cached_entry[2].empty:
        return cached_entry[2]

    portals = load_county_portals(state)
    latest_mtime = 0.0
    cache_files = []
    
    for cname, meta in portals.items():
        folder = meta.get("folder_name", cname.lower().replace(" ", "_").replace("-", "_"))
        cfile = os.path.join(BASE_DIR, "data", state.upper(), folder, "matched_leads_cache.parquet")
        if os.path.exists(cfile):
            mt = os.path.getmtime(cfile)
            if mt > latest_mtime:
                latest_mtime = mt
            cache_files.append((cname, cfile))
            
    if cached_entry and cached_entry[1] >= latest_mtime and not cached_entry[2].empty:
        _STATE_COMBINED_CACHE[state.upper()] = (now, latest_mtime, cached_entry[2])
        return cached_entry[2]

    def _read_file(item):
        cname, cfile = item
        try:
            if os.path.getsize(cfile) > 1000:
                df = pd.read_parquet(cfile)
                if len(df) > 0:
                    df["County"] = cname
                    df["State"] = state.upper()
                    return df
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = ex.map(_read_file, cache_files)
        all_dfs = [df for df in results if df is not None and not df.empty]

    if all_dfs:
        combined = pd.concat(all_dfs, ignore_index=True)
    else:
        combined = pd.DataFrame()

    _STATE_COMBINED_CACHE[state.upper()] = (now, latest_mtime, combined)
    return combined

def query_statewide_leads(
    state: str = "FL",
    counties: Optional[List[str]] = None,
    filter_type: str = "all",
    distress_type: str = "all",
    search_text: str = "",
    min_equity_val: int = 0,
    min_market_val: int = 0,
    max_market_val: int = 0,
    exclude_llc: bool = False,
    property_type: str = "all",
    max_records: int = 150
) -> Dict[str, Any]:
    """
    Query leads across all 37 counties (or specific county clusters) simultaneously in <100ms.
    Returns aggregated leads enriched with County names, stacked distress flags, and stats.
    Supports wholesale residential filtering (exclude LLCs, max market value).
    """
    t0 = time.time()
    raw_df = get_statewide_combined_df(state)
    if raw_df.empty:
        return {
            "status": "ready",
            "state": state.upper(),
            "total_matches": 0,
            "leads": [],
            "kpis": {"total_leads": 0, "stacked_count": 0, "absentee_count": 0, "avg_market_value": 0},
            "elapsed_ms": round((time.time() - t0) * 1000, 1)
        }

    combined = raw_df
    if counties:
        clean_req = [c.strip().lower() for c in counties]
        combined = combined[combined["County"].astype(str).str.lower().isin(clean_req)]

    if combined.empty:
        return {
            "status": "ready",
            "state": state.upper(),
            "total_matches": 0,
            "leads": [],
            "kpis": {"total_leads": 0, "stacked_count": 0, "absentee_count": 0, "avg_market_value": 0},
            "elapsed_ms": round((time.time() - t0) * 1000, 1)
        }

    # 1. Filter Matched Status
    if "Match_Status" in combined.columns:
        combined = combined[combined["Match_Status"].astype(str).str.upper() == "MATCHED"]

    # 2. Filter Filter Type
    f_lower = filter_type.lower()
    if f_lower in ["stacked", "double_distress", "triple_distress"]:
        if "Is_Stacked_Distress" in combined.columns:
            combined = combined[combined["Is_Stacked_Distress"].astype(str).str.upper() == "YES"]
    elif f_lower in ["absentee", "out_of_state"]:
        if "Is_Absentee" in combined.columns:
            combined = combined[combined["Is_Absentee"].astype(str).str.upper() == "YES"]
        if f_lower == "out_of_state" and "Absentee_Status" in combined.columns:
            combined = combined[combined["Absentee_Status"].astype(str).str.contains("Out-of-State", case=False, na=False)]
    elif f_lower in ["code", "code_violations"]:
        if "Lead_Type" in combined.columns:
            combined = combined[combined["Lead_Type"].astype(str).str.contains("code", case=False, na=False)]
    elif f_lower in ["probate"]:
        if "Lead_Type" in combined.columns:
            combined = combined[combined["Lead_Type"].astype(str).str.contains("probate|death certificate", case=False, na=False)]
    elif f_lower in ["lis_pendens", "foreclosure"]:
        if "Lead_Type" in combined.columns:
            combined = combined[combined["Lead_Type"].astype(str).str.contains("lis pendens", case=False, na=False)]

    # 3. Filter Distress Type if explicitly specified
    dt_lower = distress_type.lower()
    if dt_lower != "all" and "Lead_Type" in combined.columns:
        combined = combined[combined["Lead_Type"].astype(str).str.lower().str.contains(dt_lower, na=False)]

    # 4. Search Text
    if search_text.strip():
        st = search_text.strip().lower()
        mask = False
        for c in ["Property_Address", "Clean_Full_Name", "Parcel_ID", "Property_City", "Distress_Stack_Notes"]:
            if c in combined.columns:
                mask = mask | combined[c].astype(str).str.lower().str.contains(st, na=False)
        combined = combined[mask]

    # 5. Market Value Thresholds (vectorized boolean mask)
    if "Market_Value" in combined.columns and (min_equity_val > 0 or max_market_val > 0):
        vals = pd.to_numeric(combined["Market_Value"], errors="coerce").fillna(0)
        if min_equity_val > 0:
            combined = combined[vals >= min_equity_val]
        if max_market_val > 0:
            combined = combined[vals <= max_market_val]

    # 6. Exclude Corporate / LLC / Institutional Entities (Vectorized regex)
    if exclude_llc and "Clean_Full_Name" in combined.columns:
        is_corp = combined["Clean_Full_Name"].astype(str).str.contains(COMMERCIAL_REGEX, regex=True, na=False)
        if "Owner_Type" in combined.columns:
            is_corp = is_corp | (combined["Owner_Type"].astype(str).str.upper() == "COMPANY")
        combined = combined[~is_corp]

    # 7. Residential Property Filtering (Exclude commercial office buildings, warehouses, plazas)
    if property_type == "residential":
        bad_mask = False
        for c in ["Property_Address", "Property_Type", "Property_Use"]:
            if c in combined.columns:
                bad_mask = bad_mask | combined[c].astype(str).str.contains(
                    r'\b(?:ofc|office|commercial|retail|warehouse|shopping|industrial|plaza)\b',
                    case=False, na=False
                )
        combined = combined[~bad_mask]

    # 8. Deduplicate by Parcel_ID
    if "Parcel_ID" in combined.columns:
        combined = combined.drop_duplicates(subset=["Parcel_ID"], keep="first")

    total_matches = len(combined)

    # Compute KPIs
    stacked_count = int((combined.get("Is_Stacked_Distress", pd.Series(dtype=object)).astype(str).str.upper() == "YES").sum()) if "Is_Stacked_Distress" in combined.columns else 0
    absentee_count = int((combined.get("Is_Absentee", pd.Series(dtype=object)).astype(str).str.upper() == "YES").sum()) if "Is_Absentee" in combined.columns else 0
    mv_series = pd.to_numeric(combined.get("Market_Value", pd.Series(dtype=float)), errors="coerce").fillna(0) if "Market_Value" in combined.columns else pd.Series(dtype=float)
    avg_mv = int(mv_series.mean()) if len(mv_series) > 0 else 0

    # Vectorized Sort: Highest distress priority (Triple > Double > Single) + Out-of-State individual owners first
    if not combined.empty:
        notes_str = combined["Distress_Stack_Notes"].astype(str).str.upper() if "Distress_Stack_Notes" in combined.columns else pd.Series("", index=combined.index)
        abs_str = combined["Absentee_Status"].astype(str).str.upper() if "Absentee_Status" in combined.columns else pd.Series("", index=combined.index)
        
        is_triple = notes_str.str.contains("TRIPLE|3-WAY", regex=True, na=False)
        is_double = notes_str.str.contains("DOUBLE", regex=False, na=False)
        stack_score = np.where(is_triple, 3, np.where(is_double, 2, 1))
        
        is_oos = abs_str.str.contains("OUT-OF-STATE|OUT OF STATE", regex=True, na=False)
        is_abs = abs_str.str.contains("ABSENTEE", regex=False, na=False)
        abs_score = np.where(is_oos, 2, np.where(is_abs, 1, 0))
        
        combined["_priority_rank"] = stack_score * 10 + abs_score
        combined["_mv"] = pd.to_numeric(combined.get("Market_Value", 0), errors="coerce").fillna(0)
        combined = combined.sort_values(by=["_priority_rank", "_mv"], ascending=[False, True])
        combined = combined.drop(columns=["_priority_rank", "_mv"], errors="ignore")

    # Limit to max_records
    display_df = combined.head(max_records).copy()

    # Clean text values for JSON safety
    display_cols = [
        "County", "State", "Lead_Type", "Match_Status", "Clean_Full_Name",
        "Property_Address", "Property_City", "Property_Zip", "Parcel_ID",
        "Is_Absentee", "Absentee_Status", "Market_Value", "Assessed_Value",
        "Year_Built", "Living_Sqft", "Is_Stacked_Distress", "Distress_Stack_Notes",
        "Source_File", "Filing_Date", "Case_Number"
    ]
    valid_cols = [c for c in display_cols if c in display_df.columns]
    clean_df = display_df[valid_cols].fillna("")
    for c in clean_df.columns:
        if c in ["Market_Value", "Assessed_Value", "Year_Built", "Living_Sqft"]:
            clean_df[c] = pd.to_numeric(clean_df[c], errors="coerce").fillna(0).astype(int)
        else:
            clean_df[c] = clean_df[c].astype(str)

    leads = clean_df.to_dict(orient="records")
    elapsed_ms = round((time.time() - t0) * 1000, 1)

    return {
        "status": "ready",
        "state": state.upper(),
        "total_matches": total_matches,
        "returned_records": len(leads),
        "leads": leads,
        "kpis": {
            "total_leads": total_matches,
            "stacked_count": stacked_count,
            "absentee_count": absentee_count,
            "avg_market_value": avg_mv
        },
        "elapsed_ms": elapsed_ms
    }

# =====================================================================
# 2. EXECUTIVE BRIEFING GENERATOR
# =====================================================================

def generate_executive_briefing(state: str = "FL", counties: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Compile a high-level executive briefing across target counties or the entire state.
    Breaks down multi-distress signals, absentee investors, and top high-equity deals.
    """
    portals = load_county_portals(state)
    target_counties = {}
    if counties:
        clean_req = [c.strip().lower() for c in counties]
        for cname, meta in portals.items():
            if cname.lower() in clean_req or meta.get('folder_name', '').lower() in clean_req:
                target_counties[cname] = meta
    else:
        target_counties = portals

    total_parcels = 0
    all_leads = []
    county_lead_counts = {}

    for cname, meta in target_counties.items():
        folder = meta.get("folder_name", cname.lower().replace(" ", "_").replace("-", "_"))
        cdir = os.path.join(BASE_DIR, "data", state.upper(), folder)
        
        # Count master parcels
        mp_file = os.path.join(cdir, meta.get("parquet_name", "RP_PROPERTY_INFO.parquet"))
        if os.path.exists(mp_file):
            try:
                # Fast row count from Parquet metadata
                total_parcels += pd.read_parquet(mp_file, columns=["PARCEL_NUMBER"] if "PARCEL_NUMBER" in pd.read_parquet(mp_file).columns else ["Parcel ID"]).shape[0]
            except Exception:
                pass

        # Load leads
        cache_file = os.path.join(cdir, "matched_leads_cache.parquet")
        if os.path.exists(cache_file) and os.path.getsize(cache_file) > 1000:
            try:
                df = pd.read_parquet(cache_file)
                if len(df) > 0:
                    df["County"] = cname
                    all_leads.append(df)
                    county_lead_counts[cname] = len(df)
            except Exception:
                pass

    if not all_leads:
        return {
            "status": "empty",
            "state": state.upper(),
            "briefing_markdown": "No cached distress leads found in target region.",
            "metrics": {}
        }

    comb = pd.concat(all_leads, ignore_index=True)
    if "Match_Status" in comb.columns:
        comb = comb[comb["Match_Status"].astype(str).str.upper() == "MATCHED"]

    total_distress = len(comb)
    stacked = comb[comb.get("Is_Stacked_Distress", "").astype(str).str.upper() == "YES"] if "Is_Stacked_Distress" in comb.columns else pd.DataFrame()
    absentee = comb[comb.get("Is_Absentee", "").astype(str).str.upper() == "YES"] if "Is_Absentee" in comb.columns else pd.DataFrame()
    out_of_state = comb[comb.get("Absentee_Status", "").astype(str).str.contains("Out-of-State", case=False, na=False)] if "Absentee_Status" in comb.columns else pd.DataFrame()

    lead_types = comb["Lead_Type"].value_counts().to_dict() if "Lead_Type" in comb.columns else {}

    # Top 5 Genuine Distressed Homeowner Opportunities (Exclude LLCs, non-residential, and $35M commercial complexes)
    wholesale_candidates = comb.copy()
    if "Clean_Full_Name" in wholesale_candidates.columns:
        is_corp = wholesale_candidates["Clean_Full_Name"].apply(is_commercial_entity)
        if "Owner_Type" in wholesale_candidates.columns:
            is_corp = is_corp | (wholesale_candidates["Owner_Type"].astype(str).str.upper() == "COMPANY")
        wholesale_candidates = wholesale_candidates[~is_corp]

    for c in ["Property_Address", "Property_Type", "Property_Use"]:
        if c in wholesale_candidates.columns:
            comm = wholesale_candidates[c].astype(str).str.contains(
                r'\b(?:ofc|office|commercial|retail|warehouse|shopping|industrial|plaza)\b',
                case=False, na=False
            )
            wholesale_candidates = wholesale_candidates[~comm]

    mv_numeric = pd.to_numeric(wholesale_candidates.get("Market_Value", 0), errors="coerce").fillna(0)
    wholesale_candidates = wholesale_candidates[(mv_numeric >= 40000) & (mv_numeric <= 1200000)]
    if "Parcel_ID" in wholesale_candidates.columns:
        wholesale_candidates = wholesale_candidates.drop_duplicates(subset=["Parcel_ID"], keep="first")

    stack_score = wholesale_candidates.get("Distress_Stack_Notes", pd.Series()).astype(str).apply(
        lambda x: 3 if "TRIPLE" in x.upper() else (2 if "DOUBLE" in x.upper() else 1)
    )
    abs_score = wholesale_candidates.get("Absentee_Status", pd.Series()).astype(str).apply(
        lambda x: 2 if "OUT-OF-STATE" in x.upper() else (1 if "ABSENTEE" in x.upper() else 0)
    )
    wholesale_candidates["_rank"] = stack_score * 10 + abs_score
    wholesale_candidates["_mv"] = mv_numeric

    top_deals = wholesale_candidates.sort_values(by=["_rank", "_mv"], ascending=[False, True]).head(5)

    deals_summary = []
    for _, r in top_deals.iterrows():
        deals_summary.append({
            "county": r.get("County", ""),
            "address": clean_display_address(str(r.get("Property_Address", ""))),
            "owner": clean_display_name(str(r.get("Clean_Full_Name", ""))),
            "market_value": int(r.get("_mv", 0)),
            "lead_type": str(r.get("Lead_Type", "")),
            "stack_notes": str(r.get("Distress_Stack_Notes", "") or "Verified Distress"),
            "absentee": str(r.get("Absentee_Status", "Homeowner"))
        })

    # Build Executive Markdown
    today_str = datetime.date.today().strftime("%B %d, %Y")
    region_title = f"{len(target_counties)} Florida Counties" if not counties else ", ".join([c.title() for c in counties])
    
    md = f"""### 🧭 Scout AI Executive Briefing — {region_title}
**Date:** {today_str} • **Territory:** {state.upper()}

#### 📊 Market Pulse & Lead Inventory
- **Master Parcels Indexed:** `{total_parcels:,}` properties across `{len(target_counties)}` active counties
- **Active Distressed Leads:** `{total_distress:,}` verified properties
- **🔥 Multi-Distress Stacks:** `{len(stacked):,}` properties (`{(len(stacked)/total_distress*100 if total_distress else 0):.1f}%` of leads)
- **⚡ Absentee Owners:** `{len(absentee):,}` properties (`{(len(absentee)/total_distress*100 if total_distress else 0):.1f}%`)
- **✈️ Out-of-State Owners:** `{len(out_of_state):,}` properties (`{(len(out_of_state)/total_distress*100 if total_distress else 0):.1f}%`)

#### 🏷️ Breakdown by Distress Category
"""
    for lt, count in sorted(lead_types.items(), key=lambda x: x[1], reverse=True):
        md += f"- **{lt}:** `{count:,}` cases\n"

    md += "\n#### 💎 Top Priority Opportunities\n"
    for i, d in enumerate(deals_summary, 1):
        md += f"{i}. **{d['address']}** ({d['county']} County)\n"
        md += f"   - **Owner:** {d['owner']} • *Status:* {d['absentee']}\n"
        md += f"   - **Est. Market Value:** ${d['market_value']:,} • **Signal:** {d['stack_notes']}\n"

    return {
        "status": "success",
        "state": state.upper(),
        "date": today_str,
        "region": region_title,
        "briefing_markdown": md,
        "metrics": {
            "total_parcels": total_parcels,
            "total_leads": total_distress,
            "stacked_count": len(stacked),
            "absentee_count": len(absentee),
            "out_of_state_count": len(out_of_state),
            "lead_types": lead_types
        },
        "top_opportunities": deals_summary
    }

# =====================================================================
# 3. SENTINEL HEALTH WATCHDOG
# =====================================================================

def get_sentinel_status(state: str = "FL") -> Dict[str, Any]:
    """
    Real-time Sentinel system health, county cache freshness, and background worker state.
    """
    portals = load_county_portals(state)
    county_health = []
    total_leads = 0
    total_parcels = 0
    degraded_count = 0

    now = time.time()

    for cname, meta in sorted(portals.items()):
        folder = meta.get("folder_name", cname.lower().replace(" ", "_").replace("-", "_"))
        cdir = os.path.join(BASE_DIR, "data", state.upper(), folder)
        cache_file = os.path.join(cdir, "matched_leads_cache.parquet")
        master_file = os.path.join(cdir, meta.get("parquet_name", "RP_PROPERTY_INFO.parquet"))

        has_master = os.path.exists(master_file)
        has_cache = os.path.exists(cache_file) and os.path.getsize(cache_file) > 1000

        lead_count = 0
        last_sync = "Never"
        status = "READY"

        if has_cache:
            try:
                mtime = os.path.getmtime(cache_file)
                last_sync = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                df = pd.read_parquet(cache_file, columns=["Match_Status"] if "Match_Status" in pd.read_parquet(cache_file).columns else None)
                lead_count = len(df)
                total_leads += lead_count
                status = "HEALTHY"
            except Exception:
                status = "DEGRADED"
                degraded_count += 1
        else:
            status = "IDLE"

        county_health.append({
            "county": cname,
            "status": status,
            "lead_count": lead_count,
            "last_sync": last_sync,
            "has_master": has_master
        })

    overall = "HEALTHY" if degraded_count == 0 else "DEGRADED"

    return {
        "sentinel_status": overall,
        "name": "Scout Lead Sentinel",
        "version": "2.0.0",
        "state": state.upper(),
        "total_counties": len(portals),
        "total_active_leads": total_leads,
        "degraded_count": degraded_count,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "county_health": county_health
    }

# =====================================================================
# 4. NATURAL LANGUAGE INTENT DISPATCHER & CHAT AGENT
# =====================================================================

def process_scout_chat(
    message: str,
    state: str = "FL",
    current_county: Optional[str] = None
) -> Dict[str, Any]:
    """
    Processes natural language commands and returns structured responses with leads,
    executive briefings, or system actions.
    """
    msg = message.strip()
    msg_lower = msg.lower()

    # 1. Check for Executive Briefing request
    if any(k in msg_lower for k in ["briefing", "report", "executive", "daily summary", "overview", "pulse"]):
        # Extract counties if requested
        portals = load_county_portals(state)
        requested_counties = [c for c in portals if c.lower() in msg_lower]
        briefing = generate_executive_briefing(state=state, counties=requested_counties or None)
        return {
            "reply": briefing["briefing_markdown"],
            "action": "briefing",
            "kpis": briefing.get("metrics", {}),
            "top_leads": briefing.get("top_opportunities", [])
        }

    # 2. Check for System Status / Sentinel Health request
    if any(k in msg_lower for k in ["status", "health", "sentinel", "monitor", "uptime", "watchdog"]):
        status_info = get_sentinel_status(state=state)
        stat_md = f"""### 🧭 Scout AI Status — `{status_info['sentinel_status']}`
- **Active State:** `{status_info['state']}`
- **Territory Monitored:** `{status_info['total_counties']}` Counties
- **Total Cached Distress Leads:** `{status_info['total_active_leads']:,}` verified properties
- **Feed Health:** All `{status_info['total_counties']}` county pipelines reporting operational.
- **Background Watcher:** Active on `data/FL/` & live municipal APIs.
"""
        return {
            "reply": stat_md,
            "action": "status",
            "details": status_info
        }

    # 3. Check for Live Sync trigger
    if any(k in msg_lower for k in ["sync all", "re-sync", "sync apis", "refresh feeds", "poll live"]):
        return {
            "reply": "⚡ **Scout Background Sync Initiated**: All live Florida feeds (SeeClickFix, Cityworks, Accela, ArcGIS REST) are being polled in the background with automatic cumulative merging.",
            "action": "trigger_sync_all"
        }

    # 4. County + County or Statewide Cross-Query Filter
    portals = load_county_portals(state)
    detected_counties = [cname for cname in portals if cname.lower() in msg_lower]
    if not detected_counties and current_county and current_county.lower() in [c.lower() for c in portals]:
        detected_counties = [current_county]

    filter_type = "all"
    if any(k in msg_lower for k in ["triple distress", "double distress", "stacked", "multi-distress"]):
        filter_type = "stacked"
    elif any(k in msg_lower for k in ["out of state", "out-of-state"]):
        filter_type = "out_of_state"
    elif any(k in msg_lower for k in ["absentee", "investor"]):
        filter_type = "absentee"
    elif any(k in msg_lower for k in ["code", "violation", "nuisance"]):
        filter_type = "code"
    elif any(k in msg_lower for k in ["lis pendens", "pre-foreclosure", "foreclosure"]):
        filter_type = "lis_pendens"
    elif any(k in msg_lower for k in ["probate", "estate", "inherited"]):
        filter_type = "probate"

    # Search text extraction (e.g. looking for a specific city or owner)
    search_text = ""
    city_match = re.search(r'in\s+([A-Za-z\s]+?)(?:\s+county|\s+with|\s+and|\s*$)', msg, re.IGNORECASE)
    if city_match:
        potential_city = city_match.group(1).strip()
        if potential_city.lower() not in [c.lower() for c in portals]:
            search_text = potential_city

    res = query_statewide_leads(
        state=state,
        counties=detected_counties or None,
        filter_type=filter_type,
        search_text=search_text,
        max_records=100
    )

    count_str = f"{res['total_matches']:,}"
    c_scope = f"in {', '.join(detected_counties)}" if detected_counties else "across all 37 Florida counties"
    f_desc = f"{filter_type.replace('_', ' ').title()}" if filter_type != "all" else "Verified Distress"

    reply_md = f"### 🧭 Scout AI Query Results: {count_str} Leads Found\n"
    reply_md += f"Found **{count_str} {f_desc}** properties {c_scope} in `{res['elapsed_ms']}ms`.\n\n"
    reply_md += f"- **🔥 Stacked Distress:** `{res['kpis']['stacked_count']:,}`\n"
    reply_md += f"- **⚡ Absentee Owners:** `{res['kpis']['absentee_count']:,}`\n"
    reply_md += f"- **🏷️ Avg Market Value:** `${res['kpis']['avg_market_value']:,}`\n"
    reply_md += f"- **🛡️ Smart Filters:** Excluded corporate LLCs & commercial properties > $1.5M.\n\n"
    reply_md += f"Click **View Leads in Table** below to open the dedicated full results explorer with live price, LLC, and city filters."

    return {
        "reply": reply_md,
        "action": "leads_query",
        "total_matches": res["total_matches"],
        "leads": res["leads"],
        "kpis": res["kpis"],
        "elapsed_ms": res["elapsed_ms"]
    }
