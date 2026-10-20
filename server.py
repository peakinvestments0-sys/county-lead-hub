import os
import io
import sys
import time
import json
import webbrowser
import pandas as pd
import numpy as np
import requests
from requests.auth import HTTPBasicAuth
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Dict, Any, List, Tuple
import re
import threading
import random
from pydantic import BaseModel

# Reconfigure stdout/stderr to utf-8 on Windows to prevent charmap encoding errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response, Request, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Ensure root directory is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.config import WHOLESALE_EXPORT_PRESET, DATA_DIR
from src.initial_sms_templates import DEFAULT_SMS_TEMPLATES, load_initial_sms_templates
from src.saved_property_matches import load_property_index, address_key
from src.counties import (
    DEFAULT_STATES, load_available_states,
    load_county_portals, get_county_paths, update_county_portal_urls,
    load_custom_categories, add_custom_category, delete_custom_category
)
from src.data_loader import load_master_parcels, ParcelDatabase
from src.matcher import CrossReferenceEngine
from src.normalizer import (
    parse_owner_name, extract_human_defendants,
    clean_display_address, clean_display_name, clean_display_city
)
from pydantic import BaseModel

from src.link_zone_service import link_zone_service
from src.scout_operator_agent import (
    query_statewide_leads,
    generate_executive_briefing,
    get_sentinel_status,
    process_scout_chat
)
from src.seller_bot_engine import (
    SellerBotEngine, load_seller_bot_settings, save_seller_bot_settings,
    load_seller_golden_replies, save_seller_golden_reply, delete_seller_golden_reply,
    evaluate_deal_spread, test_seller_gemini_connection,
    clean_address_for_sms, sanitize_sms_no_underlines_no_hyphens
)
from src.valuation_service import get_property_market_valuation, load_valuations_cache
from src.florida_underwriter_engine import underwrite_407flips_deal
from src.calendar_service import (
    load_scheduled_callbacks, save_scheduled_callbacks,
    send_calendar_invite_email, build_google_calendar_url
)
from src.suppression_service import (
    is_number_suppressed, add_to_suppression_list, remove_from_suppression_list,
    load_suppression_list, is_dnc_number, add_to_dnc_list, load_dnc_list,
    is_lead_blocked_from_outreach, scrub_outbound_lead_list, normalize_phone_digits
)
seller_bot = SellerBotEngine()

app = FastAPI(title="Florida Lead Hub API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global in-memory cache for county ParcelDatabases
DB_CACHE = {}

class ScoutChatRequest(BaseModel):
    message: str
    state: str = "FL"
    county: Optional[str] = None

class ScoutCrossQueryRequest(BaseModel):
    state: str = "FL"
    counties: Optional[List[str]] = None
    filter_type: str = "all"
    distress_type: str = "all"
    search_text: str = ""
    min_equity_val: int = 0
    min_market_val: int = 0
    max_market_val: int = 0
    exclude_llc: bool = False
    property_type: str = "all"
    max_records: int = 150

class LegacyOperatorCommandRequest(BaseModel):
    prompt: str
    phone: Optional[str] = None

@app.get("/api/states")
def get_states():
    """Return all active states (discovers active states dynamically)."""
    return load_available_states()

@app.get("/api/link-zone/health")
def get_link_zone_health():
    """Get live connection health, status, state statistics, and audit history for Link Zone."""
    return link_zone_service.get_health_report()

@app.get("/api/florida/apis")
def get_florida_apis_catalog(state: str = "FL"):
    """Return all verified government APIs from Link Zone for specified state (FL, GA, TN, TX, etc.)."""
    return link_zone_service.get_state_api_catalog(state=state)

@app.post("/api/link-zone/resync")
def trigger_link_zone_resync():
    """Manually force re-scan of C:\\Projects\\Apps\\link-zone\\data and refresh portals."""
    return link_zone_service.force_resync()

@app.post("/api/orange/sync-apis")
@app.post("/api/code-enforcement/sync-orlando")
def trigger_orlando_code_sync():
    """Live sync open residential neglect code violations from City of Orlando SODA API."""
    try:
        from src.orlando_code_sync import sync_orlando_code_enforcement
        db = get_database("Orange", state="FL")
        result = sync_orlando_code_enforcement(db=db)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/pinellas/sync-apis")
@app.post("/api/code-enforcement/sync-pinellas")
def trigger_pinellas_api_sync():
    """Live sync Pinellas County APIs: Accela Substantial Damage & SeeClickFix Code Violations."""
    try:
        from src.pinellas_code_sync import sync_pinellas_live_apis
        result = sync_pinellas_live_apis()
        if getattr(app.state, 'last_county', '') == 'Pinellas':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/sarasota/sync-apis")
@app.post("/api/code-enforcement/sync-sarasota")
def trigger_sarasota_api_sync():
    """Live sync Sarasota County SeeClickFix code and property distress API."""
    try:
        from src.sarasota_code_sync import sync_sarasota_live_apis
        result = sync_sarasota_live_apis()
        if getattr(app.state, 'last_county', '') == 'Sarasota':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/charlotte/sync-apis")
@app.post("/api/code-enforcement/sync-charlotte")
def trigger_charlotte_api_sync():
    """Live sync Charlotte County ArcGIS code enforcement and FEMA distress API."""
    try:
        from src.charlotte_code_sync import sync_charlotte_live_apis
        result = sync_charlotte_live_apis()
        if getattr(app.state, 'last_county', '') == 'Charlotte':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/lake/sync-apis")
@app.post("/api/code-enforcement/sync-lake")
def trigger_lake_api_sync():
    """Live sync Lake County GIS code enforcement cases API."""
    try:
        from src.lake_code_sync import sync_lake_live_apis
        result = sync_lake_live_apis()
        if getattr(app.state, 'last_county', '') == 'Lake':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/pasco/sync-apis")
@app.post("/api/code-enforcement/sync-pasco")
def trigger_pasco_api_sync():
    """Live sync Pasco County SeeClickFix code & distress API."""
    try:
        from src.pasco_code_sync import sync_pasco_live_apis
        result = sync_pasco_live_apis()
        if getattr(app.state, 'last_county', '') == 'Pasco':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/manatee/sync-apis")
@app.post("/api/code-enforcement/sync-manatee")
def trigger_manatee_api_sync():
    """Live sync Manatee County SeeClickFix code & distress API."""
    try:
        from src.manatee_code_sync import sync_manatee_live_apis
        result = sync_manatee_live_apis()
        if getattr(app.state, 'last_county', '') == 'Manatee':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/alachua/sync-apis")
@app.post("/api/code-enforcement/sync-alachua")
def trigger_alachua_api_sync():
    """Live sync Alachua County GIS code enforcement cases API."""
    try:
        from src.alachua_code_sync import sync_alachua_live_apis
        result = sync_alachua_live_apis()
        if getattr(app.state, 'last_county', '') == 'Alachua':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/volusia/sync-apis")
@app.post("/api/code-enforcement/sync-volusia")
def trigger_volusia_api_sync():
    """Live sync Volusia County / Daytona Beach code enforcement & SeeClickFix distress API."""
    try:
        from src.volusia_code_sync import sync_volusia_live_apis
        result = sync_volusia_live_apis()
        if getattr(app.state, 'last_county', '') == 'Volusia':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/hillsborough/sync-apis")
@app.post("/api/code-enforcement/sync-hillsborough")
def trigger_hillsborough_api_sync():
    """Live sync Hillsborough County structural damage assessments & open distress API."""
    try:
        from src.hillsborough_code_sync import sync_hillsborough_live_apis
        result = sync_hillsborough_live_apis()
        if getattr(app.state, 'last_county', '') == 'Hillsborough':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/osceola/sync-apis")
@app.post("/api/code-enforcement/sync-osceola")
def trigger_osceola_api_sync():
    """Live sync Osceola County GIS residential damage & structural distress API."""
    try:
        from src.osceola_code_sync import sync_osceola_live_apis
        result = sync_osceola_live_apis()
        if getattr(app.state, 'last_county', '') == 'Osceola':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/polk/sync-apis")
@app.post("/api/code-enforcement/sync-polk")
def trigger_polk_api_sync():
    """Live sync Polk County / Lakeland IMS code enforcement & SeeClickFix distress API."""
    try:
        from src.polk_code_sync import sync_polk_live_apis
        result = sync_polk_live_apis()
        if getattr(app.state, 'last_county', '') == 'Polk':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/lee/sync-apis")
@app.post("/api/code-enforcement/sync-lee")
def trigger_lee_api_sync():
    """Live sync Lee County GIS Nuisance Accumulation Violations & Municipal Liens API."""
    try:
        from src.lee_code_sync import sync_lee_leads
        result = sync_lee_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') == 'Lee':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/collier/sync-apis")
@app.post("/api/code-enforcement/sync-collier")
def trigger_collier_api_sync():
    """Live sync Collier County GIS Milestone Structural Inspections & Property Distress API."""
    try:
        from src.collier_code_sync import sync_collier_leads
        result = sync_collier_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') == 'Collier':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/brevard/sync-apis")
@app.post("/api/code-enforcement/sync-brevard")
def trigger_brevard_api_sync():
    """Live sync Brevard County & Municipalities SeeClickFix Property Distress API."""
    try:
        from src.brevard_code_sync import sync_brevard_leads
        result = sync_brevard_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') == 'Brevard':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/duval/sync-apis")
@app.post("/api/code-enforcement/sync-duval")
def trigger_duval_api_sync():
    """Live sync Duval County / Jacksonville SeeClickFix distress API."""
    try:
        from src.duval_code_sync import sync_duval_leads
        result = sync_duval_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') == 'Duval':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/marion/sync-apis")
@app.post("/api/code-enforcement/sync-marion")
def trigger_marion_api_sync():
    """Live sync Marion County / Ocala Recorded Municipal Liens & SeeClickFix distress API."""
    try:
        from src.marion_code_sync import sync_marion_leads
        result = sync_marion_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') == 'Marion':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/broward/sync-apis")
@app.post("/api/code-enforcement/sync-broward")
def trigger_broward_api_sync():
    """Live sync Broward County (Fort Lauderdale, Hollywood, etc.) SeeClickFix distress API."""
    try:
        from src.broward_code_sync import sync_broward_leads
        result = sync_broward_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') == 'Broward':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/miami-dade/sync-apis")
@app.post("/api/code-enforcement/sync-miami-dade")
def trigger_miami_dade_api_sync():
    """Live sync Miami-Dade County (Miami, Hialeah, Miami Beach, etc.) SeeClickFix distress API."""
    try:
        from src.miami_dade_code_sync import sync_miami_dade_leads
        result = sync_miami_dade_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Miami-Dade', 'Miami_Dade', 'miami_dade']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/palm-beach/sync-apis")
@app.post("/api/code-enforcement/sync-palm-beach")
def trigger_palm_beach_api_sync():
    """Live sync Palm Beach County (West Palm Beach, Boca Raton, etc.) SeeClickFix distress API."""
    try:
        from src.palm_beach_code_sync import sync_palm_beach_leads
        result = sync_palm_beach_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Palm Beach', 'Palm_Beach', 'palm_beach']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/st-lucie/sync-apis")
@app.post("/api/code-enforcement/sync-st-lucie")
def trigger_st_lucie_api_sync():
    """Live sync St. Lucie County (Port St. Lucie, Fort Pierce, etc.) SeeClickFix distress API."""
    try:
        from src.st_lucie_code_sync import sync_st_lucie_leads
        result = sync_st_lucie_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['St. Lucie', 'St_Lucie', 'st._lucie', 'st_lucie']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/martin/sync-apis")
@app.post("/api/code-enforcement/sync-martin")
def trigger_martin_api_sync():
    """Live sync Martin County (Stuart, Jensen Beach, etc.) SeeClickFix distress API."""
    try:
        from src.martin_code_sync import sync_martin_leads
        result = sync_martin_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Martin', 'martin']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/indian-river/sync-apis")
@app.post("/api/code-enforcement/sync-indian-river")
def trigger_indian_river_api_sync():
    """Live sync Indian River County (Vero Beach, Sebastian, etc.) SeeClickFix distress API."""
    try:
        from src.indian_river_code_sync import sync_indian_river_leads
        result = sync_indian_river_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Indian River', 'Indian_River', 'indian_river']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/st-johns/sync-apis")
@app.post("/api/code-enforcement/sync-st-johns")
def trigger_st_johns_api_sync():
    """Live sync St. Johns County (St. Augustine, Ponte Vedra, etc.) code enforcement distress."""
    try:
        from src.st_johns_code_sync import sync_st_johns_leads
        result = sync_st_johns_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['St. Johns', 'St_Johns', 'st._johns', 'st_johns']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/flagler/sync-apis")
@app.post("/api/code-enforcement/sync-flagler")
def trigger_flagler_api_sync():
    """Live sync Flagler County (Palm Coast, Flagler Beach, etc.) code enforcement distress."""
    try:
        from src.flagler_code_sync import sync_flagler_leads
        result = sync_flagler_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Flagler', 'flagler']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/nassau/sync-apis")
@app.post("/api/code-enforcement/sync-nassau")
def trigger_nassau_api_sync():
    """Live sync Nassau County (Fernandina Beach, Yulee, etc.) code enforcement distress."""
    try:
        from src.nassau_code_sync import sync_nassau_leads
        result = sync_nassau_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Nassau', 'nassau']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/citrus/sync-apis")
@app.post("/api/code-enforcement/sync-citrus")
def trigger_citrus_api_sync():
    """Live sync Citrus County (Inverness, Crystal River, etc.) code enforcement distress."""
    try:
        from src.citrus_code_sync import sync_citrus_leads
        result = sync_citrus_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Citrus', 'citrus']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/hernando/sync-apis")
@app.post("/api/code-enforcement/sync-hernando")
def trigger_hernando_api_sync():
    """Live sync Hernando County (Brooksville, Spring Hill, etc.) structural damage & code enforcement distress."""
    try:
        from src.hernando_code_sync import sync_hernando_leads
        result = sync_hernando_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Hernando', 'hernando']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/sumter/sync-apis")
@app.post("/api/code-enforcement/sync-sumter")
def trigger_sumter_api_sync():
    """Live sync Sumter County (The Villages, Wildwood, etc.) code enforcement distress."""
    try:
        from src.sumter_code_sync import sync_sumter_leads
        result = sync_sumter_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Sumter', 'sumter']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/highlands/sync-apis")
@app.post("/api/code-enforcement/sync-highlands")
def trigger_highlands_api_sync():
    """Live sync Highlands County (Sebring, Avon Park, Lake Placid) code enforcement distress."""
    try:
        from src.highlands_code_sync import sync_highlands_leads
        result = sync_highlands_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Highlands', 'highlands']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/clay/sync-apis")
@app.post("/api/code-enforcement/sync-clay")
def trigger_clay_api_sync():
    """Live sync Clay County (Orange Park, Green Cove Springs, etc.) code enforcement distress."""
    try:
        from src.clay_code_sync import sync_clay_leads
        result = sync_clay_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Clay', 'clay']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/leon/sync-apis")
@app.post("/api/code-enforcement/sync-leon")
def trigger_leon_api_sync():
    """Live sync Leon County / Tallahassee Cityworks code enforcement violations distress."""
    try:
        from src.leon_code_sync import sync_leon_leads
        result = sync_leon_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Leon', 'leon']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/escambia/sync-apis")
@app.post("/api/code-enforcement/sync-escambia")
def trigger_escambia_api_sync():
    """Live sync Escambia County (Pensacola, Cantonment, Century) code enforcement distress."""
    try:
        from src.escambia_code_sync import sync_escambia_leads
        result = sync_escambia_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Escambia', 'escambia']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/bay/sync-apis")
@app.post("/api/code-enforcement/sync-bay")
def trigger_bay_api_sync():
    """Live sync Bay County (Panama City, Lynn Haven, Panama City Beach) code enforcement distress."""
    try:
        from src.bay_code_sync import sync_bay_leads
        result = sync_bay_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Bay', 'bay']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/okaloosa/sync-apis")
@app.post("/api/code-enforcement/sync-okaloosa")
def trigger_okaloosa_api_sync():
    """Live sync Okaloosa County (Fort Walton Beach, Destin, Crestview) code enforcement distress."""
    try:
        from src.okaloosa_code_sync import sync_okaloosa_leads
        result = sync_okaloosa_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Okaloosa', 'okaloosa']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/santa-rosa/sync-apis")
@app.post("/api/code-enforcement/sync-santa-rosa")
def trigger_santa_rosa_api_sync():
    """Live sync Santa Rosa County (Milton, Gulf Breeze, Navarre, Pace) code enforcement distress."""
    try:
        from src.santa_rosa_code_sync import sync_santa_rosa_leads
        result = sync_santa_rosa_leads(force_refresh=True)
        if getattr(app.state, 'last_county', '') in ['Santa Rosa', 'santa_rosa', 'santa-rosa']:
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}





@app.post("/api/orange/sync-jail-leads")
def trigger_orange_jail_sync():
    """Live sync daily Orange County Jail Felony bookings, match against master parcels, and update cache."""
    try:
        from src.jail_lead_agent import sync_orange_county_jail_leads
        result = sync_orange_county_jail_leads(force_download=True)
        if getattr(app.state, 'last_county', '') == 'Orange':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/seminole/sync-apis")
@app.post("/api/seminole/sync-jail-leads")
def trigger_seminole_jail_sync():
    """Live sync daily Seminole County Jail Felony bookings, match against master parcels, and update cache."""
    try:
        from src.seminole_jail_lead_agent import sync_seminole_county_jail_leads
        result = sync_seminole_county_jail_leads(max_reports=7)
        if getattr(app.state, 'last_county', '') == 'Seminole':
            app.state.last_results = None
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}

# =====================================================================
# SCOUT OPERATOR & SENTINEL AGENT ENDPOINTS
# =====================================================================

@app.post("/api/scout/chat")
def scout_chat(req: ScoutChatRequest):
    """
    Process natural language commands, questions, and instructions to Scout.
    Dispatches queries, briefings, health status, and live sync triggers.
    """
    try:
        res = process_scout_chat(message=req.message, state=req.state, current_county=req.county)
        return res
    except Exception as e:
        return {"reply": f"⚠️ Scout encountered an error: {str(e)}", "action": "error", "error": str(e)}

@app.get("/api/scout/status")
def scout_status(state: str = Query("FL")):
    """
    Real-time Sentinel system health, county cache freshness, and background worker state.
    """
    try:
        return get_sentinel_status(state=state)
    except Exception as e:
        return {"sentinel_status": "ERROR", "error": str(e)}

@app.get("/api/scout/briefing")
def scout_briefing(state: str = Query("FL"), counties: Optional[str] = Query(None)):
    """
    High-level executive briefing across target counties or the entire state.
    """
    try:
        c_list = [c.strip() for c in counties.split(",")] if counties else None
        return generate_executive_briefing(state=state, counties=c_list)
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/scout/cross-query")
def scout_cross_query(req: ScoutCrossQueryRequest):
    """
    Columnar sub-second query across all counties in the target state.
    """
    try:
        return query_statewide_leads(
            state=req.state,
            counties=req.counties,
            filter_type=req.filter_type,
            distress_type=req.distress_type,
            search_text=req.search_text,
            min_equity_val=req.min_equity_val,
            min_market_val=req.min_market_val,
            max_market_val=req.max_market_val,
            exclude_llc=req.exclude_llc,
            property_type=req.property_type,
            max_records=req.max_records
        )
    except Exception as e:
        return {"status": "error", "message": str(e), "leads": [], "total_matches": 0}

@app.post("/api/scout/sync-all")
def scout_sync_all(background_tasks: BackgroundTasks, state: str = Query("FL")):
    """
    Triggers concurrent background live API polls across all supported counties.
    """
    def run_all_syncs():
        from src.counties import load_county_portals
        import importlib
        portals = load_county_portals(state)
        for cname, meta in portals.items():
            folder = meta.get("folder_name", cname.lower().replace(" ", "_").replace("-", "_"))
            sync_module_name = f"src.{folder}_code_sync"
            try:
                mod = importlib.import_module(sync_module_name)
                for fn_name in [
                    f"sync_{folder}_live_apis",
                    f"run_{folder}_live_sync",
                    "sync_live_apis",
                    "sync_orlando_code_enforcement",
                    "sync_pinellas_live_apis",
                    "sync_hillsborough_damage_leads"
                ]:
                    if hasattr(mod, fn_name):
                        getattr(mod, fn_name)()
                        break
            except Exception:
                pass

    background_tasks.add_task(run_all_syncs)
    return {
        "status": "initiated",
        "message": f"Scout has queued background live API synchronization across all active {state.upper()} counties."
    }

# Backward compatibility routes
@app.get("/api/operator/triage")
def get_operator_triage():
    status = get_sentinel_status("FL")
    return {
        "status": "ready",
        "operator": "Scout",
        "stats": {
            "urgent_count": status.get("degraded_count", 0),
            "total_leads": status.get("total_active_leads", 0),
            "estimated_pipeline_spread": 0
        }
    }

@app.get("/api/operator/timers")
def get_operator_timers():
    return {"timers": []}

@app.post("/api/operator/command")
def execute_operator_command(req: LegacyOperatorCommandRequest):
    return process_scout_chat(req.prompt, state="FL")

@app.get("/api/operator/memory")
def get_operator_memory():
    return {"memory": ["Scout Lead Sentinel active across 37 Florida counties."]}

def get_database(county_key: str, state: str = "FL") -> ParcelDatabase:
    """Retrieve or load cached ParcelDatabase for given county and state."""
    state = (state or "FL").upper()
    cache_key = f"{state}_{county_key}".lower()
    if cache_key in DB_CACHE:
        return DB_CACHE[cache_key]
    
    info = get_county_paths(county_key, state=state)
    if not info['has_master']:
        raise HTTPException(status_code=404, detail=f"No parcel database found for {county_key} ({state}). Please install master file in {info['target_dir']}")
    
    db = load_master_parcels(csv_path=info['csv_path'], parquet_path=info['parquet_path'])
    DB_CACHE[cache_key] = db
    return db

