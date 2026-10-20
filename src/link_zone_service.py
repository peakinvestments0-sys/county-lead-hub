import os
import json
import time
import datetime
from typing import Dict, Any, List, Optional, Tuple

# Primary live path to Link Zone application data
PRIMARY_LINK_ZONE_PATH = r"C:\Projects\Apps\link-zone\data"
# Fallback local catalog path
FALLBACK_CATALOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sources_catalog")
HISTORY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "link_zone_history.json")
BACKUP_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "county_portals.json")

STATE_FILE_MAP = {
    "FL": "florida.json",
    "GA": "georgia.json",
    "IN": "indiana.json",
    "NC": "north-carolina.json",
    "OH": "ohio.json",
    "SC": "south-carolina.json",
    "TN": "tennessee.json",
    "TX": "texas.json"
}

STATE_META = {
    "FL": {"name": "Florida", "icon": "🌴", "tagline": "Opportunity Lives Here", "default_county": "Pinellas"},
    "GA": {"name": "Georgia", "icon": "🍑", "tagline": "The Peach State", "default_county": "Fulton"},
    "IN": {"name": "Indiana", "icon": "🏎️", "tagline": "The Hoosier State", "default_county": "Marion"},
    "NC": {"name": "North Carolina", "icon": "🌲", "tagline": "First in Flight", "default_county": "Mecklenburg"},
    "OH": {"name": "Ohio", "icon": "🌰", "tagline": "The Buckeye State", "default_county": "Franklin"},
    "SC": {"name": "South Carolina", "icon": "🏖️", "tagline": "The Palmetto State", "default_county": "Charleston"},
    "TN": {"name": "Tennessee", "icon": "🎸", "tagline": "The Volunteer State", "default_county": "Shelby"},
    "TX": {"name": "Texas", "icon": "⭐", "tagline": "The Lone Star State", "default_county": "Harris"}
}

