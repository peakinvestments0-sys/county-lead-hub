"""
Florida Lead Hub - Suppression List & DNC Scrubbing Engine
Ensures TCPA compliance, permanent opt-out suppression, and DNC registry enforcement.
A suppressed or DNC-flagged number must never be texted by any campaign.
"""

import os
import json
import time
import re
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SUPPRESSION_FILE = os.path.join(DATA_DIR, "suppression_list.json")
DNC_FILE = os.path.join(DATA_DIR, "dnc_list.json")


def normalize_phone_digits(phone_str: Any) -> str:
    """Extracts and normalizes phone number to 10 standard digits."""
    if not phone_str:
        return ""
    digits = "".join(filter(str.isdigit, str(phone_str)))
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def load_suppression_list() -> List[Dict[str, Any]]:
    """Loads all suppressed numbers from permanent JSON storage."""
    if os.path.exists(SUPPRESSION_FILE):
        try:
            with open(SUPPRESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_suppression_list(records: List[Dict[str, Any]]):
    """Persists suppression list to permanent JSON storage."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SUPPRESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def is_number_suppressed(phone_str: Any) -> bool:
    """Checks if a phone number is permanently suppressed across all campaigns."""
    norm = normalize_phone_digits(phone_str)
    if not norm or len(norm) < 7:
        return False
    
    suppressed = load_suppression_list()
    for rec in suppressed:
        rec_norm = rec.get("normalized_phone") or normalize_phone_digits(rec.get("phone"))
        if rec_norm and (norm == rec_norm or (len(norm) >= 10 and norm in rec_norm) or (len(rec_norm) >= 10 and rec_norm in norm)):
            return True
    return False


def add_to_suppression_list(
    phone_str: str, 
    reason: str = "OPT_OUT", 
    lead_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Permanently suppresses a phone number.
    Records timestamp, raw phone, normalized digits, parcel ID, and reason.
    """
    norm = normalize_phone_digits(phone_str)
    records = load_suppression_list()
    
    # Check if already present
    for r in records:
        r_norm = r.get("normalized_phone") or normalize_phone_digits(r.get("phone"))
        if r_norm == norm:
            return r

    lead = lead_info or {}
    new_entry = {
        "phone": str(phone_str),
        "normalized_phone": norm,
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "parcel_id": lead.get("parcel_id", ""),
        "owner_name": lead.get("owner_name") or lead.get("owner") or "",
        "property_address": lead.get("property_address") or lead.get("address") or "",
        "county": lead.get("county", "")
    }
    
    records.insert(0, new_entry)
    save_suppression_list(records)
    return new_entry


def remove_from_suppression_list(phone_str: str) -> bool:
    """Removes a phone number from suppression list if requested."""
    norm = normalize_phone_digits(phone_str)
    records = load_suppression_list()
    initial_len = len(records)
    records = [
        r for r in records 
        if (r.get("normalized_phone") or normalize_phone_digits(r.get("phone"))) != norm
    ]
    if len(records) != initial_len:
        save_suppression_list(records)
        return True
    return False


# --- Federal & State DNC Scrub Registry Helpers ---

def load_dnc_list() -> List[Dict[str, Any]]:
    """Loads all DNC scrubbed records from permanent JSON storage."""
    if os.path.exists(DNC_FILE):
        try:
            with open(DNC_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []


def save_dnc_list(records: List[Dict[str, Any]]):
    """Persists DNC list to permanent JSON storage."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DNC_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)


def is_dnc_number(phone_str: Any) -> bool:
    """Checks if a phone number is on DNC registry list."""
    norm = normalize_phone_digits(phone_str)
    if not norm or len(norm) < 7:
        return False
    
    dnc_records = load_dnc_list()
    for rec in dnc_records:
        rec_norm = rec.get("normalized_phone") or normalize_phone_digits(rec.get("phone"))
        if rec_norm and norm == rec_norm:
            return True
    return False


def add_to_dnc_list(phone_str: str, registry_name: str = "FEDERAL_STATE_DNC", source: str = "DNC Scrub") -> Dict[str, Any]:
    norm = normalize_phone_digits(phone_str)
    records = load_dnc_list()
    for r in records:
        if (r.get("normalized_phone") or normalize_phone_digits(r.get("phone"))) == norm:
            return r

    new_entry = {
        "phone": str(phone_str),
        "normalized_phone": norm,
        "registry": registry_name,
        "source": source,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    records.insert(0, new_entry)
    save_dnc_list(records)
    return new_entry


def is_lead_blocked_from_outreach(phone_str: Any, lead: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """
    Evaluates whether an outbound message is blocked due to Suppression or DNC.
    Returns (is_blocked, reason_string).
    """
    if not phone_str:
        return True, "Missing phone number"

    # 1. Permanent Opt-Out Suppression Check
    if is_number_suppressed(phone_str):
        return True, "Phone number is on permanent suppression list (OPT_OUT)."

    # 2. DNC List File Check
    if is_dnc_number(phone_str):
        return True, "Phone number is registered on DNC registry."

    # 3. Lead Object In-Memory DNC Flag Check
    if lead:
        if lead.get("dnc") is True or lead.get("is_dnc") is True:
            return True, "Lead is flagged as DNC in CRM / county records."
        if str(lead.get("dnc_status", "")).upper() == "DNC":
            return True, "Lead dnc_status is DNC."

    return False, ""


def scrub_outbound_lead_list(leads: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Scrubs a list of leads before first touch.
    Returns (clean_leads_allowed, blocked_leads).
    """
    clean_leads = []
    blocked_leads = []
    
    for lead in leads:
        phone = lead.get("phone") or lead.get("clean_phone") or ""
        is_blocked, reason = is_lead_blocked_from_outreach(phone, lead)
        if is_blocked:
            lead_copy = dict(lead)
            lead_copy["block_reason"] = reason
            blocked_leads.append(lead_copy)
        else:
            clean_leads.append(lead)

    return clean_leads, blocked_leads