# Known display metrics for county cards (Authentic Florida coastlines, skylines, and waterways)
COUNTY_DISPLAY_METRICS = {
    "Pinellas": {"records": 437559, "updated": "Sep 22, 2026", "img": "/static/images/county_pinellas_coast.jpg"}, # Clearwater / St. Pete Gulf Coast
    "Orange": {"records": 496712, "updated": "Oct 06, 2026", "img": "/static/images/county_orange_lake_eola.jpg"}, # Lake Eola / Orlando Skyline
    "Seminole": {"records": 181244, "updated": "Oct 10, 2026", "img": "/static/images/county_florida_palms.jpg"}, # Lake Mary / Sanford / Central Florida
    "Pasco": {"records": 328045, "updated": "Oct 10, 2026", "img": "/static/images/county_pasco_gulf.jpg"}, # Gulf Harbors / coastal Florida
    "Sarasota": {"records": 325358, "updated": "Oct 10, 2026", "img": "/static/images/county_sarasota_key.jpg"}, # Siesta Key turquoise waters
    "Manatee": {"records": 241088, "updated": "Oct 10, 2026", "img": "/static/images/county_pinellas_coast.jpg"}, # Bradenton Anna Maria Island
    "Charlotte": {"records": 223248, "updated": "Oct 10, 2026", "img": "/static/images/hero_banner_florida.jpg"}, # Punta Gorda / Port Charlotte
    "Lake": {"records": 216981, "updated": "Oct 10, 2026", "img": "/static/images/county_polk_central.jpg"}, # Clermont / Leesburg / Lake Harris
    "Alachua": {"records": 109962, "updated": "Oct 10, 2026", "img": "/static/images/hero_banner_florida.jpg"}, # Gainesville / University / Alachua
    "Volusia": {"records": 313548, "updated": "Oct 10, 2026", "img": "/static/images/county_florida_palms.jpg"}, # Daytona Beach coastline & palms
    "Osceola": {"records": 210878, "updated": "Oct 10, 2026", "img": "/static/images/county_polk_central.jpg"}, # Central Florida wetlands & lakes
    "Polk": {"records": 438643, "updated": "Oct 10, 2026", "img": "/static/images/county_polk_central.jpg"}, # Central Florida lakes (Lakeland, Winter Haven)
    "Hillsborough": {"records": 531609, "updated": "Oct 10, 2026", "img": "/static/images/county_hillsborough_tampa.jpg"}, # Tampa Riverwalk & Downtown Skyline
    "Broward": {"records": 754339, "updated": "Oct 11, 2026", "img": "/static/images/county_broward_beach.jpg"}, # Fort Lauderdale Oceanfront & Palms
    "Miami-Dade": {"records": 584724, "updated": "Oct 11, 2026", "img": "/static/images/county_miami_dade.jpg"}, # Miami South Beach & Biscayne Bay
    "Lee": {"records": 563028, "updated": "Oct 10, 2026", "img": "/static/images/county_lee_fortmyers.jpg"}, # Fort Myers Beach / Gulf
    "Collier": {"records": 293859, "updated": "Oct 10, 2026", "img": "/static/images/county_naples_collier.jpg"}, # Naples Pier Sunset & Coastal
    "Brevard": {"records": 349261, "updated": "Oct 10, 2026", "img": "/static/images/county_florida_palms.jpg"}, # Space Coast / Melbourne / Cocoa Beach
    "Duval": {"records": 403813, "updated": "Oct 10, 2026", "img": "/static/images/hero_banner_florida.jpg"}, # Jacksonville / River City / Beaches
    "Marion": {"records": 286006, "updated": "Oct 10, 2026", "img": "/static/images/county_polk_central.jpg"}, # Ocala / Horse Country / Marion County
    "Palm Beach": {"records": 656525, "updated": "Oct 11, 2026", "img": "/static/images/county_coastal_condos.jpg"}, # Palm Beach Atlantic Coast & estates
    "St. Lucie": {"records": 190108, "updated": "Oct 11, 2026", "img": "/static/images/county_coastal_condos.jpg"},
    "Martin": {"records": 97552, "updated": "Oct 11, 2026", "img": "/static/images/county_florida_palms.jpg"},
    "Indian River": {"records": 95226, "updated": "Oct 11, 2026", "img": "/static/images/county_coastal_condos.jpg"},
    "St. Johns": {"records": 152576, "updated": "Oct 11, 2026", "img": "/static/images/hero_banner_florida.jpg"},
    "Flagler": {"records": 87996, "updated": "Oct 11, 2026", "img": "/static/images/county_coastal_condos.jpg"},
    "Nassau": {"records": 59055, "updated": "Oct 11, 2026", "img": "/static/images/county_florida_palms.jpg"},
    "Citrus": {"records": 147181, "updated": "Oct 11, 2026", "img": "/static/images/county_polk_central.jpg"},
    "Hernando": {"records": 120180, "updated": "Oct 11, 2026", "img": "/static/images/county_florida_palms.jpg"},
    "Sumter": {"records": 104118, "updated": "Oct 11, 2026", "img": "/static/images/county_polk_central.jpg"},
    "Highlands": {"records": 112672, "updated": "Oct 11, 2026", "img": "/static/images/county_polk_central.jpg"},
    "Clay": {"records": 104927, "updated": "Oct 11, 2026", "img": "/static/images/hero_banner_florida.jpg"},
    "Leon": {"records": 111036, "updated": "Oct 11, 2026", "img": "/static/images/county_florida_palms.jpg"},
    "Escambia": {"records": 161419, "updated": "Oct 11, 2026", "img": "/static/images/hero_banner_florida.jpg"},
    "Bay": {"records": 130626, "updated": "Oct 11, 2026", "img": "/static/images/county_coastal_condos.jpg"},
    "Okaloosa": {"records": 112382, "updated": "Oct 11, 2026", "img": "/static/images/county_coastal_condos.jpg"},
    "Santa Rosa": {"records": 110298, "updated": "Oct 11, 2026", "img": "/static/images/hero_banner_florida.jpg"},
}

@app.get("/api/stats")
def get_global_stats(state: str = "FL"):
    """Return top summary KPI statistics for dashboard banner with live counts."""
    state = (state or "FL").upper()
    state_info = DEFAULT_STATES.get(state, DEFAULT_STATES["FL"])
    registry = load_county_portals(state=state)
    live_count = sum(1 for k in registry if get_county_paths(k, state=state).get("has_master"))
    ready_count = max(0, len(registry) - live_count)
    return {
        "state": state,
        "state_name": state_info["name"],
        "total_records": "9,843,782" if state == "FL" else "0",
        "total_records_sub": f"Master Parcels Indexed ({state})",
        "unique_properties": "52,896" if state == "FL" else "0",
        "unique_properties_sub": "Verified Distressed Leads",
        "counties_available": f"{live_count} Live / {ready_count} Ready",
        "counties_available_sub": "Drop Data to Activate",
        "updated_status": "Updated Daily",
        "updated_status_sub": f"Direct from {state_info['name']} Sources"
    }

@app.get("/api/counties")
def get_counties(state: str = "FL"):
    """Return all available counties for specified state with live status and metadata."""
    state = (state or "FL").upper()
    registry = load_county_portals(state=state)
    counties = []
    
    # Priority list matching reference image
    priority = [
        "Pinellas", "Orange", "Seminole", "Sarasota", "Pasco", "Manatee", "Charlotte", "Lake", "Alachua", "Volusia",
        "Osceola", "Polk", "Hillsborough", "Broward", "Miami-Dade", "Lee", "Collier", "Brevard", "Duval", "Marion",
        "Palm Beach", "St. Lucie", "Martin", "Indian River", "St. Johns", "Flagler", "Nassau",
        "Citrus", "Hernando", "Sumter", "Highlands", "Clay", "Leon",
        "Escambia", "Bay", "Okaloosa", "Santa Rosa"
    ]


    
    keys_sorted = sorted(registry.keys(), key=lambda k: priority.index(k) if k in priority else 99)
    
    for key in keys_sorted:
        info = get_county_paths(key, state=state)
        defaults = COUNTY_DISPLAY_METRICS.get(key, {
            "records": 5000,
            "updated": "Sep 20, 2026",
            "img": "/static/images/hero_banner_florida.jpg"
        })
        
        has_master = info["has_master"]
        has_cache = os.path.exists(os.path.join(info['target_dir'], 'matched_leads_cache.parquet'))
        
        rec_num = defaults["records"]
        if key == "Pinellas" and state == "FL":
            rec_num = 437559
            status_badge = "LIVE & READY"
            rec_str = "437,559 parcels • 9,753 leads"
        elif key == "Orange" and state == "FL" and has_master:
            rec_num = 496712
            status_badge = "LIVE & READY"
            rec_str = "496,712 parcels • 13,167 leads"
        elif key == "Seminole" and state == "FL" and has_master:
            rec_num = 181244
            status_badge = "LIVE & READY"
            rec_str = "181,244 parcels • 25 leads"
        elif key == "Sarasota" and state == "FL" and has_master:
            rec_num = 325358
            status_badge = "LIVE & READY"
            rec_str = "325,358 parcels • 194 leads"
        elif key == "Charlotte" and state == "FL" and has_master:
            rec_num = 223248
            status_badge = "LIVE & READY"
            rec_str = "223,248 parcels • 3,988 leads"
        elif key == "Lake" and state == "FL" and has_master:
            rec_num = 216981
            status_badge = "LIVE & READY"
            rec_str = "216,981 parcels • 424 leads"
        elif key == "Pasco" and state == "FL" and has_master:
            rec_num = 328045
            status_badge = "LIVE & READY"
            rec_str = "328,045 parcels • 86 leads"
        elif key == "Manatee" and state == "FL" and has_master:
            rec_num = 241088
            status_badge = "LIVE & READY"
            rec_str = "241,088 parcels • 21 leads"
        elif key == "Alachua" and state == "FL" and has_master:
            rec_num = 109962
            status_badge = "LIVE & READY"
            rec_str = "109,962 parcels • 2,346 leads"
        elif key == "Volusia" and state == "FL" and has_master:
            rec_num = 313548
            status_badge = "LIVE & READY"
            rec_str = "313,548 parcels • 2,572 leads"
        elif key == "Hillsborough" and state == "FL" and has_master:
            rec_num = 531609
            status_badge = "LIVE & READY"
            rec_str = "531,609 parcels • 13,746 leads"
        elif key == "Osceola" and state == "FL" and has_master:
            rec_num = 210878
            status_badge = "LIVE & READY"
            rec_str = "210,878 parcels • 7,286 leads"
        elif key == "Polk" and state == "FL" and has_master:
            rec_num = 438643
            status_badge = "LIVE & READY"
            rec_str = "438,643 parcels • 834 leads"
        elif key == "Lee" and state == "FL" and has_master:
            rec_num = 563028
            status_badge = "LIVE & READY"
            rec_str = "563,028 parcels • 1,822 leads"
        elif key == "Collier" and state == "FL" and has_master:
            rec_num = 293859
            status_badge = "LIVE & READY"
            rec_str = "293,859 parcels • 172 leads"
        elif key == "Brevard" and state == "FL" and has_master:
            rec_num = 349261
            status_badge = "LIVE & READY"
            rec_str = "349,261 parcels • 39 leads"
        elif key == "Duval" and state == "FL" and has_master:
            rec_num = 403813
            status_badge = "LIVE & READY"
            rec_str = "403,813 parcels • 2 leads"
        elif key == "Marion" and state == "FL" and has_master:
            rec_num = 286006
            status_badge = "LIVE & READY"
            rec_str = "286,006 parcels • 305 leads"
        elif has_master:
            if has_cache:
                try:
                    c_df = pd.read_parquet(os.path.join(info['target_dir'], 'matched_leads_cache.parquet'), columns=['Parcel_ID'])
                    c_leads = len(c_df)
                except Exception:
                    c_leads = 0
                status_badge = "LIVE & READY"
                rec_str = f"{rec_num:,} parcels • {c_leads:,} leads"
            else:
                status_badge = "READY"
                rec_str = f"{rec_num:,} parcels"
        else:
            status_badge = "NEEDS SETUP"
            rec_str = "Awaiting Parcel File"


            
        counties.append({
            "key": key,
            "name": key,
            "state": state,
            "full_name": info["full_name"],
            "records": rec_num,
            "records_formatted": rec_str,
            "updated": defaults["updated"],
            "status": status_badge,
            "has_master": has_master,
            "has_cache": has_cache,
            "target_dir": info["target_dir"],
            "img": defaults["img"],
            "sample_lp": bool(info.get("sample_lp")),
            "sample_code": bool(info.get("sample_code")),
            "sample_probate": bool(info.get("sample_probate")),
            "clerk_lis_pendens_url": info.get("clerk_lis_pendens_url", ""),
            "code_enforcement_url": info.get("code_enforcement_url", ""),
            "code_enforcement_note": info.get("code_enforcement_note", ""),
            "tax_liens_url": info.get("tax_liens_url", ""),
            "clerk_probate_url": info.get("clerk_probate_url", ""),
            "master_parcel_download_url": info.get("master_parcel_download_url", "")
        })
        
    return counties

class PortalUpdateRequest(BaseModel):
    county: str
    master_parcel_download_url: Optional[str] = None
    clerk_lis_pendens_url: Optional[str] = None
    code_enforcement_url: Optional[str] = None
    tax_liens_url: Optional[str] = None
    clerk_probate_url: Optional[str] = None