class LinkZoneLiveService:
    """
    Direct Live Bridge to C:\\Projects\\Apps\\link-zone\\data.
    Provides zero-click live reads, file modification tracking, syntax-error fail-safe fallback,
    and a persistent audit log history so operators can verify liveness anytime.
    """
    def __init__(self):
        self.cached_states: Dict[str, Dict[str, Any]] = {}
        self.file_mtimes: Dict[str, float] = {}
        self.history: List[Dict[str, Any]] = self._load_history()
        self.last_check_time: float = 0.0
        
        # Initial check
        self._ensure_initialized()

    def _get_active_dir(self) -> Tuple[str, bool]:
        """Returns the active data directory and boolean indicating if it's the live primary path."""
        if os.path.exists(PRIMARY_LINK_ZONE_PATH) and os.path.isdir(PRIMARY_LINK_ZONE_PATH):
            return PRIMARY_LINK_ZONE_PATH, True
        if os.path.exists(FALLBACK_CATALOG_PATH) and os.path.isdir(FALLBACK_CATALOG_PATH):
            return FALLBACK_CATALOG_PATH, False
        return "", False

    def _load_history(self) -> List[Dict[str, Any]]:
        """Load persistent history logs from disk."""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[-100:]  # Keep last 100 events
            except Exception:
                pass
        return []

    def _save_history(self):
        """Persist history logs to disk."""
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history[-100:], f, indent=2)
        except Exception:
            pass

    def log_event(self, level: str, title: str, details: str, state: Optional[str] = None, metrics: Optional[Dict[str, Any]] = None):
        """Record an audit trail event."""
        event = {
            "id": f"lz_{int(time.time() * 1000)}_{len(self.history)}",
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level.upper(),  # SUCCESS, INFO, WARNING, ERROR
            "title": title,
            "details": details,
            "state": state,
            "metrics": metrics or {}
        }
        self.history.insert(0, event)
        if len(self.history) > 100:
            self.history = self.history[:100]
        self._save_history()

    def _ensure_initialized(self):
        """Initial scan of states on startup."""
        active_dir, is_live = self._get_active_dir()
        if not active_dir:
            self.log_event("WARNING", "Link Zone Path Missing", f"Neither {PRIMARY_LINK_ZONE_PATH} nor fallback exists.")
            return

        mode_str = "Live Direct Bridge (C:\\Projects\\Apps\\link-zone\\data)" if is_live else "Local Fallback Snapshot"
        self.log_event("INFO", "Link Zone Bridge Initialized", f"Active connection established via {mode_str}.")
        
        # Load Florida by default
        self.get_state_portals("FL")

    def _parse_county_sources(self, county_name: str, sources: List[Dict[str, Any]], state: str = "FL") -> Dict[str, Any]:
        """Normalizes source entries into Florida Lead Hub's county portal schema."""
        folder_name = county_name.lower().replace(" ", "_").replace("-", "_")
        
        # Base schema
        portal = {
            "full_name": f"{county_name} County",
            "folder_name": folder_name,
            "state": state,
            "csv_name": "RP_PROPERTY_INFO.csv",
            "parquet_name": "RP_PROPERTY_INFO.parquet",
            "sample_lp": "",
            "sample_code": "",
            "sample_probate": "",
            "master_parcel_download_url": "",
            "master_parcel_note": "",
            "master_parcel_format": "",
            "master_parcel_access": "",
            "clerk_lis_pendens_url": "",
            "clerk_lis_pendens_note": "",
            "code_enforcement_url": "",
            "code_enforcement_note": "",
            "clerk_probate_url": "",
            "clerk_probate_note": "",
            "property_search_url": "",
            "property_search_note": "",
            "tax_liens_url": "",
            "tax_liens_note": "",
            "sources": sources
        }

        # Keep Pinellas live sample names if Pinellas
        if county_name.lower() == "pinellas" and state == "FL":
            portal["sample_lp"] = "pinellas_lis_pendens_20260920.csv"
            portal["sample_code"] = "pinellas_code_violations_20260920.csv"
            portal["sample_probate"] = "pinellas_probate_20260920.csv"

        # Categorize sources by explicit 'type' or content notes/indexing
        for idx, src in enumerate(sources):
            src_type = (src.get("type") or "").upper()
            url = src.get("url") or ""
            notes = src.get("notes") or ""
            access = src.get("access") or ""
            fmt = src.get("format") or ""
            notes_lower = notes.lower()

            # 6. Tax Delinquent / Liens (prioritize idx == 5 or tax collector)
            if idx == 5 or src_type in ["DELINQUENT_PROPERTY_TAX", "TAX_LIENS"] or ("tax" in notes_lower and "appraiser" not in notes_lower and "property-taxes" in url):
                if not portal["tax_liens_url"]:
                    portal["tax_liens_url"] = url
                    portal["tax_liens_note"] = notes
                continue

            # 1. Master Parcel Bulk Download
            if idx == 4 or src_type == "MASTER_PARCEL" or "cama" in notes_lower or "database" in notes_lower or ("bulk" in notes_lower and "tax" not in notes_lower):
                if not portal["master_parcel_download_url"]:
                    portal["master_parcel_download_url"] = url
                    portal["master_parcel_note"] = notes
                    portal["master_parcel_format"] = fmt
                    portal["master_parcel_access"] = access
                continue

            # 2. Lis Pendens / Foreclosure
            if idx == 0 or src_type in ["FORECLOSURE_LEGAL_NOTICES", "LIS_PENDENS"] or "lis pendens" in notes_lower or "mortgage" in notes_lower:
                if not portal["clerk_lis_pendens_url"]:
                    portal["clerk_lis_pendens_url"] = url
                    portal["clerk_lis_pendens_note"] = notes
                continue

            # 3. Code Enforcement
            if idx == 1 or src_type == "CODE_ENFORCEMENT" or "code" in notes_lower or "violation" in notes_lower:
                if not portal["code_enforcement_url"]:
                    portal["code_enforcement_url"] = url
                    portal["code_enforcement_note"] = notes
                continue

            # 4. Probate
            if idx == 2 or src_type == "PROBATE" or "probate" in notes_lower or "estate" in notes_lower:
                if not portal["clerk_probate_url"]:
                    portal["clerk_probate_url"] = url
                    portal["clerk_probate_note"] = notes
                continue

            # 5. Property Appraiser Quick Search
            if idx == 3 or src_type == "PROPERTY_SEARCH" or "property search" in notes_lower or "qpublic" in url:
                if not portal["property_search_url"]:
                    portal["property_search_url"] = url
                    portal["property_search_note"] = notes
                continue

        return portal

    def get_state_portals(self, state: str = "FL") -> Dict[str, Any]:
        """
        Live Read with auto-mtime detection & fail-safe fallback.
        Checks file mtime on C:\\Projects\\Apps\\link-zone\\data.
        If file changed, auto reloads and updates cache in real-time.
        """
        state = (state or "FL").upper()
        filename = STATE_FILE_MAP.get(state, f"{state.lower()}.json")
        active_dir, is_live = self._get_active_dir()

        if not active_dir:
            return self.cached_states.get(state, {})

        filepath = os.path.join(active_dir, filename)
        if not os.path.exists(filepath):
            # Try finding state in fallback
            filepath = os.path.join(FALLBACK_CATALOG_PATH, filename)
            if not os.path.exists(filepath):
                return self.cached_states.get(state, {})

        try:
            mtime = os.path.getmtime(filepath)
            cached_mtime = self.file_mtimes.get(state, 0.0)

            # If already cached and file has not changed, return cached version
            if state in self.cached_states and mtime <= cached_mtime:
                return self.cached_states[state]

            # Read file content
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            try:
                raw_data = json.loads(content)
            except json.JSONDecodeError as jde:
                # FAIL-SAFE: Operator is actively editing file or syntax error
                self.log_event(
                    "WARNING",
                    f"Syntax Notice: {filename}",
                    f"Detected JSON syntax error at line {jde.lineno}, col {jde.colno} ({jde.msg}). Gracefully preserved last good state.",
                    state=state,
                    metrics={"error": str(jde), "filepath": filepath}
                )
                if state in self.cached_states:
                    return self.cached_states[state]
                raise

            # Transform raw array into registry dictionary
            registry = {}
            total_links = 0
            if isinstance(raw_data, list):
                for item in raw_data:
                    c_name = item.get("county") or item.get("name")
                    if c_name:
                        srcs = item.get("sources") or []
                        registry[c_name] = self._parse_county_sources(c_name, srcs, state=state)
                        total_links += len(srcs)
            elif isinstance(raw_data, dict):
                registry = raw_data

            # Update cache and mtime
            is_initial = (state not in self.cached_states)
            self.cached_states[state] = registry
            self.file_mtimes[state] = mtime
            self.last_check_time = time.time()

            # Record event in audit history
            event_title = f"Initial Load: {state} ({len(registry)} counties)" if is_initial else f"Live Auto-Refresh: {state} ({len(registry)} counties)"
            event_type = "SUCCESS" if is_initial else "UPDATE"
            self.log_event(
                event_type,
                event_title,
                f"Successfully read {len(registry)} counties and {total_links} verified portals directly from {'Link Zone live folder' if is_live else 'catalog backup'}.",
                state=state,
                metrics={
                    "counties": len(registry),
                    "links": total_links,
                    "mtime": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "is_live": is_live
                }
            )

            # Persist to BACKUP_CONFIG_FILE as an extra safety net
            try:
                os.makedirs(os.path.dirname(BACKUP_CONFIG_FILE), exist_ok=True)
                backup_data = {}
                if os.path.exists(BACKUP_CONFIG_FILE):
                    with open(BACKUP_CONFIG_FILE, "r", encoding="utf-8") as bf:
                        backup_data = json.load(bf)
                backup_data[state] = registry
                with open(BACKUP_CONFIG_FILE, "w", encoding="utf-8") as bf:
                    json.dump(backup_data, bf, indent=4)
            except Exception:
                pass

            return registry

        except Exception as e:
            self.log_event("ERROR", f"Read Error for {state}", str(e), state=state)
            return self.cached_states.get(state, {})

    def force_resync(self) -> Dict[str, Any]:
        """Forces an immediate re-read of all state files directly from Link Zone."""
        active_dir, is_live = self._get_active_dir()
        if not active_dir:
            return {"status": "error", "message": "Link Zone data path not found"}

        synced_states = {}
        total_counties = 0
        total_links = 0

        for state, filename in STATE_FILE_MAP.items():
            path = os.path.join(active_dir, filename)
            if os.path.exists(path):
                # Force reset mtime to trigger re-parse
                self.file_mtimes[state] = 0.0
                portals = self.get_state_portals(state)
                c_count = len(portals)
                l_count = sum(len(p.get("sources", [])) for p in portals.values())
                synced_states[state] = {
                    "counties": c_count,
                    "links": l_count
                }
                total_counties += c_count
                total_links += l_count

        self.log_event(
            "SUCCESS",
            "Manual Force Re-Sync Executed",
            f"Operator triggered full system re-scan. Refreshed {len(synced_states)} states, {total_counties} counties, and {total_links} links.",
            metrics={"states": len(synced_states), "counties": total_counties, "links": total_links}
        )

        return {
            "status": "healthy",
            "is_live": is_live,
            "path": active_dir,
            "synced_states": synced_states,
            "total_counties": total_counties,
            "total_links": total_links,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_health_report(self) -> Dict[str, Any]:
        """Provides real-time health, live path detection, state totals, and recent audit history."""
        active_dir, is_live = self._get_active_dir()
        
        # Check all available state files in active directory
        available_states = {}
        total_counties = 0
        total_links = 0

        if active_dir and os.path.exists(active_dir):
            for state_code, filename in STATE_FILE_MAP.items():
                p = os.path.join(active_dir, filename)
                if os.path.exists(p):
                    mtime = os.path.getmtime(p)
                    # Check if cached
                    cached = self.cached_states.get(state_code, {})
                    c_count = len(cached)
                    l_count = sum(len(c.get("sources", [])) for c in cached.values())
                    available_states[state_code] = {
                        "name": STATE_META.get(state_code, {}).get("name", state_code),
                        "icon": STATE_META.get(state_code, {}).get("icon", "📍"),
                        "filename": filename,
                        "counties": c_count,
                        "links": l_count,
                        "last_modified": datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "is_cached": state_code in self.cached_states
                    }
                    total_counties += c_count
                    total_links += l_count

        return {
            "status": "HEALTHY" if is_live else "FALLBACK",
            "is_live_connected": is_live,
            "primary_path": PRIMARY_LINK_ZONE_PATH,
            "active_path": active_dir,
            "last_checked": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_states": len(available_states),
            "total_counties": total_counties,
            "total_links": total_links,
            "states": available_states,
            "history": self.history[:30] # Return last 30 events for instant display
        }

    def get_state_api_catalog(self, state: str = "FL") -> Dict[str, Any]:
        r"""
        Direct live reader for Link Zone's State API Directories:
        C:\Projects\Apps\link-zone\data\{state_name}-api-links.json.
        Supports FL, GA, TN, TX, and any future states dynamically.
        """
        state_code = (state or "FL").upper()
        state_filename_map = {
            "FL": "florida-api-links.json",
            "GA": "georgia-api-links.json",
            "TN": "tennessee-api-links.json",
            "TX": "texas-api-links.json",
            "IN": "indiana-api-links.json",
            "NC": "north-carolina-api-links.json",
            "OH": "ohio-api-links.json",
            "SC": "south-carolina-api-links.json",
        }
        filename = state_filename_map.get(state_code, f"{state_code.lower()}-api-links.json")
        state_name = STATE_META.get(state_code, {}).get("name", state_code)

        active_dir, is_live = self._get_active_dir()
        catalog_path = os.path.join(active_dir, filename)
        if not os.path.exists(catalog_path):
            catalog_path = os.path.join(r"C:\Projects\Apps\link-zone\data", filename)

        if not os.path.exists(catalog_path):
            return {
                "status": "not_found",
                "state": state_code,
                "state_name": state_name,
                "message": f"API catalog for {state_name} ({filename}) is not generated yet. Run the Codex prompt in Link Zone to scan {state_name}.",
                "total_endpoints": 0,
                "endpoints": [],
                "categories": [],
                "statistics": {}
            }

        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            endpoints = data.get("endpoints", [])
            categories = data.get("categories", [])
            statistics = data.get("statistics", {})
            county_coverage = data.get("countyCoverage", [])
            muni_coverage = data.get("municipalCoverage", [])

            # Decorate endpoints with active/connected indicators
            for ep in endpoints:
                ep_url = ep.get("apiUrl", "").lower()
                if "k6e8-nw6w" in ep_url or "cityoforlando.net" in ep_url:
                    ep["is_connected"] = True
                    ep["connected_lead_type"] = "Code Violation"
                    ep["connected_county"] = "Orange"
                else:
                    ep["is_connected"] = False

            return {
                "status": "ready",
                "state": state_code,
                "state_name": state_name,
                "source_file": catalog_path,
                "schema_version": data.get("schemaVersion", 1),
                "date_verified": data.get("dateVerified", ""),
                "total_endpoints": len(endpoints),
                "categories": categories,
                "statistics": statistics,
                "county_coverage_count": len(county_coverage),
                "muni_coverage_count": len(muni_coverage),
                "endpoints": endpoints
            }
        except Exception as e:
            return {
                "status": "error",
                "state": state_code,
                "state_name": state_name,
                "message": f"Failed to load catalog for {state_name}: {str(e)}",
                "total_endpoints": 0,
                "endpoints": [],
                "categories": [],
                "statistics": {}
            }

    def get_florida_api_catalog(self) -> Dict[str, Any]:
        """Backward-compatible alias for Florida catalog."""
        return self.get_state_api_catalog(state="FL")

# Global Singleton Instance
link_zone_service = LinkZoneLiveService()