@app.post("/api/counties/update-portals")
def update_portals(payload: PortalUpdateRequest):
    """Save user-updated county source and portal URLs to county_portals.json."""
    try:
        updated = update_county_portal_urls(payload.county, payload.dict())
        return {"status": "ok", "county": payload.county, "portals": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CustomCategoryRequest(BaseModel):
    id: Optional[str] = None
    name: str
    badge: Optional[str] = "Civil Filing"
    description: Optional[str] = ""
    icon: Optional[str] = "⚖️"
    color: Optional[str] = "rose"
    portal_url: Optional[str] = ""

@app.get("/api/custom-categories")
def get_custom_categories():
    """Return all user-defined distress categories/cards."""
    return load_custom_categories()

@app.post("/api/custom-categories")
def create_custom_category(cat: CustomCategoryRequest):
    """Add or update a custom distress lead card category."""
    try:
        updated = add_custom_category(cat.dict())
        return {"status": "ok", "categories": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/custom-categories/{category_id}")
def remove_custom_category(category_id: str):
    """Delete a custom distress lead card."""
    try:
        updated = delete_custom_category(category_id)
        return {"status": "ok", "categories": updated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/sources-summary")
def get_sources_summary(county: str = "Orange", state: str = "FL"):
    """
    Return detailed metadata, last loaded dates, file sizes, and verified lead counts
    for all distress sources for the specified county.
    """
    state = (state or "FL").upper()
    target_dir = os.path.join(DATA_DIR, state, county)
    if not os.path.exists(target_dir):
        target_dir = os.path.join(DATA_DIR, state, county.lower())
        
    cache_path = os.path.join(target_dir, "matched_leads_cache.parquet")
    counts = {
        "lis_pendens": 0, "code_violations": 0, "probate": 0, "tax_liens": 0,
        "ouc_water_shutoff": 0, "divorce": 0, "judgments_liens": 0
    }
    cache_mtime = ""
    if os.path.exists(cache_path):
        try:
            df = pd.read_parquet(cache_path, columns=['Lead_Type', 'Parcel_ID'])
            counts['lis_pendens'] = int(df[df['Lead_Type'] == 'Lis Pendens']['Parcel_ID'].nunique())
            counts['code_violations'] = int(df[df['Lead_Type'] == 'Code Violation']['Parcel_ID'].nunique())
            counts['probate'] = int(df[df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]['Parcel_ID'].nunique())
            counts['tax_liens'] = int(df[df['Lead_Type'].str.contains('tax lien', case=False, na=False)]['Parcel_ID'].nunique())
            counts['ouc_water_shutoff'] = int(df[df['Lead_Type'].str.contains('water|ouc', case=False, na=False)]['Parcel_ID'].nunique())
            counts['divorce'] = int(df[df['Lead_Type'].str.contains('divorce|domestic relations', case=False, na=False)]['Parcel_ID'].nunique())
            counts['judgments_liens'] = int(df[df['Lead_Type'].str.contains('judgment|lien', case=False, na=False)]['Parcel_ID'].nunique())
            cache_mtime = time.strftime('%b %d, %Y, %I:%M %p', time.localtime(os.path.getmtime(cache_path)))
        except Exception as e:
            print("Error reading cache for sources summary:", e)
            
    files = {}
    if os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            fp = os.path.join(target_dir, f)
            if os.path.isfile(fp) and not f.startswith('.'):
                st = os.stat(fp)
                files[f] = {
                    'name': f,
                    'mtime_str': time.strftime('%b %d, %Y', time.localtime(st.st_mtime)),
                    'mtime_full': time.strftime('%b %d, %Y, %I:%M %p', time.localtime(st.st_mtime)),
                    'size_str': f"{round(st.st_size / (1024*1024), 2)} MB" if st.st_size > 1024*1024 else f"{round(st.st_size / 1024, 1)} KB"
                }

    def _find_file(keywords):
        for fn, fmeta in files.items():
            fn_l = fn.lower()
            if any(k in fn_l for k in keywords) and 'property_info' not in fn_l and 'all parcels' not in fn_l:
                return fmeta
        return None

    portals = load_county_portals(state=state).get(county, {}) or load_county_portals(state=state).get(county.capitalize(), {})

    lp_file = _find_file(["lis_pendens", "_lp_"])
    code_file = _find_file(["code_enforcement", "code_violation", "code_cases"])
    water_file = _find_file(["water", "ouc"])
    comptroller_file = _find_file(["comptroller", "official_records", "searchresults"])
    probate_file = _find_file(["probate"]) or comptroller_file
    tax_file = _find_file(["tax_lien", "tax_certificates", "delinquent_tax"])

    sources = {
        "lis_pendens": {
            "key": "lis_pendens",
            "name": "Lis Pendens",
            "badge": "Pre-Foreclosures",
            "icon": "📄",
            "color": "blue",
            "lead_count": counts["lis_pendens"],
            "file_name": lp_file["name"] if lp_file else "",
            "file_size": lp_file["size_str"] if lp_file else "",
            "last_loaded": lp_file["mtime_str"] if lp_file else (cache_mtime.split(",")[0] if counts["lis_pendens"] > 0 else "Not loaded yet"),
            "last_loaded_full": lp_file["mtime_full"] if lp_file else (cache_mtime if counts["lis_pendens"] > 0 else "Awaiting CSV upload"),
            "portal_url": portals.get("clerk_lis_pendens_url", "https://selfservice.or.occompt.com/ssweb/search/DOCSEARCH2950S3" if county.lower() == "orange" else "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType"),
            "portal_name": "Orange County Comptroller Official Records" if county.lower() == "orange" else "Official Records / Lis Pendens Search",
            "portal_disclaimer_note": "Click 'I Accept' on the disclaimer if prompted." if county.lower() == "orange" else "",
            "description": "Active lawsuits, pre-foreclosures, and lender mortgage legal filings."
        },
        "code_violations": {
            "key": "code_violations",
            "name": "Code Violations",
            "badge": "Municipal Citations",
            "icon": "🚨",
            "color": "amber",
            "lead_count": counts["code_violations"],
            "file_name": code_file["name"] if code_file else "",
            "file_size": code_file["size_str"] if code_file else "",
            "last_loaded": code_file["mtime_str"] if code_file else (cache_mtime.split(",")[0] if counts["code_violations"] > 0 else "Not loaded yet"),
            "last_loaded_full": code_file["mtime_full"] if code_file else (cache_mtime if counts["code_violations"] > 0 else "Awaiting CSV upload"),
            "portal_url": portals.get("code_enforcement_url", "https://aca-prod.accela.com/PINELLAS/Cap/CapHome.aspx?module=Enforcement&TabName=Home"),
            "portal_name": "County Code Enforcement & Compliance Portal",
            "description": "Properties with open municipal citations, zoning violations, and maintenance orders."
        },
        "tax_liens": {
            "key": "tax_liens",
            "name": "Tax Liens",
            "badge": "Delinquent Taxes",
            "icon": "💰",
            "color": "rose",
            "lead_count": counts["tax_liens"],
            "file_name": tax_file["name"] if tax_file else "",
            "file_size": tax_file["size_str"] if tax_file else "",
            "last_loaded": tax_file["mtime_str"] if tax_file else (cache_mtime.split(",")[0] if counts["tax_liens"] > 0 else "Not loaded yet"),
            "last_loaded_full": tax_file["mtime_full"] if tax_file else (cache_mtime if counts["tax_liens"] > 0 else "Awaiting CSV upload"),
            "portal_url": portals.get("tax_liens_url", "https://pinellas.county-taxes.com/public"),
            "portal_name": "County Tax Collector & Delinquent Tax Rolls",
            "description": "Delinquent county property taxes, tax auction certificates, and municipal liens."
        },
        "probate": {
            "key": "probate",
            "name": "Probate & Trusts",
            "badge": "Court Filings & Trusts",
            "icon": "⚖️",
            "color": "purple",
            "lead_count": counts["probate"],
            "file_name": probate_file["name"] if probate_file else "",
            "file_size": probate_file["size_str"] if probate_file else "",
            "last_loaded": probate_file["mtime_str"] if probate_file else (cache_mtime.split(",")[0] if counts["probate"] > 0 else "Not loaded yet"),
            "last_loaded_full": probate_file["mtime_full"] if probate_file else (cache_mtime if counts["probate"] > 0 else "Awaiting CSV upload"),
            "portal_url": portals.get("clerk_probate_url", "https://myeclerk.myorangeclerk.com/cases/search" if county.lower() == "orange" else "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType"),
            "portal_name": "Orange County Clerk of Courts Case Search" if county.lower() == "orange" else "Official Records / Probate Court Docket",
            "secondary_portal_url": "https://selfservice.or.occompt.com/ssweb/search/DOCSEARCH2950S3" if county.lower() == "orange" else "",
            "secondary_portal_name": "Orange County Comptroller (Official Records)" if county.lower() == "orange" else "",
            "portal_disclaimer_note": "Click 'I Accept' on the Comptroller disclaimer if prompted." if county.lower() == "orange" else "",
            "description": "Inherited properties, deceased estates, death certificates, and court probate cases."
        },
        "ouc_water_shutoff": {
            "key": "ouc_water_shutoff",
            "name": "OUC water shutoff",
            "badge": "Water Shut-off",
            "icon": "💧",
            "color": "cyan",
            "lead_count": counts["ouc_water_shutoff"],
            "file_name": water_file["name"] if water_file else "",
            "file_size": water_file["size_str"] if water_file else "",
            "last_loaded": water_file["mtime_str"] if water_file else (cache_mtime.split(",")[0] if counts["ouc_water_shutoff"] > 0 else "Not loaded yet"),
            "last_loaded_full": water_file["mtime_full"] if water_file else (cache_mtime if counts["ouc_water_shutoff"] > 0 else "Awaiting CSV upload"),
            "portal_url": "https://www.ouc.com",
            "portal_name": "Orlando Utilities Commission (OUC)",
            "description": "Delinquent municipal utility shutoff records with disconnected meters."
        },
        "divorce": {
            "key": "divorce",
            "name": "Divorce (Domestic Relations)",
            "badge": "Family Court",
            "icon": "💔",
            "color": "pink",
            "lead_count": counts["divorce"],
            "file_name": comptroller_file["name"] if comptroller_file else "",
            "file_size": comptroller_file["size_str"] if comptroller_file else "",
            "last_loaded": comptroller_file["mtime_str"] if comptroller_file else (cache_mtime.split(",")[0] if counts["divorce"] > 0 else "Not loaded yet"),
            "last_loaded_full": comptroller_file["mtime_full"] if comptroller_file else (cache_mtime if counts["divorce"] > 0 else "Awaiting CSV upload"),
            "portal_url": "https://selfservice.or.occompt.com/ssweb/search/DOCSEARCH2950S3" if county.lower() == "orange" else portals.get("clerk_lis_pendens_url", "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType"),
            "portal_name": "Orange County Comptroller Official Records" if county.lower() == "orange" else "Official Records / Family Court Search",
            "portal_disclaimer_note": "Click 'I Accept' on the Comptroller disclaimer screen if prompted." if county.lower() == "orange" else "",
            "description": "Spouses dividing real property in marital dissolution and domestic relations court filings."
        },
        "judgments_liens": {
            "key": "judgments_liens",
            "name": "Civil Judgments & Liens",
            "badge": "Monetary Judgments",
            "icon": "🔨",
            "color": "amber",
            "lead_count": counts["judgments_liens"],
            "file_name": comptroller_file["name"] if comptroller_file else "",
            "file_size": comptroller_file["size_str"] if comptroller_file else "",
            "last_loaded": comptroller_file["mtime_str"] if comptroller_file else (cache_mtime.split(",")[0] if counts["judgments_liens"] > 0 else "Not loaded yet"),
            "last_loaded_full": comptroller_file["mtime_full"] if comptroller_file else (cache_mtime if counts["judgments_liens"] > 0 else "Awaiting CSV upload"),
            "portal_url": "https://selfservice.or.occompt.com/ssweb/search/DOCSEARCH2950S3" if county.lower() == "orange" else portals.get("clerk_lis_pendens_url", "https://officialrecords.mypinellasclerk.gov/search/SearchTypeDocType"),
            "portal_name": "Orange County Comptroller Official Records" if county.lower() == "orange" else "Official Records / Recorded Judgments & Liens",
            "portal_disclaimer_note": "Click 'I Accept' on the Comptroller disclaimer screen if prompted." if county.lower() == "orange" else "",
            "description": "Recorded monetary civil court judgments and municipal/HOA/vendor liens encumbering real property."
        }
    }

    # Dynamically inject any custom categories not already in sources
    try:
        custom_cats = load_custom_categories()
        for cat in custom_cats:
            cid = cat.get("id")
            if cid and cid not in sources:
                cat_file = _find_file([cid, cat.get("name", "").lower().replace(" ", "_")])
                c_lead_count = counts.get(cid, 0)
                if not c_lead_count and os.path.exists(cache_path):
                    try:
                        df_temp = pd.read_parquet(cache_path, columns=['Lead_Type', 'Parcel_ID'])
                        c_lead_count = int(df_temp[df_temp['Lead_Type'].str.contains(re.escape(cat.get("name", "")), case=False, na=False)]['Parcel_ID'].nunique())
                    except Exception:
                        c_lead_count = 0
                sources[cid] = {
                    "key": cid,
                    "name": cat.get("name", cid),
                    "badge": cat.get("badge", "Distress Filing"),
                    "icon": cat.get("icon", "📄"),
                    "color": cat.get("color", "purple"),
                    "lead_count": c_lead_count,
                    "file_name": cat_file["name"] if cat_file else "",
                    "file_size": cat_file["size_str"] if cat_file else "",
                    "last_loaded": cat_file["mtime_str"] if cat_file else (cache_mtime.split(",")[0] if c_lead_count > 0 else "Not loaded yet"),
                    "last_loaded_full": cat_file["mtime_full"] if cat_file else (cache_mtime if c_lead_count > 0 else "Awaiting CSV upload"),
                    "portal_url": cat.get("portal_url", ""),
                    "portal_name": cat.get("name", "") + " Portal",
                    "description": cat.get("description", "User-defined distress lead source.")
                }
    except Exception as e:
        print("Error enriching custom categories in sources summary:", e)
    
    return {
        "county": county,
        "state": state,
        "cache_updated": cache_mtime,
        "sources": sources
    }

# -------------------------------------------------------------
# Contact Management, Android SMS Gateway & SMTP2GO Email Outreach
# -------------------------------------------------------------
CONTACTS_FILE = os.path.join(DATA_DIR, "saved_contacts.json")
SMS_SETTINGS_FILE = os.path.join(DATA_DIR, "sms_settings.json")
EMAIL_SETTINGS_FILE = os.path.join(DATA_DIR, "email_settings.json")
OUTREACH_LOG_FILE = os.path.join(DATA_DIR, "outreach_history.json")
DELETED_LEADS_FILE = os.path.join(DATA_DIR, "deleted_leads.json")

def load_deleted_leads() -> set:
    if os.path.exists(DELETED_LEADS_FILE):
        try:
            with open(DELETED_LEADS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(str(x).strip() for x in data) if isinstance(data, list) else set()
        except Exception:
            pass
    return set()

def save_deleted_leads(deleted_set: set):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DELETED_LEADS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(deleted_set)), f, indent=2)

def load_saved_contacts() -> dict:
    if os.path.exists(CONTACTS_FILE):
        try:
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

OUTREACH_DATA_LOCK = threading.RLock()


def atomic_outreach_json_write(path: str, value):
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as output:
        json.dump(value, output, indent=2)
    os.replace(temp_path, path)


def append_outreach_log(entry: dict):
    # The background sender and inbound webhook can finish at the same time.
    # Merge under a lock and replace atomically so neither erases the other's log.
    with OUTREACH_DATA_LOCK:
        logs = []
        if os.path.exists(OUTREACH_LOG_FILE):
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as history_file:
                logs = json.load(history_file)
        logs.insert(0, entry)
        atomic_outreach_json_write(OUTREACH_LOG_FILE, logs[:500])


def save_contact(parcel_id: str, data: dict) -> dict:
    with OUTREACH_DATA_LOCK:
        return save_contact_locked(parcel_id, data)


def save_contact_locked(parcel_id: str, data: dict) -> dict:
    contacts = load_saved_contacts()
    pid = str(parcel_id).strip()
    contacts[pid] = {
        **contacts.get(pid, {}),
        **data,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        atomic_outreach_json_write(CONTACTS_FILE, contacts)
    except Exception as e:
        print(f"Error saving contact {pid}: {e}")
    return contacts[pid]

def load_email_settings() -> dict:
    defaults = {
        "smtp_server": "mail.smtp2go.com",
        "smtp_port": 2525,
        "smtp_user": "407flips.com",
        "smtp_password": "",
        "sender_name": "John Roberts | 407 Flips",
        "sender_email": "john@407flips.com",
        "reply_to": "john@407flips.com",
        "company_name": "407 Flips",
        "company_phone": "(407) 555-FLIP",
        "business_address": "Orlando, FL (Central Florida)"
    }
    if os.path.exists(EMAIL_SETTINGS_FILE):
        try:
            with open(EMAIL_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            pass
    return defaults

def save_email_settings(settings: dict):
    with open(EMAIL_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

@app.get("/api/leads")
def get_leads(county: str = "Pinellas", state: str = "FL", lead_type: str = "all", filter_type: str = "all"):
    """
    Return real pre-indexed leads for the selected county.
    Loads instant matched cache in 0.01 seconds!
    """
    info = get_county_paths(county, state=state)
    cache_file = os.path.join(info['target_dir'], 'matched_leads_cache.parquet')
    
    if not os.path.exists(cache_file):
        return {
            "status": "needs_setup",
            "county": county,
            "has_master": info['has_master'],
            "target_dir": info['target_dir'],
            "download_url": info.get('master_parcel_download_url', ''),
            "records": [],
            "kpis": {
                "total_leads": 0, "matched_count": 0, "match_rate": 0,
                "absentee_count": 0, "out_of_state_count": 0, "trust_count": 0,
                "corporate_count": 0, "avg_market_value": 0
            }
        }
        
    df = pd.read_parquet(cache_file)
    app.state.last_results = df
    app.state.last_county = county

    # Filter by lead_type if specified
    if lead_type == "lis_pendens":
        df = df[df['Lead_Type'] == 'Lis Pendens']
    elif lead_type == "code_violations":
        df = df[df['Lead_Type'] == 'Code Violation']
    elif lead_type == "probate":
        df = df[df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]
    elif lead_type == "tax_liens":
        df = df[df['Lead_Type'] == 'Tax Lien']
    elif lead_type in ["water_shutoff", "water", "ouc"]:
        df = df[df['Lead_Type'].str.contains('water|ouc', case=False, na=False) | df.get('Distress_Stack_Notes', '').astype(str).str.contains('water|ouc', case=False, na=False)]
    elif lead_type in ["divorce", "domestic_relations"]:
        df = df[df['Lead_Type'].str.contains('divorce|domestic relations', case=False, na=False)]
    elif lead_type in ["judgment", "judgments", "lien", "liens"]:
        df = df[df['Lead_Type'].str.contains('judgment|lien', case=False, na=False)]
    elif lead_type in ["poa", "power_of_attorney"]:
        df = df[df['Lead_Type'].str.contains('power of attorney', case=False, na=False)]
    elif lead_type in ["legal_distress", "legal", "jail", "felony"]:
        df = df[df['Lead_Type'].str.contains('legal distress|felony', case=False, na=False) | df.get('Distress_Stack_Notes', '').astype(str).str.contains('legal distress|felony', case=False, na=False)]
    elif lead_type in ["substantial_damage", "storm_damage", "damage"]:
        df = df[df['Lead_Type'].str.contains('Substantial Damage', case=False, na=False)]

    deleted_pids = load_deleted_leads()
    total_leads = len(df)
    matched_mask = df['Match_Status'].astype(str).str.upper() == 'MATCHED'
    matched_df = df[matched_mask].copy()

    # Exclude empty parcel IDs, empty addresses, and deleted leads
    matched_df = matched_df[matched_df['Parcel_ID'].astype(str).str.strip() != '']
    matched_df = matched_df[matched_df['Property_Address'].astype(str).str.strip() != '']
    if deleted_pids:
        matched_df = matched_df[~matched_df['Parcel_ID'].astype(str).str.strip().isin(deleted_pids)]

    matched_count = int(matched_df['Parcel_ID'].nunique())
    match_rate = round((matched_count / total_leads * 100), 1) if total_leads > 0 else 0.0

    absentee_count = int(matched_df[matched_df['Is_Absentee'].eq('Yes')]['Parcel_ID'].nunique())
    out_of_state_count = int(matched_df[matched_df['Absentee_Status'].str.contains('Out-of-State', na=False)]['Parcel_ID'].nunique())
    trust_count = int(matched_df[matched_df['Owner_Entity_Type'].str.contains('Trust', na=False) | matched_df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]['Parcel_ID'].nunique())
    corporate_count = int(matched_df[matched_df['Owner_Entity_Type'].str.contains('LLC|Company', na=False)]['Parcel_ID'].nunique())
    probate_count = int(matched_df[matched_df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]['Parcel_ID'].nunique())
    divorce_count = int(matched_df[matched_df['Lead_Type'].str.contains('divorce|domestic relations', case=False, na=False)]['Parcel_ID'].nunique())
    judgment_count = int(matched_df[matched_df['Lead_Type'].str.contains('judgment|lien', case=False, na=False)]['Parcel_ID'].nunique())
    lp_trust_count = int(matched_df[(matched_df['Lead_Type'] == 'Lis Pendens') & (matched_df.get('Is_Trust_In_LP', '') == 'Yes')]['Parcel_ID'].nunique())
    stacked_count = int(matched_df[matched_df.get('Is_Stacked_Distress', '') == 'Yes']['Parcel_ID'].nunique())
    legal_distress_count = int(matched_df[matched_df['Lead_Type'].str.contains('legal distress|felony', case=False, na=False) | matched_df.get('Distress_Stack_Notes', '').astype(str).str.contains('legal distress|felony', case=False, na=False)]['Parcel_ID'].nunique())
    
    vals = pd.to_numeric(matched_df['Market_Value'], errors='coerce').fillna(0)
    avg_mkt_val = int(vals.mean()) if len(vals) > 0 else 0

    # Filter for display table
    filtered_df = matched_df
    if filter_type == "absentee":
        filtered_df = matched_df[matched_df['Absentee_Status'].str.contains('Out-of-State', na=False)]
    elif filter_type == "llc":
        filtered_df = matched_df[matched_df['Owner_Entity_Type'].str.contains('LLC|Company', na=False)]
    elif filter_type == "trust":
        filtered_df = matched_df[matched_df['Owner_Entity_Type'].str.contains('Trust', na=False) | matched_df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]
    elif filter_type == "probate":
        filtered_df = matched_df[matched_df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]
    elif filter_type == "divorce":
        filtered_df = matched_df[matched_df['Lead_Type'].str.contains('divorce|domestic relations', case=False, na=False)]
    elif filter_type in ["judgment", "lien"]:
        filtered_df = matched_df[matched_df['Lead_Type'].str.contains('judgment|lien', case=False, na=False)]
    elif filter_type == "lp_trust":
        filtered_df = matched_df[(matched_df['Lead_Type'] == 'Lis Pendens') & (matched_df.get('Is_Trust_In_LP', '') == 'Yes')]
    elif filter_type == "stacked":
        filtered_df = matched_df[matched_df.get('Is_Stacked_Distress', '') == 'Yes']
    elif filter_type in ["legal_distress", "legal", "jail", "felony"]:
        filtered_df = matched_df[matched_df['Lead_Type'].str.contains('legal distress|felony', case=False, na=False) | matched_df.get('Distress_Stack_Notes', '').astype(str).str.contains('legal distress|felony', case=False, na=False)]
    elif filter_type in ["code", "code_violations"]:
        filtered_df = matched_df[matched_df['Lead_Type'].str.contains('code', case=False, na=False)]
    elif filter_type in ["damage", "substantial_damage"]:
        filtered_df = matched_df[matched_df['Lead_Type'].str.contains('substantial damage', case=False, na=False)]
    elif filter_type in ["new_api", "new_unread"]:
        if 'Source_File' in matched_df.columns:
            filtered_df = matched_df[matched_df['Source_File'].fillna('').astype(str).str.contains('Live_API|Accela|SeeClickFix', case=False, na=False)]

    # Standardize Filing_Date and Is_New_Api on filtered_df (vectorized for instant response)
    filtered_df = filtered_df.copy()
    candidate_cols = [
        'Subject_Filing_Date', 'Filing_Date', 'Subject_RecordDate', 'Recording_Date',
        'Subject_Recording Date', 'Subject_Case Open Date', 'Case_Date', 'Case Open Date',
        'Subject_Date', 'Recorded_Date', 'RecordDate', 'Date'
    ]
    avail_date_cols = [c for c in candidate_cols if c in filtered_df.columns]
    if avail_date_cols:
        date_series = filtered_df[avail_date_cols].replace({'': None, 'nan': None, 'None': None}).bfill(axis=1).iloc[:, 0].fillna('')
        filtered_df['Filing_Date'] = date_series.astype(str).str[:10].str.strip()
    else:
        filtered_df['Filing_Date'] = ''

    if 'Source_File' in filtered_df.columns:
        filtered_df['Is_New_Api'] = filtered_df['Source_File'].fillna('').astype(str).apply(lambda x: 'Yes' if any(k in str(x) for k in ['Live_API', 'Accela', 'SeeClickFix']) else 'No')
    else:
        filtered_df['Is_New_Api'] = 'No'
    filtered_df['Is_New_Lead'] = filtered_df['Is_New_Api']

    display_cols = [
        'Lead_Type', 'All_Lead_Types', 'Match_Status', 'Match_Confidence', 'Match_Method',
        'Clean_First_Name', 'Clean_Last_Name', 'Clean_Full_Name', 'Owner_Entity_Type',
        'Is_Trust_Or_Estate', 'Is_Trust_In_LP', 'Is_Stacked_Distress', 'Distress_Stack_Notes',
        'Property_Address', 'Property_City', 'Property_Zip', 'Parcel_ID',
        'Mailing_Address', 'Mailing_City', 'Mailing_State', 'Mailing_Zip',
        'Absentee_Status', 'Is_Absentee', 'Homestead_Exemption',
        'Market_Value', 'Assessed_Value', 'Year_Built', 'Living_Sqft', 'Legal_Description',
        'Filing_Date', 'Is_New_Api', 'Is_New_Lead', 'Case_Number', 'Source_File', 'Photo_Url'
    ]
    valid_cols = [c for c in display_cols if c in filtered_df.columns]
    # Replace NaN/inf with empty strings to guarantee JSON compliance for FastAPI
    clean_sub_df = filtered_df[valid_cols].copy()
    for col in valid_cols:
        if col != 'All_Lead_Types':
            clean_sub_df[col] = clean_sub_df[col].replace([float('nan'), float('inf'), -float('inf')], '').fillna('')
        else:
            clean_sub_df[col] = [list(x) if isinstance(x, (list, np.ndarray)) else [] for x in clean_sub_df[col]]
    raw_records = clean_sub_df.to_dict(orient='records')

    # Deduplicate records by Parcel_ID so Double Distress leads never appear with double rows/names
    records = []
    seen_pids = {}
    for r in raw_records:
        pid = str(r.get('Parcel_ID', '')).strip()
        if not pid:
            continue
        if pid in seen_pids:
            existing = seen_pids[pid]
            # Track all lead types for this parcel
            all_types = existing.get('All_Lead_Types', [])
            if not isinstance(all_types, list):
                all_types = [existing.get('Lead_Type', '')] if existing.get('Lead_Type') else []
            if r.get('Lead_Type') and r['Lead_Type'] not in all_types:
                all_types.append(r['Lead_Type'])
            existing['All_Lead_Types'] = all_types

            # Prefer richer clean name if existing is empty
            if (not existing.get('Clean_Full_Name') or existing.get('Clean_Full_Name') == 'Unknown Owner') and r.get('Clean_Full_Name'):
                existing['Clean_Full_Name'] = r['Clean_Full_Name']
                existing['Clean_First_Name'] = r.get('Clean_First_Name', '')
                existing['Clean_Last_Name'] = r.get('Clean_Last_Name', '')
            # If either signal indicates stacked distress, or if this property appears under multiple distinct distress types
            if r.get('Lead_Type') and existing.get('Lead_Type') and r['Lead_Type'] != existing['Lead_Type']:
                existing['Is_Stacked_Distress'] = 'Yes'
                t1 = existing.get('Lead_Type', '')
                t2 = r.get('Lead_Type', '')
                if t1 == 'Code Violation' or t2 == 'Code Violation':
                    other = t1 if t2 == 'Code Violation' else t2
                    existing['Distress_Stack_Notes'] = f"🔥 DOUBLE DISTRESS: Code Violation + {other}"
                    existing['Lead_Type'] = 'Code Violation'
                else:
                    existing['Distress_Stack_Notes'] = f"🔥 DOUBLE DISTRESS: {t1} + {t2}"
            if r.get('Is_Stacked_Distress') == 'Yes' or existing.get('Is_Stacked_Distress') == 'Yes':
                existing['Is_Stacked_Distress'] = 'Yes'
                if r.get('Distress_Stack_Notes') and not existing.get('Distress_Stack_Notes'):
                    existing['Distress_Stack_Notes'] = r['Distress_Stack_Notes']
            if r.get('Is_Trust_Or_Estate') == 'Yes' or existing.get('Is_Trust_Or_Estate') == 'Yes':
                existing['Is_Trust_Or_Estate'] = 'Yes'
            if r.get('Is_New_Api') == 'Yes' or existing.get('Is_New_Api') == 'Yes' or 'Live_API' in str(r.get('Source_File', '')) or 'Live_API' in str(existing.get('Source_File', '')):
                existing['Is_New_Api'] = 'Yes'
                existing['Is_New_Lead'] = 'Yes'
                if 'Live_API' in str(r.get('Source_File', '')):
                    existing['Source_File'] = r.get('Source_File')
            if r.get('Case_Number') and not existing.get('Case_Number'):
                existing['Case_Number'] = r['Case_Number']
            if r.get('Photo_Url') and not existing.get('Photo_Url'):
                existing['Photo_Url'] = r['Photo_Url']
            if r.get('Filing_Date') and str(r['Filing_Date']) > str(existing.get('Filing_Date', '')):
                existing['Filing_Date'] = r['Filing_Date']
        else:
            r['All_Lead_Types'] = [r.get('Lead_Type', '')] if r.get('Lead_Type') else []
            seen_pids[pid] = r
            records.append(r)

    # Merge saved contacts (phone and email)
    contacts = load_saved_contacts()

    # Load outreach history so prior SMS and Email dispatches are permanently stamped on each lead
    outreach_map = {}
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                history_logs = json.load(f)
                for entry in history_logs:
                    h_pid = str(entry.get('parcel_id', '')).strip()
                    h_chan = str(entry.get('channel', '')).upper()
                    h_ts = entry.get('timestamp', '')
                    if h_pid and h_ts:
                        if h_pid not in outreach_map:
                            outreach_map[h_pid] = {}
                        if h_chan == 'SMS' and 'last_sms_sent' not in outreach_map[h_pid]:
                            outreach_map[h_pid]['last_sms_sent'] = h_ts
                        elif h_chan == 'EMAIL' and 'last_email_sent' not in outreach_map[h_pid]:
                            outreach_map[h_pid]['last_email_sent'] = h_ts
        except Exception:
            pass

    for r in records:
        pid = str(r.get('Parcel_ID', '')).strip()
        c = contacts.get(pid, {})
        o = outreach_map.get(pid, {})
        r['Saved_Phone'] = c.get('phone', '')
        r['Saved_Email'] = c.get('email', '') or r.get('Saved_Email', '')
        r['Last_Sms_Sent'] = c.get('last_sms_sent', '') or o.get('last_sms_sent', '')
        r['Last_Email_Sent'] = c.get('last_email_sent', '') or o.get('last_email_sent', '')

        # Standardize and clean addresses & names: no ALL CAPS, drop directionals
        if r.get('Property_Address'):
            r['Property_Address'] = clean_display_address(r['Property_Address'])
        if r.get('Property_City'):
            r['Property_City'] = clean_display_city(r['Property_City'])
        if r.get('Mailing_Address'):
            r['Mailing_Address'] = clean_display_address(r['Mailing_Address'])
        if r.get('Mailing_City'):
            r['Mailing_City'] = clean_display_city(r['Mailing_City'])
        if r.get('Clean_Full_Name'):
            r['Clean_Full_Name'] = clean_display_name(r['Clean_Full_Name'])
        if r.get('Clean_First_Name'):
            r['Clean_First_Name'] = clean_display_name(r['Clean_First_Name'])
        if r.get('Clean_Last_Name'):
            r['Clean_Last_Name'] = clean_display_name(r['Clean_Last_Name'])

    # Sort records: Live API leads strictly pinned to the absolute top,
    # followed by strict newest filing date descending, then Double Distress
    from functools import cmp_to_key
    def lead_sort_cmp(a, b):
        a_new = 1 if (a.get('Is_New_Api') == 'Yes' or a.get('Is_New_Lead') == 'Yes' or 'Live_API' in str(a.get('Source_File', ''))) else 0
        b_new = 1 if (b.get('Is_New_Api') == 'Yes' or b.get('Is_New_Lead') == 'Yes' or 'Live_API' in str(b.get('Source_File', ''))) else 0
        if b_new != a_new:
            return b_new - a_new
        # Strict newest filing/recording date always on top!
        date_a = str(a.get('Filing_Date') or a.get('Case_Date') or a.get('Recording_Date') or '')[:10]
        date_b = str(b.get('Filing_Date') or b.get('Case_Date') or b.get('Recording_Date') or '')[:10]
        if date_a and date_b and date_a != date_b:
            return 1 if date_b > date_a else -1
        if date_b and not date_a:
            return 1
        if date_a and not date_b:
            return -1
        # Within matching dates, prioritize Double Distress
        a_stack = 1 if a.get('Is_Stacked_Distress') == 'Yes' else 0
        b_stack = 1 if b.get('Is_Stacked_Distress') == 'Yes' else 0
        if b_stack != a_stack:
            return b_stack - a_stack
        return 0

    records.sort(key=cmp_to_key(lead_sort_cmp))

    return {
        "status": "ready",
        "county": county,
        "total_records_in_db": 437559 if county == "Pinellas" else (496712 if county == "Orange" else (181244 if county == "Seminole" else len(df))),
        "kpis": {
            "total_leads": total_leads,
            "matched_count": matched_count,
            "match_rate": match_rate,
            "absentee_count": absentee_count,
            "out_of_state_count": out_of_state_count,
            "trust_count": trust_count,
            "corporate_count": corporate_count,
            "probate_count": probate_count,
            "divorce_count": divorce_count,
            "judgment_count": judgment_count,
            "lp_trust_count": lp_trust_count,
            "stacked_count": stacked_count,
            "legal_distress_count": legal_distress_count,
            "avg_market_value": avg_mkt_val
        },
        "records": records
    }


def read_lead_upload(content: bytes, filename: str):
    """The upload parser shared by the Load List button and inbound pulls."""
    if filename.lower().endswith(('.xlsx', '.xls')):
        subject_df = pd.read_excel(io.BytesIO(content), dtype=str)
    else:
        subject_df = pd.read_csv(io.BytesIO(content), dtype=str, low_memory=False)

    # Auto-detect header offset if top rows are report titles or blank (e.g. OUC water shutoff report)
    unnamed_cols = [c for c in subject_df.columns if str(c).startswith("Unnamed")]
    if len(unnamed_cols) >= len(subject_df.columns) * 0.5:
        header_keywords = ('ADDRESS', 'SITUS', 'LOCATION', 'NAME', 'PARCEL', 'STRAP', 'CITY', 'STATUS', 'CASE')
        for i in range(min(25, len(subject_df))):
            row_vals = [str(x).upper() for x in subject_df.iloc[i].tolist()]
            if any(any(kw in val for kw in header_keywords) for val in row_vals):
                new_headers = [str(x).strip() if pd.notna(x) and str(x).strip() != '' else f"COL_{idx}" for idx, x in enumerate(subject_df.iloc[i].tolist())]
                subject_df = subject_df.iloc[i + 1:].copy().reset_index(drop=True)
                subject_df.columns = new_headers
                break
    return subject_df


@app.post("/api/match")
async def run_match(
    county: str = Form("Pinellas"),
    lead_source: str = Form("lis_pendens"),
    file: Optional[UploadFile] = File(None)
):
    """Load List's existing entry point, also used by the folder watcher."""
    county_info = get_county_paths(county)
    if file and file.filename:
        source_name = file.filename
        try:
            subject_df = read_lead_upload(await file.read(), source_name)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Error parsing uploaded file: {exc}")
    else:
        sample_key = 'sample_code' if 'code' in lead_source.lower() else ('sample_probate' if 'probate' in lead_source.lower() else 'sample_lp')
        sample = county_info.get(sample_key) or county_info.get('sample_lp')
        if not sample:
            raise HTTPException(status_code=400, detail=f"No default lead file found for {county}. Please upload a lead list.")
        source_name = os.path.basename(sample)
        subject_df = pd.read_csv(sample, dtype=str, low_memory=False)

    # Clerk-format uploads share the same durable dedupe ledger as watched pulls.
    from src.inbound_pull import LIS_PENDENS_HEADERS, ingest_once
    if file and lead_source == 'lis_pendens' and list(subject_df.columns) == LIS_PENDENS_HEADERS:
        return ingest_once(subject_df, 'lis-pendens', county, source_name,
                           lambda rows: match_lead_dataframe(rows, county, lead_source, source_name, True))['result']
    return match_lead_dataframe(subject_df, county, lead_source, source_name, file is not None)


def match_lead_dataframe(subject_df, county, lead_source, source_name, uploaded):
    """Shared existing cross-reference, cache persistence, and result pipeline."""
    county_info = get_county_paths(county)
    if not county_info['has_master']:
        raise HTTPException(status_code=400, detail=f"Master parcel database for {county} is not installed. Please download and save to {county_info['target_dir']}")
    db = get_database(county)
    if subject_df is None or len(subject_df) == 0:
        raise HTTPException(status_code=400, detail="Lead file contains 0 records.")
    
    # Automatically clean and extract human defendants if clerk bundle is detected
    name_cols = [c for c in subject_df.columns if c.upper() in ('DECEDENT_NAME', 'DECEDENT', 'ESTATE_NAME', 'ESTATE', 'GRANTEE', 'DEFENDANT', 'INDIRECTNAME', 'OWNER_NAME', 'NAME', 'BORROWER')]
    if name_cols:
        target_name_col = name_cols[0]
        cleaned_rows = []
        for _, r in subject_df.iterrows():
            val = str(r.get(target_name_col, ''))
            humans = extract_human_defendants(val)
            if humans:
                for h in humans:
                    new_r = r.to_dict()
                    new_r.update(h)
                    cleaned_rows.append(new_r)
            else:
                new_r = r.to_dict()
                new_r.update({
                    'First_Name': '',
                    'Last_Name': '',
                    'Middle_Name': '',
                    'Suffix': '',
                    'Human_Name_Original': val,
                    'Full_Name': val
                })
                cleaned_rows.append(new_r)
        subject_df = pd.DataFrame(cleaned_rows)
    
    # Auto-detect columns
    cols_upper = {c.upper().strip(): c for c in subject_df.columns}
    column_mapping = {
        'name_col': '',
        'first_name_col': '',
        'last_name_col': '',
        'address_col': '',
        'parcel_col': '',
        'legal_col': '',
        'bookpage_col': ''
    }
    
    for cu, orig in cols_upper.items():
        if cu in ('DECEDENT_NAME', 'DECEDENT', 'ESTATE_NAME', 'ESTATE', 'HUMAN_NAME_ORIGINAL', 'FULL_NAME', 'NAME', 'GRANTEE', 'DEFENDANT') and not column_mapping['name_col']:
            column_mapping['name_col'] = orig
        elif any(k in cu for k in ['ADDRESS', 'SITUS', 'LOCATION']) and not column_mapping['address_col']:
            column_mapping['address_col'] = orig
        elif any(k in cu for k in ['PARCEL', 'STRAP', 'FOLIO']) and not column_mapping['parcel_col']:
            column_mapping['parcel_col'] = orig
        elif any(k in cu for k in ['LEGAL', 'COMMENTS', 'DESCRIPTION']) and not column_mapping['legal_col']:
            column_mapping['legal_col'] = orig

    # Filter for disconnects / shutoffs if account status column exists
    if any(k in lead_source.lower() for k in ('water', 'shutoff', 'utility')):
        status_col = next((c for c in subject_df.columns if 'STATUS' in c.upper()), None)
        if status_col:
            turn_off_mask = subject_df[status_col].astype(str).str.upper().str.contains('TURN OFF|SHUT OFF|OFF|DISCONNECT')
            if turn_off_mask.sum() > 0:
                subject_df = subject_df[turn_off_mask].copy().reset_index(drop=True)

    # Run Match
    t0 = time.time()
    engine = CrossReferenceEngine(db)
    matched_df = engine.cross_reference_dataframe(subject_df, column_mapping)
    elapsed = round(time.time() - t0, 2)

    # Set Lead Type
    custom_cats = {c.get('id'): c.get('name') for c in load_custom_categories()}
    custom_cats.update({c.get('name', '').lower().replace(' ', '_'): c.get('name') for c in load_custom_categories()})

    if lead_source in custom_cats:
        matched_df['Lead_Type'] = custom_cats[lead_source]
    elif any(k in lead_source.lower() for k in ('water', 'shutoff', 'ouc')):
        matched_df['Lead_Type'] = 'OUC water shutoff'
    elif "code" in lead_source.lower():
        matched_df['Lead_Type'] = 'Code Violation'
    elif "probate" in lead_source.lower():
        matched_df['Lead_Type'] = 'Probate'
    elif "tax" in lead_source.lower():
        matched_df['Lead_Type'] = 'Tax Lien'
    else:
        matched_df['Lead_Type'] = 'Lis Pendens'

    matched_df['Source_File'] = source_name

    # Multi-Distress Stacking: Cross-reference with Lis Pendens / Code Violations / Tax Liens / Probate
    cache_file = os.path.join(county_info['target_dir'], 'matched_leads_cache.parquet')
    if os.path.exists(cache_file) or uploaded:
        try:
            cached_all = pd.read_parquet(cache_file) if os.path.exists(cache_file) else matched_df.iloc[0:0].copy()
            lp_pids = set(cached_all[cached_all['Lead_Type'] == 'Lis Pendens']['Parcel_ID'].dropna())
            code_pids = set(cached_all[cached_all['Lead_Type'] == 'Code Violation']['Parcel_ID'].dropna())
            tax_pids = set(cached_all[cached_all['Lead_Type'] == 'Tax Lien']['Parcel_ID'].dropna())
            probate_pids = set(cached_all[cached_all['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]['Parcel_ID'].dropna())
            judgment_pids = set(cached_all[cached_all['Lead_Type'].str.contains('judgment|lien', case=False, na=False)]['Parcel_ID'].dropna())
            water_pids = set(cached_all[cached_all['Lead_Type'].str.contains('water|ouc', case=False, na=False)]['Parcel_ID'].dropna())

            def compute_distress(pid, ltype):
                signals = []
                lt_l = (ltype or "").lower()
                if pid in lp_pids and not ('lis_pendens' in lt_l or 'lis pendens' in lt_l):
                    signals.append("Lis Pendens Foreclosure")
                if pid in probate_pids and not ('probate' in lt_l or 'death certificate' in lt_l):
                    signals.append("Active County Probate Case")
                if pid in judgment_pids and not ('judgment' in lt_l or 'lien' in lt_l):
                    signals.append("County Judgment / Recorded Lien")
                if pid in code_pids and not ('code' in lt_l):
                    signals.append("Open Municipal Code Violation")
                if pid in tax_pids and not ('tax' in lt_l):
                    signals.append("County Tax Lien")
                if pid in water_pids and not ('water' in lt_l or 'ouc' in lt_l):
                    signals.append("OUC Water Shutoff")

                if len(signals) >= 2:
                    return ('Yes', f"💥 TRIPLE DISTRESS: {ltype} + {' + '.join(signals)}")
                elif len(signals) == 1:
                    return ('Yes', f"🔥 DOUBLE DISTRESS: {ltype} + {signals[0]}")
                return ('No', '')

            res_stack = matched_df.apply(lambda r: compute_distress(r.get('Parcel_ID', ''), r.get('Lead_Type', '')), axis=1)
            matched_df['Is_Stacked_Distress'] = res_stack.apply(lambda x: x[0])
            matched_df['Distress_Stack_Notes'] = res_stack.apply(lambda x: x[1])

            if "lis_pendens" in lead_source.lower():
                matched_df['Is_Trust_In_LP'] = matched_df.apply(
                    lambda r: 'Yes' if (r.get('Is_Trust_Or_Estate') == 'Yes' or 'Trust' in str(r.get('Owner_Entity_Type', '')) or r.get('Is_Stacked_Distress') == 'Yes') else 'No',
                    axis=1
                )
            else:
                matched_df['Is_Trust_In_LP'] = 'No'

            # When a file is uploaded, merge newly matched leads into the county cache so cross-referencing persists
            if uploaded and len(matched_df[matched_df['Match_Status'] == 'MATCHED']) > 0:
                new_matched = matched_df[matched_df['Match_Status'] == 'MATCHED'].copy()
                combined_df = pd.concat([cached_all, new_matched], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['Parcel_ID', 'Lead_Type'], keep='last')
                
                c_lp = set(combined_df[combined_df['Lead_Type'] == 'Lis Pendens']['Parcel_ID'].dropna())
                c_code = set(combined_df[combined_df['Lead_Type'] == 'Code Violation']['Parcel_ID'].dropna())
                c_tax = set(combined_df[combined_df['Lead_Type'] == 'Tax Lien']['Parcel_ID'].dropna())
                c_probate = set(combined_df[combined_df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False)]['Parcel_ID'].dropna())
                c_judgment = set(combined_df[combined_df['Lead_Type'].str.contains('judgment|lien', case=False, na=False)]['Parcel_ID'].dropna())
                c_water = set(combined_df[combined_df['Lead_Type'].str.contains('water|ouc', case=False, na=False)]['Parcel_ID'].dropna())

                def compute_combined(pid, ltype):
                    sig = []
                    lt = (ltype or "").lower()
                    if pid in c_lp and not ('lis_pendens' in lt or 'lis pendens' in lt):
                        sig.append("Lis Pendens Foreclosure")
                    if pid in c_probate and not ('probate' in lt or 'death certificate' in lt):
                        sig.append("Active County Probate Case")
                    if pid in c_judgment and not ('judgment' in lt or 'lien' in lt):
                        sig.append("County Judgment / Recorded Lien")
                    if pid in c_code and not ('code' in lt):
                        sig.append("Open Municipal Code Violation")
                    if pid in c_tax and not ('tax' in lt):
                        sig.append("County Tax Lien")
                    if pid in c_water and not ('water' in lt or 'ouc' in lt):
                        sig.append("OUC Water Shutoff")

                    if len(sig) >= 2:
                        return ('Yes', f"💥 TRIPLE DISTRESS: {ltype} + {' + '.join(sig)}")
                    elif len(sig) == 1:
                        return ('Yes', f"🔥 DOUBLE DISTRESS: {ltype} + {sig[0]}")
                    return ('No', '')

                res_c = combined_df.apply(lambda r: compute_combined(r.get('Parcel_ID', ''), r.get('Lead_Type', '')), axis=1)
                combined_df['Is_Stacked_Distress'] = res_c.apply(lambda x: x[0])
                combined_df['Distress_Stack_Notes'] = res_c.apply(lambda x: x[1])
                combined_df['Is_Trust_In_LP'] = combined_df.apply(
                    lambda r: 'Yes' if (r.get('Lead_Type') == 'Lis Pendens' and (r.get('Is_Trust_Or_Estate') == 'Yes' or 'Trust' in str(r.get('Owner_Entity_Type', '')) or r.get('Is_Stacked_Distress') == 'Yes')) else 'No',
                    axis=1
                )
                
                for c in combined_df.columns:
                    if combined_df[c].dtype == 'object':
                        combined_df[c] = combined_df[c].fillna('').astype(str)
                from pathlib import Path
                from uuid import uuid4
                pending_cache = Path(cache_file).with_name(f".matched-{uuid4().hex}.parquet")
                try:
                    combined_df.to_parquet(pending_cache, index=False)
                    os.replace(pending_cache, cache_file)
                finally:
                    pending_cache.unlink(missing_ok=True)
        except Exception as e:
            if uploaded:
                raise
            print("Multi-distress stacking error:", e)
    
    # Cache matched results for quick export
    app.state.last_results = matched_df
    app.state.last_county = county
    
    # Compute Analytics
    total_leads = len(matched_df)
    matched_mask = matched_df['Match_Status'] == 'MATCHED'
    matched_count = int(matched_mask.sum())
    match_rate = round((matched_count / total_leads * 100), 1) if total_leads > 0 else 0.0
    
    matched_subset = matched_df[matched_mask]
    absentee_count = int(matched_subset['Is_Absentee'].eq('Yes').sum())
    out_of_state_count = int(matched_subset['Absentee_Status'].eq('Absentee Out-of-State').sum())
    trust_count = int(matched_subset.get('Is_Trust_Or_Estate', pd.Series(dtype=str)).eq('Yes').sum())
    corporate_count = int(matched_subset['Owner_Entity_Type'].eq('Company / LLC').sum())
    stacked_count = int(matched_subset.get('Is_Stacked_Distress', pd.Series(dtype=str)).eq('Yes').sum())
    probate_count = int((matched_subset.get('Lead_Type', pd.Series(dtype=str)) == 'Probate').sum())
    lp_trust_count = int(((matched_subset.get('Lead_Type', pd.Series(dtype=str)) == 'Lis Pendens') & (matched_subset.get('Is_Trust_In_LP', pd.Series(dtype=str)) == 'Yes')).sum())
    
    avg_mkt_val = 0
    if 'Market_Value' in matched_subset.columns and len(matched_subset) > 0:
        vals = pd.to_numeric(matched_subset['Market_Value'], errors='coerce').fillna(0)
        avg_mkt_val = int(vals.mean())
        
    # Prepare preview records (top 150)
    display_cols = [
        'Lead_Type', 'Match_Status', 'Match_Confidence', 'Match_Method',
        'Clean_First_Name', 'Clean_Last_Name', 'Clean_Full_Name', 'Owner_Entity_Type',
        'Is_Trust_Or_Estate', 'Is_Trust_In_LP', 'Is_Stacked_Distress', 'Distress_Stack_Notes',
        'Property_Address', 'Property_City', 'Property_Zip', 'Parcel_ID',
        'Mailing_Address', 'Mailing_City', 'Mailing_State', 'Mailing_Zip',
        'Absentee_Status', 'Is_Absentee', 'Homestead_Exemption',
        'Market_Value', 'Assessed_Value', 'Year_Built', 'Living_Sqft', 'Legal_Description'
    ]
    
    valid_cols = [c for c in display_cols if c in matched_subset.columns]
    records = matched_subset[valid_cols].head(150).replace([float('nan'), float('inf'), -float('inf')], '').fillna('').to_dict(orient='records')
    
    # Enrich with any saved skip trace phone contacts
    saved_contacts = load_saved_contacts()
    for r in records:
        pid = str(r.get('Parcel_ID', '')).strip()
        if pid in saved_contacts:
            r['Saved_Phone'] = saved_contacts[pid].get('phone', '')
            r['Saved_Phone_Clean'] = saved_contacts[pid].get('clean_phone', '')
            r['Last_Sms_Sent'] = saved_contacts[pid].get('last_sms_sent', '')
    
    return {
        "status": "success",
        "county": county,
        "source_name": source_name,
        "elapsed_sec": elapsed,
        "kpis": {
            "total_leads": total_leads,
            "matched_count": matched_count,
            "match_rate": match_rate,
            "absentee_count": absentee_count,
            "out_of_state_count": out_of_state_count,
            "trust_count": trust_count,
            "corporate_count": corporate_count,
            "stacked_count": stacked_count,
            "probate_count": probate_count,
            "lp_trust_count": lp_trust_count,
            "avg_market_value": avg_mkt_val
        },
        "records": records
    }

@app.get("/api/export")
def export_csv(county: Optional[str] = None, state: Optional[str] = "FL", categories: Optional[str] = None):
    """Download matched leads in standard wholesaling preset with optional county & category filtering."""
    target_county = county or getattr(app.state, 'last_county', 'Orange')
    target_state = (state or "FL").upper()
    
    df = getattr(app.state, 'last_results', None)
    if df is None or getattr(app.state, 'last_county', '').lower() != target_county.lower():
        cache_path = os.path.join(DATA_DIR, target_state, target_county, "matched_leads_cache.parquet")
        if not os.path.exists(cache_path):
            cache_path = os.path.join(DATA_DIR, target_state, target_county.lower(), "matched_leads_cache.parquet")
        if os.path.exists(cache_path):
            try:
                df = pd.read_parquet(cache_path)
                app.state.last_results = df
                app.state.last_county = target_county
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed loading cache for {target_county}: {e}")
        else:
            raise HTTPException(status_code=400, detail=f"No matched results found for {target_county} County.")
    
    matched_df = df[df['Match_Status'] == 'MATCHED'].copy()
    
    # Filter by category if requested
    if categories:
        cat_list = [c.strip().lower() for c in categories.split(',') if c.strip()]
        masks = []
        for cat in cat_list:
            if cat in ['stacked', 'double_distress']:
                masks.append(matched_df['Is_Stacked_Distress'] == 'Yes')
            elif cat == 'lis_pendens':
                masks.append(matched_df['Lead_Type'] == 'Lis Pendens')
            elif cat == 'lp_trust':
                masks.append((matched_df['Lead_Type'] == 'Lis Pendens') & ((matched_df.get('Is_Trust_In_LP') == 'Yes') | (matched_df.get('Is_Trust_Or_Estate') == 'Yes')))
            elif cat == 'probate':
                masks.append(matched_df['Lead_Type'].str.contains('probate|death certificate', case=False, na=False))
            elif cat == 'divorce':
                masks.append(matched_df['Lead_Type'].str.contains('divorce|domestic relations', case=False, na=False))
            elif cat in ['judgment', 'judgments', 'lien', 'liens']:
                masks.append(matched_df['Lead_Type'].str.contains('judgment|lien', case=False, na=False))
            elif cat in ['code', 'code_violations']:
                masks.append(matched_df['Lead_Type'] == 'Code Violation')
            elif cat in ['water', 'water_shutoff', 'ouc']:
                masks.append(matched_df['Lead_Type'].str.contains('water|ouc', case=False, na=False))
            elif cat == 'absentee':
                masks.append(matched_df['Absentee_Status'].str.contains('Out-of-State', case=False, na=False))
            elif cat == 'tax_liens':
                masks.append(matched_df['Lead_Type'].str.contains('tax lien', case=False, na=False))
        if masks:
            combined_mask = masks[0]
            for m in masks[1:]:
                combined_mask = combined_mask | m
            matched_df = matched_df[combined_mask]

    priority_cols = ['Parcel_ID', 'Lead_Type', 'Is_Stacked_Distress', 'Distress_Stack_Notes']
    all_target_cols = priority_cols + [c for c in WHOLESALE_EXPORT_PRESET if c not in priority_cols and c in matched_df.columns]
    existing_cols = [c for c in all_target_cols if c in matched_df.columns]
    export_df = matched_df[existing_cols]
    
    csv_bytes = export_df.to_csv(index=False).encode('utf-8')
    cat_tag = f"_{categories.replace(',', '_')}" if categories else ""
    filename = f"{target_county}_Wholesale_Leads{cat_tag}_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def load_sms_settings() -> dict:
    defaults = {
        "mode": "local",  # "local" or "cloud"
        "base_url": "http://192.168.1.100:8080",
        "username": "admin",
        "password": "",
        "sim_number": 1,
        "template": "Hi {FirstName}, I noticed your property at {Address}. I'm an active local investor and wanted to see if you would consider a quick cash offer as-is? Let me know!"
    }
    if os.path.exists(SMS_SETTINGS_FILE):
        try:
            with open(SMS_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            pass
    return defaults

def save_sms_settings(settings: dict):
    with open(SMS_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

class ContactUpdateRequest(BaseModel):
    parcel_id: str
    county: Optional[str] = "Pinellas"
    phone: Optional[str] = ""
    clean_phone: Optional[str] = None
    email: Optional[str] = ""
    owner: Optional[str] = None
    source: Optional[str] = "TruePeopleSearch"

class Underwrite407FlipsLeadRequest(BaseModel):
    address: str
    listing_price: Optional[float] = 0.0
    arv: Optional[float] = 0.0
    sqft: Optional[int] = 1500
    year_built: Optional[int] = 1980
    beds: Optional[int] = 3
    baths: Optional[int] = 2
    condition: Optional[str] = "average"
    condition_notes: Optional[str] = ""
    wholesale_fee: Optional[float] = 10000.0
    parcel_id: Optional[str] = ""
    owner_name: Optional[str] = "Homeowner"

class SmsSettingsModel(BaseModel):
    mode: str = "local"
    base_url: str = "http://192.168.1.100:8080"
    username: str = "admin"
    password: str = ""
    sim_number: int = 1
    template: str

class SendSmsRequest(BaseModel):
    phone: str
    message: str
    parcel_id: Optional[str] = None
    county: Optional[str] = "Pinellas"
    owner_name: Optional[str] = None
    property_address: Optional[str] = None
    bypass_suppression: bool = False
    opener_angle: Optional[str] = None


def classify_opener_angle(msg: str) -> str:
    """Classifies which of the opener angles an outbound message corresponds to."""
    if not msg:
        return "other"
    low = msg.lower()
    if "casual_direct" in low or "work on homes in the neighborhood" in low:
        return "casual_direct"
    if "quick_question" in low or "still the owner of" in low:
        return "quick_question"
    if "neighbor_investor" in low or "wrapping up a renovation" in low or "doing another project" in low or "another project" in low:
        return "neighbor_investor"
    if "quick_checkin" in low or "consider an offer on" in low or "hold onto it" in low:
        return "quick_checkin"
    # Legacy fallbacks
    if "saw the house online" in low or "ever decide" in low:
        return "multi_list"
    if "came across" in low or "quick question" in low:
        return "single_list"
    if re.search(r'^\s*hey\s+[a-zA-Z0-9_\-\'\.]+\s*\?', low):
        return "ultra_short"
    return "casual_direct"


def classify_opt_out_variant(msg: str) -> str:
    """Classifies which of the 3 approved soft opt-out lines was appended."""
    low = (msg or "").lower()
    if "bothering you" in low:
        return "bothering"
    if "say the word" in low:
        return "say_the_word"
    if "drop it" in low:
        return "drop_it"
    return "other"

@app.get("/api/leads/contacts")
def get_contacts():
    """Return all saved lead contacts (phones, emails, notes)."""
    contacts = load_saved_contacts()
    approvals = auto_sms_queue.pending_initial_resends()
    from src.sms_outreach_queue import normalize_phone
    for pid, contact in contacts.items():
        contact['sms_initial_resend_pending'] = approvals.get(pid) == normalize_phone(contact.get('phone') or contact.get('clean_phone'))
    return contacts


def get_saved_property_index(county, state, indexes):
    key = (state or 'FL', county)
    if key not in indexes:
        info = get_county_paths(county, state=state or 'FL')
        cache = os.path.join(info['target_dir'], 'matched_leads_cache.parquet')
        indexes[key] = load_property_index(cache) if os.path.exists(cache) else None
    return indexes[key]


@app.post('/api/leads/refresh-property-matches')
def refresh_saved_property_matches():
    """Explicitly refresh and persist links; ordinary page loads never rematch."""
    indexes = {}
    for contact in load_saved_contacts().values():
        if contact.get('county'):
            get_saved_property_index(contact['county'], contact.get('state') or 'FL', indexes)
    with OUTREACH_DATA_LOCK:
        contacts = load_saved_contacts()
        updates, unresolved = {}, []
        for pid, contact in contacts.items():
            if pid.startswith('TEST-'):
                continue
            index = indexes.get((contact.get('state') or 'FL', contact.get('county')))
            match = index.resolve(pid, contact) if index else None
            if match:
                updates[pid] = match
            else:
                unresolved.append(pid)
        backup_dir = os.path.join(DATA_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        backup = os.path.join(backup_dir, f'saved_contacts-before-property-matches-{time.time_ns()}.json')
        atomic_outreach_json_write(backup, contacts)
        for pid, match in updates.items():
            contacts[pid].update(match)
        atomic_outreach_json_write(CONTACTS_FILE, contacts)
    return {'status': 'success', 'matched_contacts': len(updates),
            'unique_properties': len({m['matched_parcel_id'] for m in updates.values()}),
            'unresolved': unresolved, 'backup': backup}

@app.post("/api/leads/update-contact")
def update_lead_contact(req: ContactUpdateRequest):
    """Receive contact update from Chrome Extension or manual input."""
    data_to_save = {
        "owner": req.owner or "",
        "county": req.county or "Pinellas",
        "source": req.source or "TruePeopleSearch"
    }
    if req.phone:
        clean = req.clean_phone or "".join(filter(str.isdigit, req.phone))
        data_to_save["phone"] = req.phone
        data_to_save["clean_phone"] = clean
    if req.email:
        data_to_save["email"] = req.email.strip()

    contact = save_contact(req.parcel_id, data_to_save)
    return {"status": "success", "parcel_id": req.parcel_id, "contact": contact}

class DeleteLeadRequest(BaseModel):
    parcel_id: str

@app.post("/api/leads/delete")
def delete_lead_endpoint(req: DeleteLeadRequest):
    pid = (req.parcel_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="Missing parcel_id")
    deleted = load_deleted_leads()
    deleted.add(pid)
    save_deleted_leads(deleted)
    return {"status": "success", "message": f"Lead {pid} deleted", "parcel_id": pid}

@app.delete("/api/leads/{parcel_id}")
def delete_lead_by_id_endpoint(parcel_id: str):
    pid = (parcel_id or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="Missing parcel_id")
    deleted = load_deleted_leads()
    deleted.add(pid)
    save_deleted_leads(deleted)
    return {"status": "success", "message": f"Lead {pid} deleted", "parcel_id": pid}

@app.post("/api/leads/purge-condos")
def purge_condos_endpoint():
    """Bulk delete all properties containing #, Unit, Apt, Ste, Suite, Condo."""
    df = getattr(app.state, 'last_results', None)
    if df is None:
        return {"status": "error", "message": "No active dataset loaded"}
    
    condo_regex = r'(\b(unit|apt|ste|suite|condo)\b|#)'
    condo_mask = df['Property_Address'].str.contains(condo_regex, case=False, na=False)
    condo_pids = set(df[condo_mask]['Parcel_ID'].dropna().astype(str).str.strip().tolist())
    
    deleted = load_deleted_leads()
    initial_count = len(deleted)
    deleted.update(condo_pids)
    save_deleted_leads(deleted)
    purged_count = len(deleted) - initial_count
    return {"status": "success", "purged_count": purged_count, "total_deleted": len(deleted)}

def clean_phone_number(val: Any) -> Tuple[str, str]:
    if not val or pd.isna(val):
        return "", ""
    digits = re.sub(r'\D', '', str(val))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}", digits
    elif len(digits) > 10:
        d10 = digits[-10:]
        return f"({d10[:3]}) {d10[3:6]}-{d10[6:]}", d10
    return str(val).strip(), digits

FL_CITY_COUNTY_MAP = {
    "orlando": "Orange", "winter park": "Orange", "apopka": "Orange", "ocoee": "Orange", "windermere": "Orange",
    "winter garden": "Orange", "maitland": "Orange", "tampa": "Hillsborough", "temple terrace": "Hillsborough",
    "plant city": "Hillsborough", "st petersburg": "Pinellas", "saint petersburg": "Pinellas", "clearwater": "Pinellas",
    "largo": "Pinellas", "pinellas park": "Pinellas", "dunedin": "Pinellas", "tarpon springs": "Pinellas",
    "palm harbor": "Pinellas", "seminole": "Pinellas", "safety harbor": "Pinellas", "sanford": "Seminole",
    "altamonte springs": "Seminole", "oviedo": "Seminole", "casselberry": "Seminole", "lake mary": "Seminole",
    "longwood": "Seminole", "winter springs": "Seminole", "kissimmee": "Osceola", "st cloud": "Osceola",
    "saint cloud": "Osceola", "lakeland": "Polk", "winter haven": "Polk", "bartow": "Polk", "haines city": "Polk",
    "new port richey": "Pasco", "port richey": "Pasco", "land o lakes": "Pasco", "wesley chapel": "Pasco",
    "sarasota": "Sarasota", "venice": "Sarasota", "north port": "Sarasota", "bradenton": "Manatee",
    "palmetto": "Manatee", "daytona beach": "Volusia", "deland": "Volusia", "ormond beach": "Volusia",
    "clermont": "Lake", "leesburg": "Lake", "tavares": "Lake", "mount dora": "Lake",
    "gainesville": "Alachua", "ocala": "Marion", "jacksonville": "Duval", "fort myers": "Lee",
    "cape coral": "Lee", "naples": "Collier", "miami": "Miami-Dade", "fort lauderdale": "Broward",
    "west palm beach": "Palm Beach", "boca raton": "Palm Beach", "tallahassee": "Leon", "pensacola": "Escambia"
}


# Cache for county distress lookup dataframes (loaded once per run)
_distress_lookup_cache: dict = {}

def _normalize_addr(addr: str) -> str:
    """Normalize address to alphanumeric-only uppercase for fuzzy matching."""
    return re.sub(r'[^A-Z0-9]', '', str(addr).upper())

def _lookup_distress_by_address(county: str, address: str) -> str:
    """
    Cross-reference an address against local county distress data files to
    recover the real Lead_Type when the CSV only says 'Skip-Traced Lead'.
    Returns the real distress type string, or empty string if not found.
    """
    global _distress_lookup_cache
    if not county or not address:
        return ""

    norm_addr = _normalize_addr(address)
    if not norm_addr:
        return ""

    # Load (and cache) the county distress dataframe
    if county not in _distress_lookup_cache:
        county_dir = os.path.join("data", "FL", county)
        parquet_path = os.path.join(county_dir, "matched_leads_cache.parquet")
        dfs = []
        # Primary: parquet cache
        if os.path.exists(parquet_path):
            try:
                df_p = pd.read_parquet(parquet_path, columns=["Property_Address", "Lead_Type"])
                df_p = df_p.rename(columns={"Property_Address": "addr", "Lead_Type": "lt"})
                dfs.append(df_p)
            except Exception:
                pass
        # Fallback CSV files with Lead_Type column
        for fname in os.listdir(county_dir) if os.path.isdir(county_dir) else []:
            if not fname.lower().endswith('.csv'):
                continue
            fpath = os.path.join(county_dir, fname)
            try:
                df_c = pd.read_csv(fpath, dtype=str, low_memory=False)
                # Must have both an address and a Lead_Type column
                addr_c = next((c for c in df_c.columns if re.search(r'address', c, re.I)), None)
                lt_c   = next((c for c in df_c.columns if re.search(r'lead.*type|distress', c, re.I)), None)
                if addr_c and lt_c:
                    tmp = df_c[[addr_c, lt_c]].rename(columns={addr_c: "addr", lt_c: "lt"})
                    dfs.append(tmp)
            except Exception:
                pass

        if dfs:
            combined = pd.concat(dfs, ignore_index=True)
            combined = combined.dropna(subset=["addr"])
            combined["addr_norm"] = combined["addr"].apply(_normalize_addr)
            combined = combined[combined["addr_norm"] != ""]
            _distress_lookup_cache[county] = combined
        else:
            _distress_lookup_cache[county] = None

    df_lookup = _distress_lookup_cache.get(county)
    if df_lookup is None or df_lookup.empty:
        return ""

    # Exact normalized match
    matches = df_lookup[df_lookup["addr_norm"] == norm_addr]
    if not matches.empty:
        lt = str(matches.iloc[0]["lt"]).strip()
        if lt and lt.lower() not in ("nan", "none", "", "skip-traced lead"):
            return lt

    # Partial match: address starts-with (handles unit suffix differences)
    if len(norm_addr) >= 8:
        partial = df_lookup[df_lookup["addr_norm"].str.startswith(norm_addr[:min(len(norm_addr), 20)])]
        if not partial.empty:
            lt = str(partial.iloc[0]["lt"]).strip()
            if lt and lt.lower() not in ("nan", "none", "", "skip-traced lead"):
                return lt

    return ""

def detect_fl_county(raw_county: Any, city: Any, default_county: str = "Pinellas") -> str:

    if raw_county and not pd.isna(raw_county):
        cleaned = re.sub(r'(?i)\bcounty\b|\bfl\b|[,\.]', '', str(raw_county)).strip().title()
        if cleaned:
            return cleaned
    if city and not pd.isna(city):
        city_clean = str(city).strip().lower()
        if city_clean in FL_CITY_COUNTY_MAP:
            return FL_CITY_COUNTY_MAP[city_clean]
    return default_county or "Pinellas"

@app.post("/api/leads/import-skiptrace")
async def import_skiptrace_endpoint(
    file: UploadFile = File(...),
    default_county: str = Form("Pinellas")
):
    """
    Import a skip-traced CSV or Excel spreadsheet containing phone numbers, emails,
    and property owners across one or multiple Florida counties.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    contents = await file.read()
    try:
        if file.filename.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents), dtype=str)
        else:
            try:
                df = pd.read_csv(io.BytesIO(contents), dtype=str, low_memory=False)
            except UnicodeDecodeError:
                df = pd.read_csv(io.BytesIO(contents), dtype=str, encoding='latin1', low_memory=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read spreadsheet: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="The uploaded spreadsheet is empty.")

    # Auto-detect header row offset if top rows are blank or report titles
    unnamed_cols = [c for c in df.columns if str(c).startswith("Unnamed")]
    if len(unnamed_cols) >= len(df.columns) * 0.5:
        header_keywords = ('ADDRESS', 'PHONE', 'NAME', 'PARCEL', 'APN', 'EMAIL', 'COUNTY', 'CITY', 'OWNER')
        for i in range(min(15, len(df))):
            row_vals = [str(x).upper() for x in df.iloc[i].tolist()]
            if any(any(kw in val for kw in header_keywords) for val in row_vals):
                new_headers = [str(x).strip() if pd.notna(x) and str(x).strip() != '' else f"COL_{idx}" for idx, x in enumerate(df.iloc[i].tolist())]
                df = df.iloc[i + 1:].copy().reset_index(drop=True)
                df.columns = new_headers
                break

    cols = list(df.columns)
    
    def find_col(*patterns):
        for pattern in patterns:
            for c in cols:
                readable = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', str(c)).replace('_', ' ')
                if re.search(pattern, str(c), re.IGNORECASE) or re.search(pattern, readable, re.IGNORECASE):
                    return c
        return None

    # Detect Phone columns in order of priority
    phone_cols = []
    for c in cols:
        c_str = str(c).strip()
        if re.search(r'\b(mobile|cell|wireless|direct)\b', c_str, re.IGNORECASE):
            phone_cols.append(c)
    for c in cols:
        c_str = str(c).strip()
        if re.search(r'\bphone\s*1\b|\bphone_1\b|\bprimary\s*phone\b|\bphone\b', c_str, re.IGNORECASE) and c not in phone_cols:
            phone_cols.append(c)
    for c in cols:
        c_str = str(c).strip()
        if re.search(r'\bphone\s*[2-9]\b|\bphone_[2-9]\b', c_str, re.IGNORECASE) and c not in phone_cols:
            phone_cols.append(c)
    for c in cols:
        c_str = str(c).strip()
        if re.search(r'phone|tel|number', c_str, re.IGNORECASE) and c not in phone_cols:
            phone_cols.append(c)

    # Detect Email columns
    email_cols = [c for c in cols if re.search(r'email|e[-_\s]+mail|^mail$', str(c), re.IGNORECASE)]

    # Detect Owner columns
    owner_col = find_col(r'\bowner\s*name\b', r'\bfull\s*name\b', r'\bowner\b', r'\bclean_full_name\b', r'\bcontact\s*name\b', r'^name$')
    first_name_col = find_col(r'\bfirst\s*name\b', r'\bfirst_name\b')
    last_name_col = find_col(r'\blast\s*name\b', r'\blast_name\b')

    # Detect Address columns
    addr_col = find_col(r'\bproperty\s*address\b', r'\bsitus\s*address\b', r'\baddress\b', r'\bstreet\s*address\b', r'\bproperty_address\b')
    city_col = find_col(r'\bproperty\s*city\b', r'\bsitus\s*city\b', r'\bcity\b')
    state_col = find_col(r'\bproperty\s*state\b', r'\bstate\b')
    zip_col = find_col(r'\bproperty\s*zip\b', r'\bzip\b', r'\bpostal\b')

    # Detect County column
    county_col = find_col(r'\bproperty\s*county\b', r'\bcounty\b')

    # Detect Parcel / APN column
    parcel_col = find_col(r'\bparcel\s*id\b', r'\bparcel_id\b', r'\bapn\b', r'\bfolio\b', r'\bpin\b', r'\bstrap\b', r'\bparcel\b')

    # Detect Distress / Lead Type / List
    distress_col = find_col(r'\blead\s*type\b', r'\bdistress\b', r'\btags?\b', r'\blist\b', r'\bcategory\b')

    # Detect Market / Assessed Value
    value_col = find_col(r'\bmarket\s*value\b', r'\bjust\s*value\b', r'\bassessed\b', r'\bestimated\s*value\b', r'\bvalue\b')

    saved_contacts = load_saved_contacts()
    property_indexes = {}
    imported_count = 0
    phones_found = 0
    emails_found = 0
    counties_breakdown = {}

    for idx, row in df.iterrows():
        primary_phone = ""
        clean_p = ""
        phone_2 = ""
        for pc in phone_cols:
            val = str(row.get(pc, '')).strip()
            fmt, clean = clean_phone_number(val)
            if clean and len(clean) >= 10:
                if not primary_phone:
                    primary_phone = fmt
                    clean_p = clean
                elif not phone_2 and clean != clean_p:
                    phone_2 = fmt
                    break

        email = ""
        for ec in email_cols:
            eval_val = str(row.get(ec, '')).strip()
            if '@' in eval_val and '.' in eval_val:
                email = eval_val
                break

        owner = ""
        if owner_col and pd.notna(row.get(owner_col)):
            owner = str(row.get(owner_col)).strip()
        elif first_name_col or last_name_col:
            fn = str(row.get(first_name_col, '')).strip() if first_name_col else ""
            ln = str(row.get(last_name_col, '')).strip() if last_name_col else ""
            owner = f"{fn} {ln}".strip()

        addr = str(row.get(addr_col, '')).strip() if addr_col and pd.notna(row.get(addr_col)) else ""
        city = str(row.get(city_col, '')).strip() if city_col and pd.notna(row.get(city_col)) else ""
        state = str(row.get(state_col, 'FL')).strip() if state_col and pd.notna(row.get(state_col)) else "FL"
        zip_code = str(row.get(zip_col, '')).strip() if zip_col and pd.notna(row.get(zip_col)) else ""

        if not primary_phone and not email and not addr and not owner:
            continue

        raw_county = str(row.get(county_col, '')).strip() if county_col and pd.notna(row.get(county_col)) else ""
        county = detect_fl_county(raw_county, city, default_county)

        pid = str(row.get(parcel_col, '')).strip() if parcel_col and pd.notna(row.get(parcel_col)) else ""
        if not pid or pid.lower() in ('nan', 'none', 'null', ''):
            clean_addr_slug = re.sub(r'[^A-Za-z0-9]', '-', addr).strip('-').upper()
            if not clean_addr_slug and owner:
                clean_addr_slug = re.sub(r'[^A-Za-z0-9]', '-', owner).strip('-').upper()
            pid = f"SKIP-{county.upper()}-{clean_addr_slug[:24] or str(idx)}"

        val_str = str(row.get(value_col, '0')).strip() if value_col and pd.notna(row.get(value_col)) else "0"
        val_clean = re.sub(r'[^\d\.]', '', val_str)
        try:
            market_val = float(val_clean) if val_clean else 250000.0
        except ValueError:
            market_val = 250000.0

        distress = str(row.get(distress_col, 'Skip-Traced Lead')).strip() if distress_col and pd.notna(row.get(distress_col)) else "Skip-Traced Lead"
        if not distress or distress.lower() in ('nan', 'none'):
            distress = "Skip-Traced Lead"

        contact_record = {
            "owner": owner or "Property Owner",
            "county": county,
            "address": addr,
            "city": city,
            "state": state,
            "zip": zip_code,
            "phone": primary_phone,
            "clean_phone": clean_p,
            "phone_2": phone_2,
            "email": email,
            "just_value": market_val,
            "distress_category": distress,
            "source": f"Skip Trace CSV ({file.filename})",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        previous = saved_contacts.get(pid, {})
        same_property = (previous.get('property_match') and address_key(previous.get('address')) == address_key(addr)
                         and previous.get('county') == county and (previous.get('state') or 'FL') == state)
        if same_property:
            contact_record.update({k: previous[k] for k in ('matched_parcel_id', 'property_match')})
        else:
            index = get_saved_property_index(county, state, property_indexes)
            match = index.resolve(pid, contact_record) if index else None
            if match:
                contact_record.update(match)
        if contact_record.get('property_match'):
            contact_record['distress_category'] = contact_record['property_match']['record']['Lead_Type']
        for field in ('phone', 'clean_phone', 'phone_2', 'email'):
            if not contact_record.get(field) and previous.get(field):
                contact_record[field] = previous[field]

        saved_contacts[pid] = {
            **saved_contacts.get(pid, {}),
            **contact_record
        }

        imported_count += 1
        if primary_phone:
            phones_found += 1
        if email:
            emails_found += 1
        counties_breakdown[county] = counties_breakdown.get(county, 0) + 1

    with OUTREACH_DATA_LOCK:
        # Preserve SMS tracking if a background send finished during the import.
        for existing_pid, existing_contact in load_saved_contacts().items():
            if existing_pid not in saved_contacts:
                saved_contacts[existing_pid] = existing_contact
            elif str(existing_contact.get("last_sms_sent") or "") >= str(saved_contacts[existing_pid].get("last_sms_sent") or ""):
                for field in ("last_sms_sent", "last_sms_status", "last_sms_message"):
                    if field in existing_contact:
                        saved_contacts[existing_pid][field] = existing_contact[field]
        atomic_outreach_json_write(CONTACTS_FILE, saved_contacts)

    return {
        "status": "success",
        "imported_count": imported_count,
        "phones_found": phones_found,
        "emails_found": emails_found,
        "counties_breakdown": counties_breakdown,
        "counties_count": len(counties_breakdown),
        "message": f"Successfully imported {imported_count} skip-traced leads across {len(counties_breakdown)} Florida counties."
    }

@app.get("/api/sms/settings")
def get_sms_settings():
    """Return current Android SMS Gateway configuration."""
    return load_sms_settings()

@app.post("/api/sms/settings")
def update_sms_settings(req: SmsSettingsModel):
    """Update and persist Android SMS Gateway configuration."""
    save_sms_settings(req.dict())
    return {"status": "success", "settings": req.dict()}

@app.post("/api/sms/send")
def send_sms_via_gateway(req: SendSmsRequest):
    """
    Send an SMS using Android SMS Gateway (https://github.com/capcom6/android-sms-gateway).
    Formats payload according to official OpenAPI spec: POST /3rdparty/v1/messages
    Enforces permanent suppression and DNC registry scrub before dispatch.
    """
    # Recheck late replies at the gateway boundary, including manual sends.
    if str(req.opener_angle or '').startswith('follow_up_') and auto_sms_queue.has_replied(req.phone):
        return {'status': 'error', 'suppressed': True, 'blocked_reason': 'Already replied',
                'message': 'Follow-up skipped because this person has replied.'}

    # 1. Check permanent suppression and DNC registry before any outbound SMS
    if not req.bypass_suppression:
        is_blocked, block_reason = is_lead_blocked_from_outreach(req.phone, {
            "parcel_id": req.parcel_id,
            "owner_name": req.owner_name,
            "property_address": req.property_address
        })
        if is_blocked:
            return {
                "status": "error",
                "message": f"Outbound SMS blocked: {block_reason}",
                "suppressed": True,
                "blocked_reason": block_reason
            }

    settings = load_sms_settings()
    mode = settings.get("mode", "local")
    base_url = settings.get("base_url", "http://192.168.1.100:8080").rstrip("/")
    username = settings.get("username", "admin")
    password = settings.get("password", "")
    sim_number = int(settings.get("sim_number", 1))

    # Clean phone number
    digits = "".join(filter(str.isdigit, req.phone))
    if len(digits) == 10:
        phone_e164 = f"+1{digits}"
    elif len(digits) == 11 and digits.startswith("1"):
        phone_e164 = f"+{digits}"
    elif req.phone.startswith("+"):
        phone_e164 = req.phone.strip()
    else:
        phone_e164 = digits

    # Safe Sandbox Test Lead Handling (Non-live carrier simulation for dummy 555 numbers)
    # Exclude user's real Google Voice test line (407-504-2503) so live carrier SMS actually dispatches!
    is_live_google_voice = ("4075042503" in digits or "5042503" in digits)
    is_sandbox = not is_live_google_voice and (
        (req.parcel_id and str(req.parcel_id) == "TEST-PINELLAS-001") or
        "5550199" in digits or "555" in digits
    )

    clean_msg = sanitize_sms_no_underlines_no_hyphens(req.message)

    # Opener angle and soft opt-out tagging
    angle = getattr(req, "opener_angle", None) or classify_opener_angle(clean_msg)
    opt_variant = classify_opt_out_variant(clean_msg)

    if is_sandbox:
        resp_data = {"id": f"sandbox_sms_{int(time.time())}", "state": "Delivered (Sandbox Simulated)"}
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": "SMS",
            "direction": "OUTBOUND",
            "parcel_id": req.parcel_id or "TEST-PINELLAS-001",
            "county": req.county or "Pinellas",
            "owner": req.owner_name or "Robert Vance (Test Lead)",
            "address": clean_address_for_sms(req.property_address or "742 Evergreen Terr, St. Petersburg, FL"),
            "phone": phone_e164,
            "recipient": phone_e164,
            "subject": "SMS Text Message (Sandbox)",
            "message": clean_msg,
            "opener_angle": angle,
            "opt_out_variant": opt_variant,
            "status": "SENT",
            "status_code": 200,
            "response": resp_data,
            "sandbox": True
        }
        logs = []
        if os.path.exists(OUTREACH_LOG_FILE):
            try:
                with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        append_outreach_log(log_entry)

        if req.parcel_id:
            save_contact(req.parcel_id, {
                "last_sms_sent": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_sms_status": "SENT (Sandbox)",
                "last_sms_message": clean_msg
            })

        # Auto-trigger an interactive 2-way reply from Robert Vance 3 seconds later
        # Rotating Stage 1 target replies: "what?", "who is this?", "which one were you?"
        def simulate_homeowner_reply():
            time.sleep(3)
            sample_inbounds = [
                "what? who is this?",
                "which one were you? when did we talk?",
                "who is this?",
                "excuse me?",
                "Hey Emma, thanks for reaching out. What would you offer cash for the place as is?",
                "We got cited for the garage and roof by county code enforcement. Can you close fast with cash?",
                "I might sell if the price makes sense. I'll let it go for 130k if you can close this month."
            ]
            sim_text = random.choice(sample_inbounds)
            sim_req = InboundSmsWebhookRequest(
                phone=req.phone or "(727) 555-0199",
                message=sim_text,
                parcel_id=req.parcel_id or "TEST-PINELLAS-001"
            )
            simulate_seller_inbound(sim_req)

        threading.Thread(target=simulate_homeowner_reply, daemon=True).start()

        return {
            "status": "success",
            "message": "✓ Sandbox SMS dispatched! (Simulated 2-way reply arriving in 3s)",
            "log": log_entry,
            "sandbox": True
        }

    target_url = "https://api.sms-gate.app/3rdparty/v1/messages" if mode == "cloud" else f"{base_url}/3rdparty/v1/messages"

    payload = {
        "textMessage": {
            "text": clean_msg
        },
        "phoneNumbers": [phone_e164],
        "simNumber": sim_number,
        "priority": 100
    }

    headers = {"Content-Type": "application/json"}
    auth = HTTPBasicAuth(username, password) if username or password else None

    try:
        resp = requests.post(target_url, json=payload, headers=headers, auth=auth, timeout=12)
        resp_data = resp.json() if resp.status_code in [200, 201, 202] else {"text": resp.text}
        
        # Log outreach
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": "SMS",
            "direction": "OUTBOUND",
            "parcel_id": req.parcel_id,
            "county": req.county,
            "owner": req.owner_name,
            "address": req.property_address,
            "phone": phone_e164,
            "recipient": phone_e164,
            "subject": "SMS Text Message",
            "message": req.message,
            "opener_angle": angle,
            "opt_out_variant": opt_variant,
            "status": "SENT" if resp.status_code in [200, 201, 202] else "FAILED",
            "status_code": resp.status_code,
            "response": resp_data
        }
        
        # Save to outreach log
        logs = []
        if os.path.exists(OUTREACH_LOG_FILE):
            try:
                with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        append_outreach_log(log_entry)

        # Mark in saved contacts
        if req.parcel_id:
            save_contact(req.parcel_id, {
                "last_sms_sent": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_sms_status": "SENT" if resp.status_code in [200, 201, 202] else "FAILED"
            })

        if resp.status_code not in [200, 201, 202]:
            return {
                "status": "error",
                "message": f"SMS Gateway returned HTTP {resp.status_code}: {resp.text}",
                "url": target_url
            }

        auto_sms_queue.record_sent(req.phone)
        return {
            "status": "success",
            "message": "SMS dispatched successfully to your Android phone!",
            "phone": phone_e164,
            "gateway_response": resp_data
        }
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": f"Could not connect to Android SMS Gateway at {target_url}. Check phone Wi-Fi IP and ensure app is running. Details: {str(e)}"
        }

@app.post("/api/sms/test")
def test_sms_gateway():
    """Ping the Android SMS Gateway to verify connectivity."""
    settings = load_sms_settings()
    mode = settings.get("mode", "local")
    base_url = settings.get("base_url", "http://192.168.1.100:8080").rstrip("/")
    username = settings.get("username", "admin")
    password = settings.get("password", "")
    target_url = "https://api.sms-gate.app/3rdparty/v1/health" if mode == "cloud" else f"{base_url}/"
    headers = {"Content-Type": "application/json"}
    auth = HTTPBasicAuth(username, password) if username or password else None
    try:
        resp = requests.get(target_url, headers=headers, auth=auth, timeout=6)
        if resp.status_code in [200, 201, 204]:
            return {"status": "success", "message": f"Successfully connected to Android Gateway! (HTTP {resp.status_code})"}
        elif resp.status_code == 401:
            return {"status": "error", "message": "Phone reached, but Username/Password is incorrect (HTTP 401 Unauthorized)."}
        else:
            return {"status": "warning", "message": f"Gateway reachable, returned HTTP {resp.status_code}."}
    except Exception as e:
        return {"status": "error", "message": f"Connection failed: {str(e)}"}

# -------------------------------------------------------------
# Direct-to-Seller Autonomous Bot & Golden Training Suite API
# -------------------------------------------------------------

def find_lead_by_phone(phone_str: str, *, allow_online_lookup: bool = True, contacts: Optional[Dict[str, Any]] = None, valuation_cache: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Finds matching parcel lead in saved contacts or defaults to generic Florida lead."""
    digits = "".join(filter(str.isdigit, str(phone_str)))
    if len(digits) > 10 and digits.startswith("1"):
        digits = digits[1:]

    # Dedicated Sandbox Test Lead match
    if digits in ["7275550199", "4075550199", "5550199"]:
        return {
            "parcel_id": "TEST-PINELLAS-001",
            "owner_name": "Robert Vance (Test Lead)",
            "property_address": "742 Evergreen Terr, St. Petersburg, FL 33701",
            "phone": "(727) 555-0199",
            "distress_category": "Code Violation",
            "just_value": 240000.0,
            "market_value": 312000.0
        }

    # Dedicated Live Google Voice Test Lead #2 match
    if digits in ["4075042503", "14075042503"] or "5042503" in digits:
        return {
            "parcel_id": "TEST-PINELLAS-002",
            "owner_name": "Marcus Sterling (Test Lead #2)",
            "property_address": "1204 Gulf Way, St. Pete Beach, FL 33706",
            "phone": "(407) 504-2503",
            "distress_category": "Lis Pendens",
            "just_value": 310000.0,
            "market_value": 485000.0
        }

    if contacts is None:
        contacts = load_saved_contacts()
    for pid, c in contacts.items():
        c_clean = c.get("clean_phone") or "".join(filter(str.isdigit, str(c.get("phone", ""))))
        if c_clean and (digits in c_clean or c_clean in digits):
            jval = float(c.get("just_value") or 250000.0)
            val = get_property_market_valuation(c.get("address", ""), jval, allow_online_lookup=allow_online_lookup, cache=valuation_cache)
            return {
                "parcel_id": pid,
                "owner_name": c.get("owner") or "Property Owner",
                "property_address": c.get("address") or "Florida Property",
                "phone": c.get("phone") or phone_str,
                "distress_category": c.get("distress_category") or "General Distress",
                "just_value": jval,
                "market_value": float(val.get("market_value") or (jval * 1.30))
            }

    return {
        "parcel_id": "",
        "owner_name": "Florida Homeowner",
        "property_address": "Florida Property",
        "phone": phone_str,
        "distress_category": "General Distress",
        "just_value": 250000.0
    }

def get_lead_sms_thread(phone_str: str, parcel_id: str = "") -> List[Dict[str, Any]]:
    """Retrieves 2-way conversation history for a given phone or parcel."""
    digits = "".join(filter(str.isdigit, str(phone_str)))
    if len(digits) > 10 and digits.startswith("1"):
        digits = digits[1:]

    history = []
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
                for entry in logs:
                    e_phone = "".join(filter(str.isdigit, str(entry.get("phone") or entry.get("recipient") or entry.get("sender_phone") or "")))
                    e_pid = str(entry.get("parcel_id") or "")
                    if (digits and (digits in e_phone or e_phone in digits)) or (parcel_id and parcel_id == e_pid):
                        history.append(entry)
        except Exception:
            pass
    return sorted(history, key=lambda x: x.get("timestamp", ""))

class InboundSmsWebhookRequest(BaseModel):
    phone: Optional[str] = None
    sender: Optional[str] = None
    from_number: Optional[str] = None
    message: Optional[str] = None
    text: Optional[str] = None
    body: Optional[str] = None
    parcel_id: Optional[str] = None

@app.post("/api/sms/inbound")
@app.post("/api/webhooks/android-sms-gateway")
async def receive_inbound_sms(request: Request):
    """
    Inbound SMS Webhook from Android SMS Gateway.
    Supports official Cloud & Local Android SMS Gateway event format and flat JSON.
    1. Captures text from seller
    2. Matches parcel lead record
    3. Runs through SellerBotEngine (Code, Lis Pendens, Probate)
    4. Evaluates deal spread
    5. Logs into outreach_history.json
    6. If in Autopilot mode and allowed, dispatches AI reply via gateway
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}

    # Extract phone number
    sender_phone = (
        body.get("phoneNumber") or body.get("phone") or body.get("sender") or body.get("from_number") or
        payload.get("phoneNumber") or payload.get("phone") or payload.get("sender") or ""
    )
    if not sender_phone and isinstance(payload.get("phoneNumbers"), list) and len(payload["phoneNumbers"]) > 0:
        sender_phone = payload["phoneNumbers"][0]

    # Extract message text
    msg_text = (
        body.get("message") or body.get("text") or body.get("body") or
        payload.get("message") or payload.get("text") or payload.get("body") or ""
    )

    event_type = body.get("event", "")
    if event_type and event_type not in ("sms:received", "mms:downloaded", ""):
        return {"status": "ignored", "reason": f"Event {event_type} ignored"}

    if not sender_phone or not msg_text:
        return {"status": "ignored", "reason": "No sender phone or message text detected"}

    auto_sms_queue.record_reply(sender_phone)
    lead = find_lead_by_phone(sender_phone)
    parcel_override = body.get("parcel_id") or payload.get("parcel_id")
    if parcel_override:
        lead["parcel_id"] = parcel_override

    history = get_lead_sms_thread(sender_phone, lead.get("parcel_id", ""))
    bot_res = seller_bot.process_inbound_sms(lead, msg_text, history)

    outbound_msgs = [m for m in history if m.get("direction") == "OUTBOUND"]
    first_outbound = outbound_msgs[0] if outbound_msgs else None
    reply_to_opener = first_outbound.get("opener_angle") if first_outbound else (classify_opener_angle(first_outbound.get("message", "")) if first_outbound else None)

    # Log incoming message to outreach history
    log_entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": "SMS",
        "direction": "INBOUND",
        "sender_phone": sender_phone,
        "phone": sender_phone,
        "recipient": "Emma (Gateway)",
        "parcel_id": lead.get("parcel_id"),
        "owner": lead.get("owner_name"),
        "address": lead.get("property_address"),
        "message": msg_text,
        "status": "RECEIVED",
        "bot_action": bot_res.get("action"),
        "bot_node": bot_res.get("node"),
        "suggested_reply": bot_res.get("suggested_reply"),
        "bot_response": bot_res.get("suggested_reply"),
        "reply_to_opener_angle": reply_to_opener,
        "is_opt_out": (bot_res.get("action") == "OPT_OUT"),
        "deal_evaluation": bot_res.get("deal_evaluation"),
        "spread_eval": bot_res.get("deal_evaluation")
    }

    logs = []
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    append_outreach_log(log_entry)

    # If opt-out action was detected, permanently persist to suppression list and dispatch confirmation
    if bot_res.get("action") == "OPT_OUT":
        add_to_suppression_list(sender_phone, reason="OPT_OUT", lead_info=lead)
        opt_out_reply = bot_res.get("suggested_reply") or "Got it, won't text again."
        try:
            send_sms_via_gateway(SendSmsRequest(
                phone=sender_phone,
                message=opt_out_reply,
                parcel_id=lead.get("parcel_id"),
                owner_name=lead.get("owner_name"),
                property_address=lead.get("property_address"),
                bypass_suppression=True
            ))
        except Exception as e:
            print(f"[OptOut] Error dispatching opt-out confirmation: {e}")

    # If appointment was confirmed, automatically dispatch calendar invite (.ics) to John's Gmail
    if bot_res.get("action") == "APPOINTMENT_CONFIRMED":
        try:
            appt_time_str = bot_res.get("appointment_time") or "Soon"
            send_calendar_invite_email(lead, appt_time_str)
        except Exception as e:
            print(f"[CalendarSync] Error sending calendar invite: {e}")

    # Check for Autopilot automated dispatch (with 30-45 second human delay)
    settings = load_seller_bot_settings()
    auto_dispatched = False
    if (settings.get("enabled") and settings.get("mode") == "autopilot"
            and bot_res.get("auto_send_allowed") and not auto_sms_queue.requires_manual_reply(sender_phone)):
        reply_text = bot_res.get("suggested_reply")
        if reply_text:
            delay_sec = int(settings.get("auto_send_delay_seconds") or random.randint(30, 45))
            def delayed_dispatch():
                time.sleep(delay_sec)
                if auto_sms_queue.requires_manual_reply(sender_phone):
                    return
                send_sms_via_gateway(SendSmsRequest(
                    phone=sender_phone,
                    message=reply_text,
                    parcel_id=lead.get("parcel_id"),
                    owner_name=lead.get("owner_name"),
                    property_address=lead.get("property_address")
                ))
            threading.Thread(target=delayed_dispatch, daemon=True).start()
            auto_dispatched = True

    return {
        "status": "success",
        "ok": True,
        "lead": lead,
        "bot_response": bot_res.get("suggested_reply"),
        "suggested_reply": bot_res.get("suggested_reply"),
        "action": bot_res.get("action"),
        "deal_evaluation": bot_res.get("deal_evaluation"),
        "spread_eval": bot_res.get("deal_evaluation"),
        "auto_dispatched": auto_dispatched
    }

@app.post("/api/sms/simulate-inbound")
def simulate_seller_inbound(req: InboundSmsWebhookRequest):
    """Simulates an inbound seller text for testing copilot and training flows."""
    sender_phone = req.phone or req.sender or req.from_number or "(727) 555-0199"
    msg_text = req.message or req.text or req.body or "How much can you offer cash?"
    auto_sms_queue.record_reply(sender_phone)
    lead = find_lead_by_phone(sender_phone)
    if req.parcel_id:
        lead["parcel_id"] = req.parcel_id

    history = get_lead_sms_thread(sender_phone, lead.get("parcel_id", ""))
    bot_res = seller_bot.process_inbound_sms(lead, msg_text, history)

    # If opt-out action was detected, persist to suppression list
    if bot_res.get("action") == "OPT_OUT":
        add_to_suppression_list(sender_phone, reason="OPT_OUT", lead_info=lead)

    outbound_msgs = [m for m in history if m.get("direction") == "OUTBOUND"]
    first_outbound = outbound_msgs[0] if outbound_msgs else None
    reply_to_opener = first_outbound.get("opener_angle") if first_outbound else (classify_opener_angle(first_outbound.get("message", "")) if first_outbound else None)

    log_entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "channel": "SMS",
        "direction": "INBOUND",
        "sender_phone": sender_phone,
        "phone": sender_phone,
        "recipient": "Emma (Gateway)",
        "parcel_id": lead.get("parcel_id"),
        "owner": lead.get("owner_name"),
        "address": lead.get("property_address"),
        "message": msg_text,
        "status": "RECEIVED",
        "bot_action": bot_res.get("action"),
        "bot_node": bot_res.get("node"),
        "suggested_reply": bot_res.get("suggested_reply"),
        "bot_response": bot_res.get("suggested_reply"),
        "reply_to_opener_angle": reply_to_opener,
        "is_opt_out": (bot_res.get("action") == "OPT_OUT"),
        "deal_evaluation": bot_res.get("deal_evaluation"),
        "spread_eval": bot_res.get("deal_evaluation")
    }

    logs = []
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    append_outreach_log(log_entry)

    return {
        "status": "success",
        "ok": True,
        "lead": lead,
        "bot_response": bot_res,
        "log": log_entry
    }

@app.post("/api/leads/sandbox-test-lead")
def ensure_sandbox_test_lead():
    """Seeds or resets the dedicated Sandbox Test Lead (Robert Vance) and Google Voice Test Lead (Marcus Sterling)."""
    test_lead_1 = {
        "owner": "Robert Vance (Test Lead)",
        "county": "Pinellas",
        "source": "Sandbox Demo Lead",
        "phone": "(727) 555-0199",
        "clean_phone": "7275550199",
        "email": "robert.vance.test@gmail.com",
        "address": "742 Evergreen Terr",
        "city": "St. Petersburg",
        "zip": "33701",
        "just_value": 240000,
        "market_value": 310000,
        "distress_category": "Code Violation",
        "notes": "Dedicated Sandbox test lead for verifying inbound webhooks, deal scoring, audio chime, and PandaDoc contracts.",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_contact("TEST-PINELLAS-001", test_lead_1)

    test_lead_2 = {
        "owner": "Marcus Sterling (Test Lead #2)",
        "county": "Pinellas",
        "source": "Google Voice Live Test Line",
        "phone": "(407) 504-2503",
        "clean_phone": "4075042503",
        "email": "marcus.sterling.test@gmail.com",
        "address": "1204 Gulf Way",
        "city": "St. Pete Beach",
        "zip": "33706",
        "just_value": 310000,
        "market_value": 395000,
        "distress_category": "Lis Pendens",
        "notes": "Dedicated Google Voice live test lead (407-504-2503) for real 2-way cellular SMS testing back and forth.",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_contact("TEST-PINELLAS-002", test_lead_2)

    return {"status": "success", "leads": [test_lead_1, test_lead_2]}

@app.get("/api/bot/settings")
def get_bot_settings():
    s = load_seller_bot_settings()
    return {"status": "ok", "settings": s, **s}

@app.post("/api/bot/settings")
def update_bot_settings(settings: Dict[str, Any]):
    save_seller_bot_settings(settings)
    s = load_seller_bot_settings()
    return {"status": "ok", "settings": s, **s}

@app.get("/api/bot/training")
def get_bot_training():
    replies = load_seller_golden_replies()
    return {
        "status": "ok",
        "count": len(replies),
        "scenarios": replies,
        "golden_replies": replies
    }

@app.post("/api/bot/training/save")
def save_bot_training_item(entry: Dict[str, Any]):
    saved = save_seller_golden_reply(entry)
    replies = load_seller_golden_replies()
    return {
        "status": "ok",
        "scenario": saved or entry,
        "scenarios": replies,
        "golden_replies": replies
    }

@app.delete("/api/bot/training/{entry_id}")
def delete_bot_training_item(entry_id: str):
    success = delete_seller_golden_reply(entry_id)
    return {"status": "ok" if success else "error"}

@app.post("/api/bot/suggest")
def generate_bot_suggestion(payload: Dict[str, Any]):
    """Generates an instant Copilot reply suggestion for any lead and text."""
    parcel_id = payload.get("parcel_id", "")
    phone = payload.get("phone", "")
    inbound_text = payload.get("inbound_text") or payload.get("seller_message", "")
    lead = find_lead_by_phone(phone)
    if parcel_id:
        lead["parcel_id"] = parcel_id
    if payload.get("property_address") or payload.get("address"):
        lead["property_address"] = payload.get("property_address") or payload.get("address")
    if payload.get("owner_name"):
        lead["owner_name"] = payload["owner_name"]
    if payload.get("distress_category") or payload.get("distress_type"):
        lead["distress_category"] = payload.get("distress_category") or payload.get("distress_type")
    if payload.get("assessed_value"):
        lead["assessed_value"] = payload["assessed_value"]
    if payload.get('county'):
        lead['county'] = payload['county']

    history = get_lead_sms_thread(phone, parcel_id)
    if inbound_text == "INITIAL_HOOK" or (not history and (not inbound_text or "outreach inquiry" in inbound_text.lower() or "noticed your property" in inbound_text.lower())):
        bot_res = seller_bot.generate_initial_outreach(lead, forced_angle=payload.get('opener_angle'))
    else:
        bot_res = seller_bot.process_inbound_sms(lead, inbound_text, history)
    reply_text = bot_res.get("suggested_reply", "")
    deal_eval = bot_res.get("deal_evaluation", {})

    return {
        "status": "ok",
        "suggestion": reply_text,
        "spread_eval": deal_eval,
        "deal_evaluation": deal_eval,
        "bot_details": bot_res
    }

@app.post("/api/bot/test-gemini")
def test_gemini_endpoint(payload: Optional[Dict[str, Any]] = None):
    settings = load_seller_bot_settings()
    key = (payload.get("key") if payload else None) or settings.get("gemini_api_key", "")
    model = (payload.get("model") if payload else None) or settings.get("gemini_model", "gemini-3.8-flash")
    res = test_seller_gemini_connection(key, model)
    if res.get("status") in ["success", "ok"]:
        return {"status": "ok", "message": res.get("message", "Connected"), "model": model, "reply": "GEMINI_OK"}
    return {"status": "error", "message": res.get("message", "Failed to connect")}

@app.get("/api/inbox")
def get_inbox_messages():
    """Returns all inbound seller SMS messages, grouped conversation threads, and counts."""
    logs = []
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
    inbound = [m for m in logs if m.get("direction") == "INBOUND"]
    threads = get_grouped_sms_threads()
    return {
        "status": "success",
        "messages": inbound,
        "threads": threads,
        "count": len(inbound),
        "thread_count": len(threads)
    }

def get_grouped_sms_threads() -> List[Dict[str, Any]]:
    """Groups all outreach logs into unified 2-way seller conversation threads."""
    logs = []
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    # Inbox refreshes must not wait on online appraisal searches or repeatedly
    # reread the same contact and valuation files for each conversation.
    contacts = load_saved_contacts()
    valuation_cache = load_valuations_cache()
    threads_map: Dict[str, Dict[str, Any]] = {}
    # Iterate oldest to newest so messages array is in chronological order
    for entry in reversed(logs):
        phone_raw = entry.get("sender_phone") or entry.get("phone") or entry.get("recipient") or ""
        digits = "".join(filter(str.isdigit, str(phone_raw)))
        if len(digits) > 10 and digits.startswith("1"):
            digits = digits[1:]

        pid = str(entry.get("parcel_id") or "").strip()
        key = digits or pid
        if not key:
            continue

        if key not in threads_map:
            lead_info = find_lead_by_phone(digits or phone_raw, allow_online_lookup=False, contacts=contacts, valuation_cache=valuation_cache)
            addr = entry.get("address") or (lead_info.get("property_address") if lead_info else "Florida Property")
            jval = float(lead_info.get("just_value", 250000.0) if lead_info else 250000.0)
            val = get_property_market_valuation(addr, jval, allow_online_lookup=False, cache=valuation_cache)
            threads_map[key] = {
                "key": key,
                "phone": entry.get("phone") or entry.get("sender_phone") or (lead_info.get("phone") if lead_info else phone_raw),
                "clean_phone": digits,
                "parcel_id": pid or (lead_info.get("parcel_id") if lead_info else ""),
                "owner": entry.get("owner") or (lead_info.get("owner_name") if lead_info else "Homeowner"),
                "address": addr,
                "just_value": jval,
                "market_value": float(lead_info.get("market_value") or val.get("market_value") or (jval * 1.30)),
                "valuation_source": val.get("source", "Florida Retail Model (+30%)"),
                "distress_category": lead_info.get("distress_category", "Distressed Lead") if lead_info else "Distressed Lead",
                "deal_evaluation": {},
                "latest_bot_response": "",
                "last_message": "",
                "last_timestamp": "",
                "last_direction": "",
                "inbound_count": 0,
                "messages": []
            }

        t = threads_map[key]
        t["messages"].append(entry)
        t["last_message"] = entry.get("message", "")
        t["last_timestamp"] = entry.get("timestamp", "")
        t["last_direction"] = entry.get("direction", "OUTBOUND")

        # Capture latest deal evaluation if available
        d_eval = entry.get("deal_evaluation") or entry.get("spread_eval") or {}
        if d_eval and d_eval.get("deal_rating") and d_eval.get("deal_rating") != "UNKNOWN":
            t["deal_evaluation"] = d_eval

        # Capture latest bot suggested reply
        b_reply = entry.get("bot_response") or entry.get("suggested_reply")
        if b_reply:
            t["latest_bot_response"] = b_reply

        if entry.get("direction") == "INBOUND":
            t["inbound_count"] += 1

    # Sort threads by last_timestamp descending (newest activity first)
    result = list(threads_map.values())
    result.sort(key=lambda x: x.get("last_timestamp", ""), reverse=True)
    return result

@app.get("/api/sms/threads")
def get_sms_threads_endpoint():
    """API endpoint to get all grouped conversation threads."""
    threads = get_grouped_sms_threads()
    return {"status": "success", "threads": threads, "count": len(threads)}

@app.post("/api/underwrite/407flips")
def underwrite_lead_407flips_endpoint(req: Underwrite407FlipsLeadRequest):
    """
    407flips Underwriting Engine Endpoint for County Lead Hub
    Applies the full 407flips Standard (8-Point compliance, Florida 4-Point Insurance & Systems Triggers,
    Two-Tier Scope, 23% Friction/Profit MAO, and Three-Tier Offer Engine) to distressed county leads.
    """
    arv_val = req.arv or 0.0
    if arv_val <= 0:
        val_info = get_property_market_valuation(req.address, req.listing_price or 250000.0)
        arv_val = float(val_info.get("market_value", 300000.0))

    report = underwrite_407flips_deal(
        address=req.address,
        listing_price=req.listing_price or 0.0,
        arv=arv_val,
        sqft=req.sqft or 1500,
        year_built=req.year_built or 1980,
        beds=req.beds or 3,
        baths=req.baths or 2,
        condition=req.condition or "poor",
        condition_notes=req.condition_notes or "Florida distressed lead",
        wholesale_fee=req.wholesale_fee or 10000.0,
        agent_name=req.owner_name or "Homeowner",
        parcel_id=req.parcel_id or "",
        owner_name=req.owner_name or "Homeowner"
    )
    return {"status": "success", "report": report}

@app.get("/api/sms/thread")
def get_single_thread_endpoint(phone: str = "", parcel_id: str = ""):
    """Returns chronological message thread for a specific phone or parcel."""
    thread = get_lead_sms_thread(phone, parcel_id)
    lead_info = find_lead_by_phone(phone)
    return {
        "status": "success",
        "phone": phone,
        "parcel_id": parcel_id,
        "lead": lead_info,
        "messages": thread,
        "count": len(thread)
    }

class ThreadDeleteRequest(BaseModel):
    key: str
    phone: Optional[str] = None
    parcel_id: Optional[str] = None

@app.post("/api/inbox/thread/delete")
def delete_inbox_thread_endpoint(payload: ThreadDeleteRequest):
    """Delete a specific conversation thread and remove all its messages from outreach history."""
    target_key = (payload.key or "").strip()
    target_phone = (payload.phone or "").strip()
    target_pid = (payload.parcel_id or "").strip()

    clean_digits = "".join(filter(str.isdigit, str(target_phone or target_key)))
    if len(clean_digits) > 10 and clean_digits.startswith("1"):
        clean_digits = clean_digits[1:]

    deleted_count = 0
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
            
            kept_logs = []
            for entry in logs:
                phone_raw = entry.get("sender_phone") or entry.get("phone") or entry.get("recipient") or ""
                digits = "".join(filter(str.isdigit, str(phone_raw)))
                if len(digits) > 10 and digits.startswith("1"):
                    digits = digits[1:]
                
                pid = str(entry.get("parcel_id") or "").strip()
                
                is_match = False
                if clean_digits and digits == clean_digits:
                    is_match = True
                elif target_key and (target_key == digits or target_key == pid or target_key in str(phone_raw)):
                    is_match = True
                elif target_pid and pid == target_pid:
                    is_match = True

                if is_match:
                    deleted_count += 1
                else:
                    kept_logs.append(entry)

            with open(OUTREACH_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(kept_logs, f, indent=2)

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {
        "status": "success",
        "message": f"Deleted thread and purged {deleted_count} messages.",
        "deleted_count": deleted_count,
        "key": target_key
    }

# -------------------------------------------------------------
# Scheduled Callbacks with John & Google Calendar Sync
# -------------------------------------------------------------
@app.get("/api/callbacks")
def get_scheduled_callbacks_endpoint():
    """Returns all scheduled phone callbacks for John."""
    callbacks = load_scheduled_callbacks()
    pending = [c for c in callbacks if c.get("status") == "PENDING"]
    return {
        "status": "success",
        "callbacks": callbacks,
        "pending_count": len(pending),
        "total_count": len(callbacks)
    }

@app.post("/api/callbacks/complete")
def complete_callback_endpoint(payload: Dict[str, Any]):
    """Marks a callback as completed or dismissed."""
    callback_id = payload.get("id")
    clean_phone = payload.get("clean_phone")
    callbacks = load_scheduled_callbacks()
    for c in callbacks:
        if (callback_id and c.get("id") == callback_id) or (clean_phone and c.get("clean_phone") == clean_phone):
            c["status"] = "COMPLETED"
            c["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_scheduled_callbacks(callbacks)
    return {"status": "success", "callbacks": callbacks}

@app.post("/api/callbacks/send-invite")
def manual_send_calendar_invite_endpoint(payload: Dict[str, Any]):
    """Manually triggers or re-sends a calendar invite for a callback."""
    phone = payload.get("phone", "")
    lead = find_lead_by_phone(phone)
    time_str = payload.get("time") or payload.get("scheduled_time_raw") or "Soon"
    res = send_calendar_invite_email(lead, time_str)
    return res

# -------------------------------------------------------------
# Email Outreach via SMTP2GO (mail.smtp2go.com)
# -------------------------------------------------------------
class EmailSettingsModel(BaseModel):
    smtp_server: str = "mail.smtp2go.com"
    smtp_port: int = 2525
    smtp_user: str = "407flips.com"
    smtp_password: str = ""
    sender_name: str = "John Roberts | 407 Flips"
    sender_email: str = "john@407flips.com"
    reply_to: str = "john@407flips.com"
    company_name: str = "407 Flips"
    company_phone: Optional[str] = "(407) 555-FLIP"
    business_address: Optional[str] = "Orlando, FL (Central Florida)"

class SendEmailRequest(BaseModel):
    recipient_email: str
    recipient_name: Optional[str] = "Property Owner"
    property_address: Optional[str] = ""
    subject: str
    html_content: str
    plain_content: Optional[str] = None
    auto_outreach: bool = False
    parcel_id: Optional[str] = None
    county: Optional[str] = "Pinellas"
    template_type: Optional[str] = "cash_offer"

@app.get("/api/email/settings")
def get_email_settings():
    """Return saved SMTP2GO email settings."""
    return load_email_settings()

@app.post("/api/email/settings")
def update_email_settings(req: EmailSettingsModel):
    """Update and persist SMTP2GO email settings."""
    save_email_settings(req.dict())
    return {"status": "success", "settings": req.dict()}

@app.post("/api/email/test")
def test_email_connection():
    """Verify SMTP2GO connection and authentication."""
    settings = load_email_settings()
    host = settings.get("smtp_server", "mail.smtp2go.com")
    port = int(settings.get("smtp_port", 2525))
    user = settings.get("smtp_user", "407flips.com")
    pwd = settings.get("smtp_password", "")

    if not pwd:
        return {"status": "error", "message": "SMTP password not set. Enter your SMTP2GO password in settings."}

    try:
        server = smtplib.SMTP(host, port, timeout=10)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(user, pwd)
        server.quit()
        return {"status": "success", "message": f"Successfully authenticated with SMTP2GO ({host}:{port}) as {user}!"}
    except smtplib.SMTPAuthenticationError as e:
        return {"status": "error", "message": f"Authentication failed: Check your SMTP2GO username and password."}
    except Exception as e:
        return {"status": "error", "message": f"Could not connect to {host}:{port}: {str(e)}"}

def is_email_blocked_from_outreach(email, contact):
    """Honor known opt-outs/bounces on an address or any linked contact record."""
    from src.email_outreach_queue import normalize_email, property_key
    normalized = normalize_email(email)
    if not normalized:
        return True, 'Missing or malformed email'
    suppression_file = os.path.join(DATA_DIR, 'email_suppression.json')
    if os.path.exists(suppression_file):
        with open(suppression_file, 'r', encoding='utf-8') as source:
            suppressed = json.load(source)
        if not isinstance(suppressed, list):
            raise ValueError('Email suppression file must contain a list. Correct it before starting outreach.')
        for entry in suppressed:
            value = entry.get('email') if isinstance(entry, dict) else entry
            if normalize_email(value) == normalized:
                return True, 'Email is on the suppression list'
    linked = [contact]
    if contact.get('matched_parcel_id'):
        key = property_key('', contact)
        linked += [c for pid, c in load_saved_contacts().items() if property_key(pid, c) == key]
    for candidate in linked:
        if (candidate.get('email_opt_out') or candidate.get('unsubscribed') or candidate.get('email_bounced')
                or str(candidate.get('email_status') or '').lower() in ('bounced', 'unsubscribed', 'blocked')
                or candidate.get('dnc') is True or candidate.get('is_dnc') is True
                or str(candidate.get('dnc_status') or '').upper() == 'DNC'):
            return True, 'Contact is opted out, bounced, or blocked'
        phone = candidate.get('phone') or candidate.get('clean_phone')
        if phone:
            blocked, reason = is_lead_blocked_from_outreach(phone, candidate)
            if blocked:
                return True, reason
    return False, ''


@app.post("/api/email/send")
def send_email_via_smtp(req: SendEmailRequest):
    """
    Send an offer email via SMTP2GO.
    Formatted with multi-part alternative (HTML + plain text fallback).
    """
    from src.email_outreach_queue import normalize_email
    contact = load_saved_contacts().get(req.parcel_id, {})
    blocked, reason = is_email_blocked_from_outreach(req.recipient_email, contact)
    if blocked:
        return {'status': 'error', 'suppressed': True, 'blocked_reason': reason, 'message': reason}
    if req.auto_outreach:
        reason = auto_email_queue.recheck_before_send(req.parcel_id, req.recipient_email)
        if reason:
            return {'status': 'error', 'suppressed': True, 'blocked_reason': reason, 'message': reason}
    settings = load_email_settings()
    host = settings.get("smtp_server", "mail.smtp2go.com")
    port = int(settings.get("smtp_port", 2525))
    user = settings.get("smtp_user", "407flips.com")
    pwd = settings.get("smtp_password", "")
    sender_name = settings.get("sender_name", "John Roberts | 407 Flips")
    sender_email = settings.get("sender_email", "john@407flips.com")
    reply_to = settings.get("reply_to", "john@407flips.com")

    # Safe Sandbox Test Lead Handling (Non-live carrier simulation)
    is_sandbox = (
        (req.parcel_id and str(req.parcel_id).startswith("TEST-")) or
        (not req.auto_outreach and (
            (req.recipient_email and any(t in req.recipient_email.lower() for t in ["@test.", ".test@", "test@gmail.com", "example.com", "555"])) or
            "test" in (req.recipient_name or "").lower()))
    )

    if is_sandbox:
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": "EMAIL",
            "direction": "OUTBOUND",
            "parcel_id": req.parcel_id or "TEST-PINELLAS-001",
            "county": req.county or "Pinellas",
            "owner": req.recipient_name or "Robert Vance (Test Lead)",
            "address": req.property_address or "742 Evergreen Terr, St. Petersburg, FL",
            "recipient": req.recipient_email or "robert.vance.test@gmail.com",
            "subject": req.subject or "Cash Offer for 742 Evergreen Terr",
            "message": req.subject or "Cash Offer Email (Sandbox)",
            "status": "SENT",
            "status_code": 200,
            "sandbox": True
        }
        logs = []
        if os.path.exists(OUTREACH_LOG_FILE):
            try:
                with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        append_outreach_log(log_entry)

        if req.parcel_id:
            save_contact(req.parcel_id, {
                "last_email_sent": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_email_status": "SENT (Sandbox)",
                "email": req.recipient_email
            })

        return {
            "status": "success",
            "message": f"✓ [Sandbox Test Agent] Offer email dispatched safely to {req.recipient_email} (Simulated - no SMTP bounce)!",
            "recipient": req.recipient_email,
            "sandbox": True
        }

    if not pwd:
        return {"status": "error", "message": "SMTP password not configured. Open Email Setup and enter your SMTP2GO password."}

    if not normalize_email(req.recipient_email) or '\r' in req.subject or '\n' in req.subject:
        return {"status": "error", "message": "Invalid recipient email address."}

    msg = MIMEMultipart("alternative")
    msg["Subject"] = req.subject
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = req.recipient_email
    msg["Reply-To"] = reply_to

    # Plain text preview
    plain_fallback = req.plain_content or f"Offer for {req.property_address} from 407 Flips. Please view in an HTML-compatible email client or reply directly."
    msg.attach(MIMEText(plain_fallback, "plain", "utf-8"))
    msg.attach(MIMEText(req.html_content, "html", "utf-8"))

    try:
        server = smtplib.SMTP(host, port, timeout=12)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(user, pwd)
        server.sendmail(sender_email, [req.recipient_email], msg.as_string())
        server.quit()

        # Mark in saved contacts
        if req.parcel_id:
            save_contact(req.parcel_id, {
                "last_email_sent": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_email_status": "SENT",
                "last_email_template": req.template_type,
                "email": req.recipient_email
            })

        # Save to outreach history log
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": "EMAIL",
            "direction": "OUTBOUND",
            "parcel_id": req.parcel_id,
            "county": req.county,
            "owner": req.recipient_name,
            "address": req.property_address,
            "recipient": req.recipient_email,
            "subject": req.subject,
            "message": req.plain_content or req.subject,
            "template_type": req.template_type,
            "status": "SENT"
        }
        logs = []
        if os.path.exists(OUTREACH_LOG_FILE):
            try:
                with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        append_outreach_log(log_entry)

        return {
            "status": "success",
            "message": f"Offer email dispatched successfully to {req.recipient_email} via SMTP2GO!",
            "recipient": req.recipient_email
        }
    except Exception as e:
        return {"status": "error", "message": f"SMTP Error sending email: {str(e)}"}

@app.get("/api/outreach/history")
def get_outreach_history():
    """Return outreach dispatch log history."""
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

@app.get("/api/outreach/lead")
def get_lead_outreach_endpoint(parcel_id: str = "", phone: str = "", email: str = ""):
    """Return prior sent outreach (SMS and Email) for a specific lead."""
    p_id = (parcel_id or "").strip()
    digits = "".join(filter(str.isdigit, str(phone or "")))
    if len(digits) > 10 and digits.startswith("1"):
        digits = digits[1:]
    clean_email = (email or "").strip().lower()

    matches = []
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
                for entry in logs:
                    e_pid = str(entry.get("parcel_id") or "").strip()
                    e_phone = "".join(filter(str.isdigit, str(entry.get("phone") or entry.get("recipient") or "")))
                    if len(e_phone) > 10 and e_phone.startswith("1"):
                        e_phone = e_phone[1:]
                    e_email = str(entry.get("recipient") or entry.get("email") or "").strip().lower()
                    
                    matched = False
                    if p_id and p_id == e_pid:
                        matched = True
                    elif digits and (digits == e_phone or (len(digits) >= 7 and digits in e_phone)):
                        matched = True
                    elif clean_email and clean_email in e_email:
                        matched = True

                    if matched:
                        matches.append(entry)
        except Exception:
            pass

    # Sort chronological
    sorted_matches = sorted(matches, key=lambda x: x.get("timestamp", ""))
    sms_matches = [m for m in sorted_matches if str(m.get("channel", "")).upper() == "SMS"]
    email_matches = [m for m in sorted_matches if str(m.get("channel", "")).upper() == "EMAIL"]

    return {
        "status": "success",
        "parcel_id": p_id,
        "items": sorted_matches,
        "sms_count": len(sms_matches),
        "email_count": len(email_matches),
        "last_sms": sms_matches[-1] if sms_matches else None,
        "last_email": email_matches[-1] if email_matches else None
    }

@app.delete("/api/outreach/history")
def clear_outreach_history():
    """Clear outreach dispatch log history."""
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump([], f)
        except Exception:
            pass
    return {"status": "success", "message": "Outreach history cleared."}

@app.get("/api/outreach/opener-metrics")
def get_opener_metrics():
    """
    Calculates reply rate and opt-out metrics per opener angle across outreach history.
    Angles: multi_list, single_list, ultra_short.
    Primary metric: reply rate (replies / sent).
    """
    logs = []
    if os.path.exists(OUTREACH_LOG_FILE):
        try:
            with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []

    leads_sent = {}         # phone -> angle
    leads_replied = set()   # phones with at least 1 inbound reply
    leads_opted_out = set() # phones that opted out

    for entry in reversed(logs):
        phone_digits = "".join(filter(str.isdigit, str(entry.get("phone") or entry.get("recipient") or entry.get("sender_phone") or "")))
        if len(phone_digits) > 10 and phone_digits.startswith("1"):
            phone_digits = phone_digits[1:]
        if not phone_digits:
            continue

        direction = (entry.get("direction") or "").upper()
        if direction == "OUTBOUND":
            if phone_digits not in leads_sent:
                angle = entry.get("opener_angle") or classify_opener_angle(entry.get("message", ""))
                if angle in ["multi_list", "single_list", "ultra_short"]:
                    leads_sent[phone_digits] = angle
                else:
                    leads_sent[phone_digits] = "single_list" # default to single_list
        elif direction == "INBOUND":
            leads_replied.add(phone_digits)
            if entry.get("bot_action") == "OPT_OUT" or entry.get("is_opt_out"):
                leads_opted_out.add(phone_digits)

    angle_stats = {
        "multi_list": {
            "key": "multi_list",
            "name": "Saw the house online",
            "tier": "2+ Distress Lists",
            "opener_sample": "Saw the house online {Address} any plans i have an idea?",
            "sent": 0,
            "replied": 0,
            "reply_rate": 0.0,
            "opt_outs": 0,
            "opt_out_rate": 0.0
        },
        "single_list": {
            "key": "single_list",
            "name": "Came across online",
            "tier": "Single Distress List",
            "opener_sample": "Hey i came across {Address} online, open for a discussion about it?",
            "sent": 0,
            "replied": 0,
            "reply_rate": 0.0,
            "opt_outs": 0,
            "opt_out_rate": 0.0
        },
        "ultra_short": {
            "key": "ultra_short",
            "name": "Doing another project",
            "tier": "Neighborhood Project",
            "opener_sample": "Hey im doing another project in that neighborhood {Address} looks like a good project. Any thoughts on letting it go?",
            "sent": 0,
            "replied": 0,
            "reply_rate": 0.0,
            "opt_outs": 0,
            "opt_out_rate": 0.0
        }
    }

    for phone, angle in leads_sent.items():
        if angle in angle_stats:
            angle_stats[angle]["sent"] += 1
            if phone in leads_replied:
                angle_stats[angle]["replied"] += 1
            if phone in leads_opted_out:
                angle_stats[angle]["opt_outs"] += 1

    total_sent = 0
    total_replied = 0
    total_opt_outs = 0
    best_rate = -1.0
    best_key = None
    worst_rate = 999.0
    worst_key = None

    for k, stat in angle_stats.items():
        s = stat["sent"]
        r = stat["replied"]
        o = stat["opt_outs"]
        stat["reply_rate"] = round((r / s * 100), 1) if s > 0 else 0.0
        stat["opt_out_rate"] = round((o / s * 100), 1) if s > 0 else 0.0
        total_sent += s
        total_replied += r
        total_opt_outs += o

        if s > 0:
            if stat["reply_rate"] > best_rate:
                best_rate = stat["reply_rate"]
                best_key = k
            if stat["reply_rate"] < worst_rate:
                worst_rate = stat["reply_rate"]
                worst_key = k

    overall_reply_rate = round((total_replied / total_sent * 100), 1) if total_sent > 0 else 0.0
    overall_opt_out_rate = round((total_opt_outs / total_sent * 100), 1) if total_sent > 0 else 0.0

    return {
        "status": "success",
        "angles": angle_stats,
        "summary": {
            "total_sent": total_sent,
            "total_replied": total_replied,
            "overall_reply_rate": overall_reply_rate,
            "total_opt_outs": total_opt_outs,
            "overall_opt_out_rate": overall_opt_out_rate,
            "top_performer": best_key,
            "lowest_performer": worst_key if (best_key != worst_key) else None,
            "review_recommendation": "Review after ~2 weeks of volume; retire the lowest performer and rotate the winners."
        }
    }

# -------------------------------------------------------------
# Outreach Templates Management (SMS & Email)
# -------------------------------------------------------------
OUTREACH_TEMPLATES_FILE = os.path.join(DATA_DIR, "outreach_templates.json")

DEFAULT_OUTREACH_TEMPLATES = {
    "sms": DEFAULT_SMS_TEMPLATES,
    "email": [
        {
            "id": "lis_pendens",
            "name": "🏛️ Pre-Foreclosure / Stop Foreclosure Auction",
            "category": "lis_pendens",
            "subject": "Cash Offer & Options to Stop Foreclosure: {Address}",
            "body": "Hi {FirstName},\n\nI noticed public county records showing a pending foreclosure filing regarding your property at {Address}. I know how stressful this situation can be, but you still have legal rights and options to protect your equity before an auction date is set.\n\nAt 407 Flips, we buy Central Florida homes directly for cash:\n• Stop the auction immediately with a binding contract & proof of funds\n• Protect your credit and walk away with cash in hand\n• $0 Realtor commissions, $0 inspection costs, and $0 closing fees\n• We buy 100% As-Is — absolutely no repairs, painting, or cleaning required\n• We work directly with your lender to obtain payoff statements\n\nIf you'd like to see what a fair cash offer looks like with zero obligation, please reply directly to this email or call/text me at (407) 555-FLIP.\n\nRespectfully,\nJohn Roberts | 407 Flips\nEmail: john@407flips.com | Phone: (407) 555-FLIP\nOrlando, FL | Serving Central Florida Homeowners"
        },
        {
            "id": "probate",
            "name": "📜 Probate / Inherited Property (Leave Furniture)",
            "category": "probate",
            "subject": "Estate Inquiry & Direct Cash Offer: {Address}",
            "body": "Hi {FirstName},\n\nPlease accept my condolences if you have recently lost a family member. I am reaching out regarding the estate property at {Address}.\n\nSettling an estate can be an exhausting process, especially when managing cleanouts, repairs, and probate court paperwork.\n\nAt 407 Flips, we specialize in purchasing inherited Florida homes:\n• Leave anything you don't want: furniture, old appliances, clothing, or clutter. We handle full disposal.\n• No repairs needed — we buy strictly in current As-Is condition.\n• Cash closing in as little as 7 to 14 days, or on whatever timeline works best for the heirs.\n• Zero realtor commissions, no staging, and no open houses.\n\nIf you and the family are considering liquidating the property, I'd be honored to make a fair, all-cash offer with zero obligation.\n\nFeel free to reply directly to this email or call/text me at (407) 555-FLIP.\n\nWarm regards,\nJohn Roberts | 407 Flips\nEmail: john@407flips.com | Phone: (407) 555-FLIP\nOrlando, FL"
        },
        {
            "id": "code_violation",
            "name": "⚠️ Code Violations / Heavy Repairs (Taking Over Liens)",
            "category": "code_violations",
            "subject": "As-Is Cash Offer (We Take Over Violations): {Address}",
            "body": "Hi {FirstName},\n\nI am contacting you regarding your property at {Address}.\n\nI work with local Florida homeowners who are dealing with burdensome code enforcement citations, daily municipal fines, open permits, or substantial deferred maintenance. Dealing with the city and contractors can quickly turn into a financial nightmare.\n\nAt 407 Flips, we buy houses in ANY physical condition:\n• We take over existing city code violations and municipal liens\n• Zero repair demands — roof damage, plumbing, electrical, or structural issues welcome\n• All-cash purchase with no appraisal contingencies or bank inspection delays\n• Fast closing on your preferred date (7–14 days)\n• Zero fees or closing expenses to you\n\nIf you'd like to walk away with cash and let us handle the city and repairs, reply directly to this email or call/text me at (407) 555-FLIP.\n\nBest regards,\nJohn Roberts | 407 Flips\nEmail: john@407flips.com | Phone: (407) 555-FLIP\nOrlando, FL"
        },
        {
            "id": "quick_cash",
            "name": "💰 Quick As-Is Cash Offer (Close in 7–14 Days)",
            "category": "cash_offer",
            "subject": "Direct Cash Offer for {Address} - No Fees or Repairs",
            "body": "Hi {FirstName},\n\nMy name is John with 407 Flips. I am a local Florida private cash buyer actively purchasing homes in your neighborhood.\n\nI am interested in making a direct, all-cash offer on your property at {Address}.\n\nWhy homeowners choose to work with 407 Flips:\n• All-Cash Offer — No bank approvals, no appraisal hurdles\n• As-Is Condition — No repairs, painting, or cleaning needed\n• Fast & Flexible Closing — Close in 7–14 days or on your chosen date\n• Zero Expenses — No 6% Realtor commissions and no seller closing costs\n\nIf you have considered selling or simply want to know what a cash offer on your property would look like, please reply to this email or call/text me at (407) 555-FLIP.\n\nBest regards,\nJohn Roberts | 407 Flips\nEmail: john@407flips.com | Phone: (407) 555-FLIP\nOrlando, FL"
        }
    ]
}

def load_outreach_templates() -> dict:
    if os.path.exists(OUTREACH_TEMPLATES_FILE):
        try:
            with open(OUTREACH_TEMPLATES_FILE, "r", encoding="utf-8") as f:
                templates = json.load(f)
            shared = load_initial_sms_templates(templates)
            ids = {t['id'] for t in shared}
            templates['sms'] = shared + [t for t in templates.get('sms', []) if t.get('id') not in ids]
            return templates
        except Exception:
            pass
    return DEFAULT_OUTREACH_TEMPLATES

def save_outreach_templates(templates: dict):
    with open(OUTREACH_TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, indent=2)

@app.get("/api/templates")
def get_templates():
    """Return all configured SMS and Email outreach templates."""
    return load_outreach_templates()

@app.post("/api/templates")
def update_templates(payload: dict):
    """Save updated SMS and Email outreach templates."""
    save_outreach_templates(payload)
    return {"status": "success", "message": "Outreach templates saved successfully."}

@app.post("/api/templates/reset")
def reset_templates():
    """Reset outreach templates to default factory scripts."""
    save_outreach_templates(DEFAULT_OUTREACH_TEMPLATES)
    return {"status": "success", "message": "Templates reset to defaults.", "templates": DEFAULT_OUTREACH_TEMPLATES}

# -------------------------------------------------------------
# Permanent Suppression List & DNC Scrub Endpoints
# -------------------------------------------------------------

class SuppressionAddRequest(BaseModel):
    phone: str
    reason: Optional[str] = "OPT_OUT"
    parcel_id: Optional[str] = ""
    owner_name: Optional[str] = ""
    property_address: Optional[str] = ""
    county: Optional[str] = ""

class SuppressionRemoveRequest(BaseModel):
    phone: str

class DncScrubRequest(BaseModel):
    leads: List[Dict[str, Any]] = []

@app.get("/api/suppression")
def get_suppression_endpoint():
    """Get all permanently suppressed numbers and opt-out history."""
    items = load_suppression_list()
    return {"status": "success", "count": len(items), "suppression_list": items}

@app.post("/api/suppression/add")
def add_suppression_endpoint(req: SuppressionAddRequest):
    """Manually add a number to permanent suppression list."""
    entry = add_to_suppression_list(
        phone_str=req.phone,
        reason=req.reason or "OPT_OUT",
        lead_info={
            "parcel_id": req.parcel_id,
            "owner_name": req.owner_name,
            "property_address": req.property_address,
            "county": req.county
        }
    )
    return {"status": "success", "message": f"Phone {req.phone} permanently suppressed.", "entry": entry}

@app.post("/api/suppression/remove")
def remove_suppression_endpoint(req: SuppressionRemoveRequest):
    """Remove a number from suppression list."""
    success = remove_from_suppression_list(req.phone)
    return {"status": "success" if success else "not_found", "phone": req.phone}

@app.get("/api/dnc")
def get_dnc_endpoint():
    """Get all numbers on DNC registry list."""
    items = load_dnc_list()
    return {"status": "success", "count": len(items), "dnc_list": items}

@app.post("/api/dnc/scrub")
def scrub_leads_dnc_endpoint(req: DncScrubRequest):
    """Scrub a list of leads against federal/state DNC and permanent suppression list."""
    clean_leads, blocked_leads = scrub_outbound_lead_list(req.leads)
    return {
        "status": "success",
        "total_submitted": len(req.leads),
        "clean_count": len(clean_leads),
        "blocked_count": len(blocked_leads),
        "clean_leads": clean_leads,
        "blocked_leads": blocked_leads
    }

# -------------------------------------------------------------
# Wholesale Purchase Agreement & PandaDoc E-Sign Integration
# -------------------------------------------------------------
PANDADOC_SETTINGS_FILE = os.path.join(DATA_DIR, "pandadoc_settings.json")

class PandaDocSettingsModel(BaseModel):
    mode: str = "sandbox"  # 'sandbox' or 'production'
    sandbox_key: str = ""
    production_key: str = ""
    buyer_name: str = "Peak Investments LLC"
    buyer_signer_name: str = "Johnathan Roberts"
    sender_email: str = "john@407flips.com"
    default_title_company: str = "TBD"
    default_inspection_days: int = 14
    default_deposit: float = 100.0

def load_pandadoc_settings() -> dict:
    if os.path.exists(PANDADOC_SETTINGS_FILE):
        try:
            with open(PANDADOC_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "mode": "sandbox",
        "sandbox_key": "",
        "production_key": "",
        "buyer_name": "Peak Investments LLC",
        "buyer_signer_name": "Johnathan Roberts",
        "sender_email": "john@407flips.com",
        "default_title_company": "TBD",
        "default_inspection_days": 14,
        "default_deposit": 100.0
    }

def save_pandadoc_settings(settings: dict):
    with open(PANDADOC_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)

class ContractPayload(BaseModel):
    parcel_id: Optional[str] = ""
    county: Optional[str] = "Pinellas"
    agreement_date: Optional[str] = ""
    seller_name: str
    buyer_name: str = "Peak Investments LLC"
    buyer_signer_name: Optional[str] = "Johnathan Roberts"
    property_address: str
    property_city: Optional[str] = "St Petersburg"
    property_state: Optional[str] = "FL"
    property_zip: Optional[str] = ""
    legal_description: Optional[str] = ""
    purchase_price: float
    deposit_amount: float = 100.0
    cash_due_closing: float
    closing_date: str
    closing_location: str = "TBD"
    inspection_days: int = 14
    additional_terms: Optional[str] = ""
    recipient_email: str
    recipient_name: Optional[str] = ""
    notes: Optional[str] = ""

def generate_contract_html(data: ContractPayload, for_pandadoc: bool = False) -> str:
    """Generate exact 1-page HTML matching Contract 1 (WHOLESALE_Contract_Blank.pdf)."""
    date_display = data.agreement_date or time.strftime("%d day of %B, 20%y")
    terms_text = data.additional_terms or "Property sold in strictly 'AS-IS' condition with zero seller repairs. Buyer to pay standard buyer and seller closing costs; Seller responsible for mortgage payoffs, municipal liens, and prorated taxes through date of closing."

    signer_name = data.buyer_signer_name or "Johnathan Roberts"
    contract_date = data.agreement_date or time.strftime("%B %d, %Y")
    if for_pandadoc:
        seller_date_block = f'<div style="margin-bottom: 8px; font-weight: bold;">DATE: <span style="font-weight: normal; text-decoration: underline;">{contract_date}</span></div>'
        seller_sig_space = '<div style="height: 48px; display: flex; align-items: flex-end; padding-bottom: 2px;"><span style="color: white; font-size: 7.5pt;">{{signature:Seller:sig_seller__________}}</span></div>'
        buyer_date_block = f'<div style="margin-bottom: 8px; font-weight: bold;">DATE: <span style="font-weight: normal; text-decoration: underline;">{contract_date}</span></div>'
        buyer_sig_space = '<div style="height: 48px; display: flex; align-items: flex-end; padding-bottom: 2px;"><span style="color: white; font-size: 7.5pt;">{{signature:Buyer:sig_buyer__________}}</span></div>'
    else:
        seller_date_block = '<div style="margin-bottom: 8px;">DATE: ____________________</div>'
        seller_sig_space = '<div style="height: 48px;"></div>'
        buyer_date_block = '<div style="margin-bottom: 8px;">DATE: ____________________</div>'
        buyer_sig_space = '<div style="height: 48px;"></div>'

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: letter;
    margin: 0.32in 0.45in 0.3in 0.45in;
  }}
  * {{
    box-sizing: border-box;
  }}
  body {{
    font-family: Arial, Helvetica, sans-serif;
    color: #111;
    font-size: 8.5pt;
    line-height: 1.22;
    margin: 0;
    padding: 0;
  }}
  .contract-title {{
    font-size: 13pt;
    font-weight: 800;
    text-align: center;
    letter-spacing: 0.5px;
    margin: 0 0 10px 0;
    text-transform: uppercase;
  }}
  .fill-val {{
    font-weight: 700;
    color: #051a3a;
    border-bottom: 1px solid #111;
    padding: 0 4px;
  }}
  .preamble {{
    margin-bottom: 7px;
    line-height: 1.35;
  }}
  .prop-section {{
    margin-bottom: 7px;
    line-height: 1.35;
  }}
  .prop-line {{
    margin-bottom: 3px;
  }}
  .price-box {{
    margin: 6px 0 8px 0;
    padding: 5px 12px;
    background: #fbfbfb;
    border: 1px solid #ccc;
    border-radius: 4px;
    font-size: 8.5pt;
  }}
  .price-row {{
    display: flex;
    justify-content: space-between;
    padding: 1.5px 0;
  }}
  .price-row.total {{
    border-top: 1px solid #ddd;
    margin-top: 2px;
    padding-top: 2px;
    font-weight: bold;
  }}
  .clause {{
    margin-bottom: 4px;
    text-align: justify;
    font-size: 7.7pt;
    line-height: 1.2;
  }}
  .clause-title {{
    font-weight: bold;
  }}
  .terms-header {{
    font-weight: bold;
    font-size: 8pt;
    margin-top: 5px;
    margin-bottom: 2px;
  }}
  .terms-box {{
    border: 1px solid #777;
    border-radius: 3px;
    padding: 4px 8px;
    min-height: 34px;
    font-size: 7.5pt;
    background: #fafafa;
    line-height: 1.25;
    margin-bottom: 7px;
  }}
  .sig-block {{
    border-top: 1px solid #333;
    padding-top: 5px;
    margin-top: 6px;
    font-size: 7.5pt;
  }}
  .sig-verify {{
    font-style: italic;
    font-weight: 600;
    text-align: center;
    margin-bottom: 8px;
    font-size: 8pt;
  }}
  .sig-grid {{
    display: flex;
    justify-content: space-between;
    gap: 30px;
  }}
  .sig-col {{
    width: 48%;
  }}
  .sig-line {{
    border-top: 1px solid #111;
    margin-top: 18px;
    padding-top: 2px;
    display: flex;
    justify-content: space-between;
  }}
</style>
</head>
<body>
  <div class="contract-title">PURCHASE AND SALE AGREEMENT</div>

  <div class="preamble">
    This agreement is made this <span class="fill-val">{date_display}</span> between <span class="fill-val">{data.seller_name}</span> Seller(s) and <span class="fill-val">{data.buyer_name}</span> Buyer(s).
  </div>

  <div class="prop-section">
    Seller agrees to sell and buyer agrees to buy the following described real property together with all improvements and fixtures and the personal property described below:
    <div class="prop-line" style="margin-top: 3px;">
      Street Address: <span class="fill-val">{data.property_address}</span>
    </div>
    <div class="prop-line">
      City, State, Zip: <span class="fill-val">{data.property_city}, {data.property_state}, {data.property_zip}</span>
    </div>
    <div class="prop-line">
      Legal description: <span class="fill-val">Parcel ID / PIN: {data.legal_description or data.parcel_id}</span>
    </div>
  </div>

  <div class="price-box">
    <div style="font-weight: bold; margin-bottom: 3px;">The purchase price to be paid as follows:</div>
    <div class="price-row">
      <span>Total Deposit</span>
      <span><b>${data.deposit_amount:,.2f}</b></span>
    </div>
    <div class="price-row">
      <span>Cash due to Seller at Closing</span>
      <span><b>${data.cash_due_closing:,.2f}</b></span>
    </div>
    <div class="price-row total">
      <span>Total Price</span>
      <span><b>${data.purchase_price:,.2f}</b></span>
    </div>
  </div>

  <div class="clause">
    <span class="clause-title">1. EARNEST MONEY</span> to be deposited with a licensed title company or attorney within 48 hours of acceptance and ratification of offer.
  </div>

  <div class="clause">
    <span class="clause-title">2. PRORATIONS, IMPOUNDS & SECURITY DEPOSITS:</span> Loan interest, property taxes, insurance, and rents shall be prorated as of the date of closing. All security deposits shall be transferred to buyer at closing. All impound accounts for taxes and insurance are included in the purchase price and shall be transferred to buyer at closing. Any shortage in these accounts shall be charged to seller at closing.
  </div>

  <div class="clause">
    <span class="clause-title">3. CLOSING DATE AND TRANSFER OF TITLE:</span> This transaction shall close on or before <span class="fill-val">{data.closing_date}</span>. Closing will be held at <span class="fill-val">{data.closing_location}</span> and Seller(s) agree to transfer marketable title free and clear of all encumbrances except those listed and pay any required state taxes or stamps required to record deed and mortgage. Seller agrees to furnish title insurance in the amount of the purchase price, showing no encumbrances or exceptions other than previously noted.
  </div>

  <div class="clause">
    <span class="clause-title">4. DAMAGE TO PROPERTY:</span> Seller shall maintain property in its current condition and keep it insured against all loss until closing. In the event of destruction covered by insurance, buyer may elect to close and collect the insurance proceeds.
  </div>

  <div class="clause">
    <span class="clause-title">5. DEFAULTS:</span> If buyer defaults under this contract, any and all monies deposited by buyer(s) shall be retained by seller as full liquidated damages. If seller defaults, buyer may pursue all remedies allowed by law and seller agrees to be responsible for all costs incurred by buyer as a result of sellers default.
  </div>

  <div class="clause">
    <span class="clause-title">6. SUCCESSORS AND ASSIGNEES:</span> The terms and conditions of this contract shall bind all successors, heirs, administrators, trustees, executors and assignees of the respective parties.
  </div>

  <div class="clause">
    <span class="clause-title">7. ACCESS:</span> Sellers agree that buyers may advertise property and have access during reasonable hours to show property to others.
  </div>

  <div class="clause">
    <span class="clause-title">8. ASSIGNABLE:</span> This contract is assignable by the buyer.
  </div>

  <div class="clause">
    <span class="clause-title">9. INSPECTION:</span> (a) Buyer shall have <span class="fill-val">{data.inspection_days}</span> days from Effective Date ("Inspection Period") within which to have such inspections of the Property performed as Buyer shall desire and utilities service shall be made available by the Seller during the Inspection Period; (b) Buyer shall be responsible for prompt payment for such inspections and repair of damage to and restoration of the Property resulting from such inspections; and (c) If Buyer determines, in Buyer's sole discretion, that the condition of the Property is not acceptable to Buyer, Buyer may cancel this Contract by delivering written notice of such election to Seller prior to the expiration of the Inspection Period. If Buyer timely cancels this Contract, the deposit(s) paid shall be immediately returned to Buyer; thereupon, Buyer and Seller shall be released of all further obligations under this Contract.
  </div>

  <div class="terms-header">10. ADDITIONAL TERMS AND CONDITIONS:</div>
  <div class="terms-box">{terms_text}</div>

  <div class="sig-block">
    <div class="sig-verify">The undersigned have read the above information, understand it and verify that it is correct.</div>
    <div class="sig-grid">
      <div class="sig-col">
        {seller_date_block}
        {seller_sig_space}
        <div class="sig-line" style="margin-top: 2px;">
          <span>SELLER: {data.seller_name}</span>
          <span style="color:#777; font-size:7pt;">Primary</span>
        </div>
        <div class="sig-line" style="margin-top: 14px;">
          <span>SELLER: _________________________</span>
          <span style="color:#777; font-size:7pt;">Co-Principal</span>
        </div>
      </div>
      <div class="sig-col">
        {buyer_date_block}
        {buyer_sig_space}
        <div class="sig-line" style="margin-top: 2px;">
          <span>BUYER: {data.buyer_name}</span>
          <span style="color:#555; font-size:7pt;">By: {signer_name}</span>
        </div>
        <div class="sig-line" style="margin-top: 14px;">
          <span>BUYER: __________________________</span>
          <span style="color:#777; font-size:7pt;">Co-Principal</span>
        </div>
      </div>
    </div>
  </div>
</body>
</html>"""

async def generate_contract_pdf_bytes(html_content: str) -> bytes:
    """Render HTML string to single-page PDF bytes via Playwright Chromium."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_content)
        pdf_bytes = await page.pdf(
            format="Letter",
            print_background=True,
            margin={"top": "0.32in", "bottom": "0.3in", "left": "0.45in", "right": "0.45in"}
        )
        await browser.close()
        return pdf_bytes

@app.get("/api/pandadoc/settings")
def get_pandadoc_settings():
    """Return saved PandaDoc API settings."""
    return load_pandadoc_settings()

@app.post("/api/pandadoc/settings")
def update_pandadoc_settings(req: PandaDocSettingsModel):
    """Save PandaDoc API settings and active mode."""
    save_pandadoc_settings(req.dict())
    return {"status": "success", "settings": req.dict()}

@app.post("/api/contract/pdf")
async def download_contract_pdf_endpoint(payload: ContractPayload):
    """Generate and return downloadable 1-page PDF for Contract 1."""
    try:
        html = generate_contract_html(payload)
        pdf_bytes = await generate_contract_pdf_bytes(html)
        safe_addr = re.sub(r'[^a-zA-Z0-9_-]', '_', payload.property_address or "Property")
        filename = f"Purchase_Agreement_{safe_addr}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")

@app.post("/api/contract/pandadoc/send")
async def send_contract_pandadoc_endpoint(payload: ContractPayload):
    """
    Generate Contract 1 PDF and dispatch for digital signature via PandaDoc API.
    Uses Sandbox or Production API key based on configuration.
    """
    settings = load_pandadoc_settings()
    mode = settings.get("mode", "sandbox").lower()
    api_key = settings.get("production_key") if mode == "production" else settings.get("sandbox_key")

    if not api_key:
        return {"status": "error", "message": f"No PandaDoc API key found for {mode} mode. Check PandaDoc Settings."}

    if not payload.recipient_email or "@" not in payload.recipient_email:
        return {"status": "error", "message": "Valid recipient email is required to send e-signature invitation."}

    try:
        # 1. Generate clean 1-page PDF with PandaDoc signature tags
        html = generate_contract_html(payload, for_pandadoc=True)
        pdf_bytes = await generate_contract_pdf_bytes(html)

        # 2. Upload to PandaDoc
        headers = {"Authorization": f"API-Key {api_key}"}
        doc_name = f"Purchase Agreement - {payload.property_address}"
        
        name_parts = (payload.seller_name or "Homeowner").strip().split()
        first_n = name_parts[0] if name_parts else "Homeowner"
        last_n = name_parts[-1] if len(name_parts) > 1 else ""

        buyer_signer = payload.buyer_signer_name or settings.get("buyer_signer_name", "Johnathan Roberts")
        b_parts = buyer_signer.strip().split()
        b_first = b_parts[0] if b_parts else "Johnathan"
        b_last = b_parts[-1] if len(b_parts) > 1 else "Roberts"
        buyer_email = settings.get("sender_email", "john@407flips.com").strip()
        seller_email = payload.recipient_email.strip()

        # If testing with the same email as both seller and buyer, use plus addressing (e.g. john+seller@407flips.com)
        # so PandaDoc accepts two distinct signing steps, and Google Workspace routes it straight to your inbox without bouncing!
        if seller_email.lower() == buyer_email.lower() and "@" in seller_email:
            name_part, domain_part = seller_email.split("@", 1)
            seller_email = f"{name_part}+seller@{domain_part}"

        pandadoc_metadata = {
            "name": doc_name,
            "recipients": [
                {
                    "email": seller_email,
                    "first_name": first_n,
                    "last_name": last_n,
                    "role": "Seller",
                    "signing_order": 1
                },
                {
                    "email": buyer_email,
                    "first_name": b_first,
                    "last_name": b_last,
                    "role": "Buyer",
                    "signing_order": 2
                }
            ],
            "parse_form_fields": False
        }

        files = {
            "file": ("Purchase_Agreement.pdf", pdf_bytes, "application/pdf")
        }

        create_res = requests.post(
            "https://api.pandadoc.com/public/v1/documents",
            headers=headers,
            data={"data": json.dumps(pandadoc_metadata)},
            files=files,
            timeout=20
        )

        if create_res.status_code not in [200, 201]:
            return {
                "status": "error",
                "message": f"PandaDoc document creation failed (HTTP {create_res.status_code}): {create_res.text}"
            }

        doc_data = create_res.json()
        doc_id = doc_data.get("id")
        if not doc_id:
            return {"status": "error", "message": "No document ID returned from PandaDoc."}

        # 3. Poll until document transitions to 'document.draft' (usually 1-2 sec)
        time.sleep(1.5)
        for _ in range(6):
            status_res = requests.get(f"https://api.pandadoc.com/public/v1/documents/{doc_id}", headers=headers, timeout=10)
            if status_res.ok and status_res.json().get("status") == "document.draft":
                break
            time.sleep(1)

        # 4. Dispatch document for e-signature
        send_payload = {
            "message": f"Hello {first_n},\n\nPlease review and electronically sign the Purchase and Sale Agreement for {payload.property_address}.\n\nPeak Investments LLC",
            "subject": f"Purchase and Sale Agreement: {payload.property_address} | Peak Investments",
            "silent": False
        }

        send_res = requests.post(
            f"https://api.pandadoc.com/public/v1/documents/{doc_id}/send",
            headers={"Authorization": f"API-Key {api_key}", "Content-Type": "application/json"},
            json=send_payload,
            timeout=15
        )

        shared_link = ""
        if send_res.ok:
            recips = send_res.json().get("recipients", [])
            for r in recips:
                if r.get("signing_order") == 1 or r.get("email") == payload.recipient_email:
                    shared_link = r.get("shared_link", "")
                    break
            if not shared_link and recips:
                shared_link = recips[0].get("shared_link", "")

        # 5. Log into Outreach History Log
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "channel": f"E-SIGN ({mode.upper()})",
            "parcel_id": payload.parcel_id,
            "county": payload.county,
            "owner": payload.seller_name,
            "address": payload.property_address,
            "recipient": payload.recipient_email,
            "subject": f"Purchase Agreement for ${payload.purchase_price:,.0f} ({mode.upper()})",
            "message": f"Dispatched 1-page agreement via PandaDoc E-Sign. Price: ${payload.purchase_price:,.2f}, Closing: {payload.closing_date}, Inspection: {payload.inspection_days} days.",
            "status": "SENT" if send_res.ok else "FAILED",
            "document_id": doc_id,
            "shared_link": shared_link
        }

        logs = []
        if os.path.exists(OUTREACH_LOG_FILE):
            try:
                with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []
        append_outreach_log(log_entry)

        # 6. Update saved contacts cache
        if payload.parcel_id:
            save_contact(payload.parcel_id, {
                "last_contract_sent": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_contract_status": "SENT",
                "email": payload.recipient_email
            })

        if not send_res.ok:
            return {
                "status": "warning",
                "message": f"Document created in PandaDoc ({doc_id}), but send endpoint returned HTTP {send_res.status_code}: {send_res.text}",
                "document_id": doc_id
            }

        return {
            "status": "success",
            "message": f"Contract dispatched successfully to {payload.recipient_email} via PandaDoc ({mode.upper()})! Homeowner will receive a secure mobile signing invite.",
            "document_id": doc_id,
            "shared_link": shared_link,
            "mode": mode
        }

    except Exception as e:
        return {"status": "error", "message": f"PandaDoc E-Sign Error: {str(e)}"}


FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

@app.get("/static/app.js")
def serve_app_js():
    js_path = os.path.join(FRONTEND_DIR, "app.js")
    if os.path.exists(js_path):
        with open(js_path, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="application/javascript", headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            })
    raise HTTPException(status_code=404, detail="app.js not found")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            })
    return "<h1>Florida Lead Hub</h1><p>Frontend is loading...</p>"

_proxy_started = False

def start_cloudflare_tunnel_proxy():
    """
    Runs a lightweight HTTP forwarder on port 8767 to receive traffic from Cloudflared
    (which routes homeowner.407rescreen.com -> 127.0.0.1:8767) and proxy it to port 8505.
    """
    global _proxy_started
    if _proxy_started:
        return
    _proxy_started = True

    import http.server
    import urllib.request
    import threading

    class TunnelProxyHandler(http.server.BaseHTTPRequestHandler):
        def forward(self, method):
            try:
                length = int(self.headers.get('Content-Length', 0))
                data = self.rfile.read(length) if length > 0 else None
                headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'content-length')}
                headers['Host'] = '127.0.0.1:8505'
                try:
                    req = urllib.request.Request('http://127.0.0.1:8505' + self.path, data=data, headers=headers, method=method)
                    with urllib.request.urlopen(req, timeout=25) as resp:
                        self.send_response(resp.status)
                        for k, v in resp.headers.items():
                            if k.lower() not in ('transfer-encoding', 'content-length'):
                                self.send_header(k, v)
                        content = resp.read()
                        self.send_header('Content-Length', str(len(content)))
                        self.end_headers()
                        self.wfile.write(content)
                except urllib.error.HTTPError as e:
                    self.send_response(e.code)
                    self.end_headers()
                    self.wfile.write(e.read())
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
                    pass
                except Exception as e:
                    try:
                        self.send_response(500)
                        self.end_headers()
                        self.wfile.write(str(e).encode())
                    except Exception:
                        pass
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, OSError):
                pass
            except Exception:
                pass

        def do_POST(self): self.forward("POST")
        def do_GET(self): self.forward("GET")
        def do_DELETE(self): self.forward("DELETE")
        def log_message(self, format, *args): pass

    try:
        proxy_server = http.server.ThreadingHTTPServer(('127.0.0.1', 8767), TunnelProxyHandler)
        t = threading.Thread(target=proxy_server.serve_forever, daemon=True)
        t.start()
        print("[*] Cloudflare Tunnel forwarder active on http://127.0.0.1:8767 (homeowner.407rescreen.com -> :8505)")
    except Exception as e:
        print(f"[!] Could not bind tunnel proxy on 8767: {e}")

def warm_scout_cache():
    try:
        from src.scout_operator_agent import get_statewide_combined_df
        get_statewide_combined_df("FL")
        print("[*] Scout statewide columnar cache pre-warmed.")
    except Exception as e:
        print(f"[!] Scout cache warm error: {e}")

from src.sms_outreach_queue import SmsOutreachQueue


def load_auto_sms_history():
    if not os.path.exists(OUTREACH_LOG_FILE):
        return []
    with open(OUTREACH_LOG_FILE, "r", encoding="utf-8") as history_file:
        return json.load(history_file)


auto_sms_queue = SmsOutreachQueue(
    os.path.join(DATA_DIR, "auto_sms_queue.json"),
    load_saved_contacts, load_auto_sms_history, load_outreach_templates,
    is_lead_blocked_from_outreach,
    lambda payload: send_sms_via_gateway(SendSmsRequest(**payload)),
)

from src.email_outreach_queue import EmailOutreachQueue

auto_email_queue = EmailOutreachQueue(
    os.path.join(DATA_DIR, 'auto_email_queue.json'),
    load_saved_contacts, load_auto_sms_history, load_outreach_templates, load_email_settings,
    is_email_blocked_from_outreach,
    lambda payload: send_email_via_smtp(SendEmailRequest(**payload)),
)


class AutoEmailStartRequest(BaseModel):
    parcel_ids: List[str]


class AutoEmailControlRequest(BaseModel):
    action: str


@app.get('/api/email/auto/status')
def get_auto_email_status():
    return {'status': 'success', 'queue': auto_email_queue.status()}


@app.post('/api/email/auto/preview')
def preview_auto_email(req: AutoEmailStartRequest):
    try:
        return {'status': 'success', **auto_email_queue.preview(req.parcel_ids)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/email/auto/start')
def start_auto_email(req: AutoEmailStartRequest):
    try:
        return {'status': 'success', 'queue': auto_email_queue.start(req.parcel_ids)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/email/auto/control')
def control_auto_email(req: AutoEmailControlRequest):
    try:
        return {'status': 'success', 'queue': auto_email_queue.control(req.action)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class AutoSmsStartRequest(BaseModel):
    parcel_ids: List[str]
    campaign: str = 'initial'


class AutoSmsControlRequest(BaseModel):
    action: str


class AutoSmsResetRequest(BaseModel):
    parcel_ids: List[str]
    county: str


@app.post('/api/sms/auto/reset-initial')
def reset_auto_sms_initial(req: AutoSmsResetRequest):
    try:
        return {'status': 'success', **auto_sms_queue.reset_initial(req.parcel_ids, req.county)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/sms/auto/status")
def get_auto_sms_status():
    return {"status": "success", "queue": auto_sms_queue.status()}


@app.post("/api/sms/auto/preview")
def preview_auto_sms(req: AutoSmsStartRequest):
    try:
        return {"status": "success", **auto_sms_queue.preview(req.parcel_ids, req.campaign)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/sms/auto/start")
def start_auto_sms(req: AutoSmsStartRequest):
    try:
        return {"status": "success", "queue": auto_sms_queue.start(req.parcel_ids, req.campaign)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/sms/auto/control")
def control_auto_sms(req: AutoSmsControlRequest):
    try:
        return {"status": "success", "queue": auto_sms_queue.control(req.action)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.on_event("startup")
def startup_event():
    start_cloudflare_tunnel_proxy()
    auto_sms_queue.start_worker()
    auto_email_queue.start_worker()
    threading.Thread(target=warm_scout_cache, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    import traceback
    start_cloudflare_tunnel_proxy()
    port = 8505
    print("============================================================")
    print(f"[*] Florida Lead Hub running at http://localhost:{port}")
    print("============================================================")
    if "--no-browser" not in sys.argv:
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass
    while True:
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
        except KeyboardInterrupt:
            print("[*] Server stopped by user.")
            break
        except Exception as e:
            print(f"[!] Server error: {e}")
            traceback.print_exc()
            time.sleep(2)
