"""
Direct-to-Seller Distressed Bot Engine & Golden Training Suite
Specialized for Florida Lead Hub (Code Violations, Lis Pendens, Probate)
Persona: Emma (Acquisitions Coordinator) handing off to John (Principal Buyer)
"""

import os
import re
import json
import time
import random
import requests
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

try:
    from src.valuation_service import get_property_market_valuation
except ImportError:
    from valuation_service import get_property_market_valuation

try:
    from src.suppression_service import add_to_suppression_list
except ImportError:
    try:
        from suppression_service import add_to_suppression_list
    except ImportError:
        add_to_suppression_list = None

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SELLER_BOT_SETTINGS_FILE = os.path.join(DATA_DIR, "seller_bot_settings.json")
SELLER_TRAINING_FILE = os.path.join(DATA_DIR, "seller_golden_replies.json")

DEFAULT_SELLER_BOT_SETTINGS = {
    "enabled": True,
    "mode": "copilot",  # "copilot" (review first) or "autopilot" (hands-free auto dispatch)
    "bot_name": "Emma",
    "partner_name": "John",
    "office_phone": "(407) 815-5043",
    "gateway_phone": "(407) 793-7029",
    "gold_deal_threshold": 0.70,       # Asking <= 70% of Assessed/Market Value is GOLD DEAL
    "spread_deal_threshold": 0.85,     # 70% - 85% is SPREAD DEAL
    "auto_send_delay_seconds": 30,
    "gemini_api_key": os.environ.get("GEMINI_API_KEY", ""),
    "gemini_model": "gemini-3.8-flash",
    "use_gemini_enhancer": True,
    "personality_prompt": "Friendly, warm, casual Florida local. Short 1 to 2 sentence texts. Disarming, understanding. Drive toward a quick 5 minute call with John."
}

# --- Core Distress Outreach Scripts & State Machine Constants ---
# Doorbell Stage 1 Openers (Single-Segment, Under 160 Chars, Tiered by Distress Count)
DISTRESS_SCRIPTS = {
    # 1. Doorbell Stage 1 Openers (The Doorbell - Only Goal is Getting a Reply)
    "OPENER_MULTI_LIST": "Hey {first_name} — did you ever decide what you're doing with {address}?",
    "OPENER_SINGLE_LIST": "Hey {first_name}, quick question on {address}, got a sec?",
    "OPENER_ULTRA_SHORT": "Hey {first_name}?",

    # Legacy hooks retained for backward compatibility
    "CASUAL_LOCAL_HOOK": "Hey {first_name}, quick question on {address}, got a sec?",
    "DRIVEBY_HOOK": "Hey {first_name} — did you ever decide what you're doing with {address}?",
    "AS_IS_NO_FEES_HOOK": "Hey {first_name}, quick question on {address}, got a sec?",
    "CURIOUS_WALKAWAY_HOOK": "Hey {first_name}?",

    # 2. Stage 1 -> Stage 2 Bridge Golden Replies (Identifies Emma & Bridges to Qualify)
    "BRIDGE_WHAT_EXCUSE_ME": "It's Emma — I help homeowners in {area} figure out their options on {address}. Are you still the owner there?",
    "BRIDGE_WHEN_DID_WE_TALK": "We haven't talked — sorry, should've led with that. I'm Emma, I work with homeowners around {area}. Had a quick question on {address}, got a sec?",
    "BRIDGE_WHO_IS_THIS": "Emma, I work with a local investment group buying in {area}. Not a realtor, no listings — just asking about {address}.",

    # 3. Code Violation Branch
    "CODE_INITIAL_HOOK": "Hey {first_name} — did you ever decide what you're doing with {address}?",
    "CODE_ASSESS_FINES": "Completely understand, city fines add up fast. What is the current status with the code compliance officer, and what repairs are they demanding?",
    "CODE_OFFER_ASIS": "Got it. That is what we specialize in. We take over the property 100% as is and resolve the city citations directly at closing so you walk away clean. What are you looking to walk away with?",
    
    # 4. Lis Pendens / Pre-Foreclosure Branch
    "LIS_PENDENS_INITIAL_HOOK": "Hey {first_name} — did you ever decide what you're doing with {address}?",
    "LIS_PENDENS_TIMELINE": "I know how stressful bank notices can be. Do you know if the bank has set a formal auction date yet, or are you still in the early stages?",
    "LIS_PENDENS_PAYOFF": "Understood. We can move fast enough to close before the auction date and pay off the mortgage balance. What would you need to net to make a move work?",
    "LIS_PENDENS_BACKUP": "That makes total sense if you are working on a loan modification. We would love to position ourselves as your backup plan just in case the bank stalls before the auction date. Would you be open to a quick backup agreement?",
    
    # 5. Probate / Inherited Property Branch
    "PROBATE_INITIAL_HOOK": "Hey {first_name} — did you ever decide what you're doing with {address}?",
    "PROBATE_STATUS_CHECK": "Thank you for letting me know. Has probate formally been opened with the county court yet, or are you still working through the estate paperwork?",
    "PROBATE_CONTENTS_LEFTOVER": "Take all the time you need for personal keepsakes. For everything else, you can leave furniture, clothing, or clutter right where it is. We handle 100% of the cleanout. What are you and the family hoping to walk away with?",
    
    # 6. Universal Qualification & Appointment Closes
    "QUALIFY_CONDITION": "What can you tell me about the overall condition of the home? How are the roof, AC, and plumbing holding up?",
    "QUALIFY_WALKAWAY_PRICE": "Thank you for sharing that. If we pay cash, cover standard closing costs, and buy 100% as is, what is your ideal walkaway price?",
    "GOLD_DEAL_CALL_CLOSE": "That sounds like a fair number we can make work for a fast cash close. I would love to have John, who heads up our acquisitions, give you a quick 5 minute call today to confirm the details. Would later this afternoon or tomorrow morning work better?",
    "SPREAD_DEAL_COUNTER": "Got it. Because we take on the open citations and all needed repairs with cash, our offer typically needs to be a bit lower to account for the work. What is the absolute bottom dollar you would feel comfortable taking?",
    "RETAIL_CREATIVE_PIVOT": "I completely respect where you want to be on price. For a full retail number with the current situation, the only way we could make that work would be on creative terms. Would you be open to hearing how that works?",
    "UNREALISTIC_DREAM_PRICE": "Haha fair enough, at that price I would pack my bags today too! Seriously though, if you are open to seeing what a realistic as is cash offer looks like without realtors, repairs, or fees, John and I can help. Otherwise, no worries at all!",
    
    # 7. Handoff to John Closes
    "BOOK_CALL_PROPOSAL": "Awesome. Let me set you up with John, our managing partner, for a quick 5 minute call to walk through the cash numbers and timeline. Would later today or tomorrow morning work better for a chat with John?",
    "BOOK_CALL_CONFIRMED": "Sounds great! I have scheduled John to call you at {time} from our office line (407) 815-5043. We look forward to helping you get this resolved!",
    
    # 8. Objection Handlers
    "OBJ_HOW_DID_YOU_GET_NUMBER": "We monitor the county clerk and property appraiser public records, and use a licensed skip trace service to reach owners directly by phone.",
    "OBJ_LOWBALL_DEFENSE": "I completely understand your concern. We are not here to waste your time with insult offers. We run our numbers off real county comps, we pay all closing fees, and you do not pay 6% realtor commissions.",
    "OBJ_ALREADY_HAVE_OFFER": "That is great! A lot of buyer offers fall through during inspection. If your current buyer asks for price cuts or backs out, please keep us as your backup cash buyer.",
    "AS_IS_CONTENTS": "No, absolutely not! You do not have to remove anything, and we will never charge you for cleanout. Anything left behind, furniture, old tables, trash, or tenant items, you can leave right there. We buy 100% as is and handle all the cleanup at our own expense. What are you hoping to walk away with cash in hand for the property?",
    "OBJECTION_MID_CONVO_NO": "Completely understand. If you don't mind me asking, what bottom dollar number would make letting it go worth it for you?",
    "OPT_OUT_CONFIRMATION": "Got it, won't text again."
}

# --- Approved Human Soft Opt-Out Lines (Rotate on Every First Touch) ---
SOFT_OPT_OUTS = [
    "If I'm bothering you just say no and I won't text you no more.",
    "If you don't want these texts just say the word and I'm gone.",
    "Not interested? Just say no and I'll drop it."
]


def get_soft_opt_out(index: Optional[int] = None) -> str:
    """Returns an approved human soft opt-out line."""
    if index is not None:
        return SOFT_OPT_OUTS[index % len(SOFT_OPT_OUTS)]
    return random.choice(SOFT_OPT_OUTS)


def get_lead_area_name(lead: Dict[str, Any]) -> str:
    """Extracts local city or county area name for natural conversational phrasing in bridge replies."""
    if not lead:
        return "the area"

    # 1. Check explicit city field
    city = lead.get("city") or lead.get("City") or lead.get("property_city")
    if city and str(city).strip() and str(city).strip().lower() not in ["florida", "fl"]:
        return str(city).strip().title()

    # 2. Extract city from address if formatted '123 Main St, Clearwater, FL 33767'
    addr = str(lead.get("property_address") or lead.get("address") or "")
    if "," in addr:
        parts = [p.strip() for p in addr.split(",") if p.strip()]
        if len(parts) >= 2:
            candidate_city = parts[1]
            candidate_city = re.sub(r'\b(FL|Florida|\d{5})\b', '', candidate_city, flags=re.IGNORECASE).strip()
            if candidate_city and len(candidate_city) >= 3:
                return candidate_city.title()

    # 3. Check county field
    county = lead.get("county") or lead.get("County")
    if county and str(county).strip() and str(county).strip().lower() not in ["florida", "fl"]:
        return str(county).strip().title()

    return "the area"


def is_multi_distress_lead(lead: Dict[str, Any]) -> bool:
    """Determines whether a lead is on 2+ distress lists (Multi-list tier)."""
    if not lead:
        return False

    # Explicit count
    count = lead.get("distress_count") or lead.get("list_count")
    if count is not None:
        try:
            if int(count) >= 2:
                return True
        except (ValueError, TypeError):
            pass

    # Stacked distress indicators
    if str(lead.get("Is_Stacked_Distress", "")).strip().lower() in ["yes", "true", "1"]:
        return True
    if str(lead.get("is_stacked_distress", "")).strip().lower() in ["yes", "true", "1"]:
        return True
    if lead.get("is_stacked") is True:
        return True

    # Stack notes
    notes = str(lead.get("Distress_Stack_Notes") or lead.get("distress_stack_notes") or "").upper()
    if "DOUBLE" in notes or "TRIPLE" in notes or "+" in notes:
        return True

    # Check distinct category signals
    signals = 0
    cat_str = str(lead.get("distress_category") or lead.get("category") or lead.get("lead_type") or "").lower()
    for sig in ["code", "lis", "probate", "tax"]:
        if sig in cat_str:
            signals += 1

    for flag in ["Code_Violations", "Lis_Pendens", "Probate", "Tax_Liens", "code_violations", "lis_pendens", "tax_lien"]:
        if lead.get(flag):
            signals += 1

    lists = lead.get("distress_lists")
    if isinstance(lists, (list, tuple)) and len(lists) >= 2:
        return True

    return signals >= 2


def load_seller_bot_settings() -> Dict[str, Any]:
    cfg = dict(DEFAULT_SELLER_BOT_SETTINGS)
    if os.path.exists(SELLER_BOT_SETTINGS_FILE):
        try:
            with open(SELLER_BOT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    return cfg


def save_seller_bot_settings(settings: Dict[str, Any]):
    cfg = dict(DEFAULT_SELLER_BOT_SETTINGS)
    cfg.update(settings)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SELLER_BOT_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# --- Golden Replies Training Data Helpers ---

def load_seller_golden_replies() -> List[Dict[str, Any]]:
    if os.path.exists(SELLER_TRAINING_FILE):
        try:
            with open(SELLER_TRAINING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass
    # If file doesn't exist, seed with pre-trained scenarios
    seeded = get_preseeded_golden_replies()
    save_all_golden_replies(seeded)
    return seeded


def save_all_golden_replies(replies: List[Dict[str, Any]]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SELLER_TRAINING_FILE, "w", encoding="utf-8") as f:
        json.dump(replies, f, indent=2)


def save_seller_golden_reply(entry: Dict[str, Any]):
    """Appends or updates a golden training example when user approves/edits a reply in Copilot."""
    replies = load_seller_golden_replies()
    entry_id = entry.get("id") or f"seller_golden_{int(time.time())}_{random.randint(100, 999)}"
    entry["id"] = entry_id
    if not entry.get("timestamp"):
        entry["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")

    replies = [r for r in replies if r.get("id") != entry_id]
    replies.insert(0, entry)
    replies = replies[:120]  # Cap at 120 high-quality training pairs
    save_all_golden_replies(replies)


def delete_seller_golden_reply(entry_id: str) -> bool:
    replies = load_seller_golden_replies()
    initial_len = len(replies)
    replies = [r for r in replies if r.get("id") != entry_id]
    if len(replies) != initial_len:
        save_all_golden_replies(replies)
        return True
    return False


# --- Automated "Deal or No Deal" Spread Scorer ---

def evaluate_deal_spread(asking_price: float, parcel_value: float, market_value: Optional[float] = None) -> Dict[str, Any]:
    """
    Evaluates asking price against true retail market value (Zestimate/ARV) or county tax assessed value.
    Returns deal tier, ratio, and strategic action.
    """
    benchmark = float(market_value) if market_value and market_value > 0 else (float(parcel_value) * 1.30 if parcel_value and parcel_value > 0 else float(parcel_value or 0))

    if not asking_price or asking_price <= 0 or not benchmark or benchmark <= 0:
        return {
            "tier": "UNKNOWN",
            "deal_rating": "UNKNOWN",
            "ratio": None,
            "ratio_pct": None,
            "detected_price": asking_price,
            "parcel_value": parcel_value,
            "market_value": benchmark or parcel_value,
            "badge": "NEED NUMBERS",
            "badge_color": "slate",
            "headline": "Awaiting Price or Value",
            "action": "Qualify asking price and check comps."
        }

    ratio = asking_price / benchmark
    settings = load_seller_bot_settings()
    gold_threshold = float(settings.get("gold_deal_threshold", 0.70))
    spread_threshold = float(settings.get("spread_deal_threshold", 0.85))

    ratio_pct = round(ratio * 100, 1)

    # 1. Unrealistic / Sarcastic Dream Price Anchor (> 135% of Retail Market Value)
    if ratio > 1.35:
        return {
            "tier": "UNREALISTIC_PRICE",
            "deal_rating": "UNREALISTIC_PRICE",
            "ratio": round(ratio, 2),
            "ratio_pct": ratio_pct,
            "detected_price": asking_price,
            "parcel_value": parcel_value,
            "market_value": benchmark,
            "spread_pct": round((ratio - 1.0) * 100, 1),
            "badge": "🎲 DREAM PRICE",
            "badge_color": "rose",
            "headline": f"Unrealistic Retail Anchor ({ratio_pct}% of Market)",
            "action": "Sarcastic or dream anchor. Defuse with humor & as-is reality check."
        }
    elif ratio <= gold_threshold:
        return {
            "tier": "GOLD_DEAL",
            "deal_rating": "GOLD_DEAL",
            "ratio": round(ratio, 2),
            "ratio_pct": ratio_pct,
            "detected_price": asking_price,
            "parcel_value": parcel_value,
            "market_value": benchmark,
            "spread_pct": round((1.0 - ratio) * 100, 1),
            "badge": "🔥 THE GOLD DEAL",
            "badge_color": "emerald",
            "headline": f"Deep Equity Spread ({round((1.0 - ratio) * 100)}% Discount)",
            "action": "Urgent priority! Rush to book 5-minute call with John."
        }
    elif ratio <= spread_threshold:
        return {
            "tier": "SPREAD_DEAL",
            "deal_rating": "SPREAD_DEAL",
            "ratio": round(ratio, 2),
            "ratio_pct": ratio_pct,
            "detected_price": asking_price,
            "parcel_value": parcel_value,
            "market_value": benchmark,
            "spread_pct": round((1.0 - ratio) * 100, 1),
            "badge": "⚡ SPREAD DEAL",
            "badge_color": "amber",
            "headline": f"Negotiable Spread ({ratio_pct}% of Market)",
            "action": "Counter with repair/code fine discount to bridge the gap."
        }
    else:
        return {
            "tier": "RETAIL_CREATIVE",
            "deal_rating": "RETAIL_CREATIVE",
            "ratio": round(ratio, 2),
            "ratio_pct": ratio_pct,
            "detected_price": asking_price,
            "parcel_value": parcel_value,
            "market_value": benchmark,
            "spread_pct": round((ratio - 1.0) * 100, 1),
            "badge": "🏷️ RETAIL ASK",
            "badge_color": "rose",
            "headline": f"Near Full Retail ({ratio_pct}% of Market)",
            "action": "Pivot to creative terms (Subject-To / Seller Finance) or explain as-is cash difference."
        }


# --- Pre-Seeded 12 Golden Training Scenarios ---

def get_preseeded_golden_replies() -> List[Dict[str, Any]]:
    return [
        {
            "id": "golden_bridge_what_1",
            "category": "Stage 1-2 Bridge",
            "node": "BRIDGE_WHAT_EXCUSE_ME",
            "distress_type": "General",
            "seller_inbound": "what? who is this and what are you talking about?",
            "final_approved_text": "It's Emma — I help homeowners in Pinellas figure out their options on 14783 SEMINOLE TRL. Are you still the owner there?",
            "notes": "Stage 1 to Stage 2 bridge: warm, disarming, identifies Emma, pivots to ownership check."
        },
        {
            "id": "golden_bridge_when_talk_2",
            "category": "Stage 1-2 Bridge",
            "node": "BRIDGE_WHEN_DID_WE_TALK",
            "distress_type": "General",
            "seller_inbound": "which one were you? when did we talk?",
            "final_approved_text": "We haven't talked — sorry, should've led with that. I'm Emma, I work with homeowners around Pinellas. Had a quick question on 14783 SEMINOLE TRL, got a sec?",
            "notes": "Stage 1 to Stage 2 bridge: disarms confusion with apology, establishes local presence, asks for quick sec."
        },
        {
            "id": "golden_bridge_who_is_this_3",
            "category": "Stage 1-2 Bridge",
            "node": "BRIDGE_WHO_IS_THIS",
            "distress_type": "General",
            "seller_inbound": "who is this?",
            "final_approved_text": "Emma, I work with a local investment group buying in Pinellas. Not a realtor, no listings — just asking about 14783 SEMINOLE TRL.",
            "notes": "Stage 1 to Stage 2 bridge: concise, confirms investor not realtor, direct to address inquiry."
        },
        {
            "id": "golden_bridge_wrong_number_4",
            "category": "Stage 1-2 Bridge",
            "node": "OPT_OUT",
            "distress_type": "General",
            "seller_inbound": "wrong number, never owned that property",
            "final_approved_text": "Got it, won't text again.",
            "notes": "Stage 1 to Stage 2 bridge: wrong number treated as opt-out with confirmation."
        },
        {
            "id": "golden_code_fines_1",
            "category": "Code Violations",
            "node": "CODE_ASSESS_FINES",
            "distress_type": "Code Violation",
            "seller_inbound": "The city has been fining me $150 a day because the roof tarp tore and the grass is high. I can't afford to fix it.",
            "final_approved_text": "I completely understand, those daily city fines add up fast. We buy completely as is, take over the property, and pay off the code liens right at closing so it stops hitting your record. What are you looking to walk away with?",
            "notes": "Empathetic, confirms relief from daily fines, asks for walkaway price."
        },
        {
            "id": "golden_code_condemned_2",
            "category": "Code Violations",
            "node": "CODE_OFFER_ASIS",
            "distress_type": "Code Violation",
            "seller_inbound": "They put an unsafe building placard on the door. It needs a full gut rehab.",
            "final_approved_text": "No problem at all on our end, we specialize in heavy fixers and buy strictly cash as is without any city inspection requirements. If we cover all closing costs, what is your bottom dollar cash price?",
            "notes": "Removes fear of inspections, asks bottom-dollar cash."
        },
        {
            "id": "golden_lis_pendens_urgent_3",
            "category": "Lis Pendens",
            "node": "LIS_PENDENS_TIMELINE",
            "distress_type": "Lis Pendens",
            "seller_inbound": "The bank filed a foreclosure lawsuit last month. I don't know what to do.",
            "final_approved_text": "I know how stressful that is, but the good news is you still have time to take control. Has the court set a final auction date yet, or are you still in the response window?",
            "notes": "Disarming reassurance, vets auction urgency."
        },
        {
            "id": "golden_lis_pendens_auction_soon_4",
            "category": "Lis Pendens",
            "node": "LIS_PENDENS_PAYOFF",
            "distress_type": "Lis Pendens",
            "seller_inbound": "The auction is scheduled for next month on the 24th. I owe about $140,000 on the mortgage.",
            "final_approved_text": "Understood. We can move fast enough to close before the auction date and pay off the mortgage balance. What would you need to net to make a move work?",
            "notes": "Clear path to credit protection and walkaway cash."
        },
        {
            "id": "golden_probate_heirs_5",
            "category": "Probate",
            "node": "PROBATE_STATUS_CHECK",
            "distress_type": "Probate",
            "seller_inbound": "My mother passed away and left the house to my brother and me. We don't live in Florida.",
            "final_approved_text": "Please accept my heartfelt condolences. Handling an out of town estate can be overwhelming. Have you guys filed probate with the Florida court yet, or are you just getting started?",
            "notes": "Respectful, checks formal probate standing."
        },
        {
            "id": "golden_probate_clutter_6",
            "category": "Probate",
            "node": "PROBATE_CONTENTS_LEFTOVER",
            "distress_type": "Probate",
            "seller_inbound": "The house is completely packed with 40 years of furniture and clutter. We cannot clean it out.",
            "final_approved_text": "Please do not worry about cleaning anything out. You take whatever personal items or keepsakes you want, and leave literally everything else behind, we handle 100% of the cleanout at our expense. What price are you guys hoping for?",
            "notes": "Eliminates the #1 probate objection (clean-out exhaustion)."
        },
        {
            "id": "golden_obj_how_number_7",
            "category": "Objection Handling",
            "node": "OBJ_HOW_DID_YOU_GET_NUMBER",
            "distress_type": "General",
            "seller_inbound": "Who is this and how did you get my cell number?",
            "final_approved_text": "We monitor the county clerk and property appraiser public records, and use a licensed skip trace service to reach owners directly by phone.",
            "notes": "Concrete, transparent, honest, non-defensive."
        },
        {
            "id": "golden_obj_lowball_8",
            "category": "Objection Handling",
            "node": "OBJ_LOWBALL_DEFENSE",
            "distress_type": "General",
            "seller_inbound": "Are you just another wholesaler who's going to offer me 30 cents on the dollar?",
            "final_approved_text": "Not at all, I completely understand your frustration with lowball callers. We buy direct with our own capital, cover 100% of standard closing costs, and charge zero commissions. What is the number you would need to make a deal make sense?",
            "notes": "Validates frustration, differentiates direct buyer, asks for their number."
        },
        {
            "id": "golden_gold_price_received_9",
            "category": "Gold Deal",
            "node": "GOLD_DEAL_CALL_CLOSE",
            "distress_type": "General",
            "seller_inbound": "I just want $130,000 cash and I want it gone by next Friday.",
            "final_approved_text": "That sounds very reasonable and within our cash budget. I want to have John, who manages our acquisitions, give you a quick 5 minute call today to confirm the details. Would 2pm or later this afternoon work better for a quick call with John?",
            "notes": "Validates number immediately, transitions smoothly to call with John."
        },
        {
            "id": "golden_spread_price_received_10",
            "category": "Negotiation",
            "node": "SPREAD_DEAL_COUNTER",
            "distress_type": "Code Violation",
            "seller_inbound": "I'm looking for around $220,000 cash.",
            "final_approved_text": "Got it. Normally for homes with open code fines and deferred maintenance, our cash numbers need to be a bit lower so we can clear the city liens. What is the absolute bottom dollar you would feel comfortable walking away with?",
            "notes": "Polite anchor on distress fines, prompts for true walkaway bottom."
        },
        {
            "id": "golden_book_call_time_11",
            "category": "Appointment Booking",
            "node": "BOOK_CALL_PROPOSAL",
            "distress_type": "General",
            "seller_inbound": "Yeah, I'd be open to speaking with someone about a cash offer.",
            "final_approved_text": "Awesome! Let me have John give you a brief 5 minute call to walk through the cash numbers and closing timeline. Would later today around 3pm or tomorrow morning work better for a chat with John?",
            "notes": "Simple two-option time choice."
        },
        {
            "id": "golden_book_call_confirmed_12",
            "category": "Appointment Booking",
            "node": "BOOK_CALL_CONFIRMED",
            "distress_type": "General",
            "seller_inbound": "Tomorrow morning around 10am works for me.",
            "final_approved_text": "Sounds great! I have scheduled John to call you tomorrow at 10:00 AM from our office line (407) 815-5043. We look forward to connecting and helping you get this solved!",
            "notes": "Locks in time, establishes office caller ID (407-815-5043)."
        }
    ]


# --- Gemini AI Voice Enhancer ---

def polish_seller_reply_with_gemini(
    node: str, 
    template_reply: str, 
    lead: Dict[str, Any], 
    inbound_message: str,
    distress_type: str = "General",
    deal_eval: Optional[Dict[str, Any]] = None
) -> str:
    """
    Enhances template reply using Google Gemini with direct-to-seller few-shot golden examples.
    Persona: Emma (Acquisitions Coordinator at Peak Investments LLC) handing off to John.
    First-touch outreach nodes bypass Gemini completely to ensure deterministic carrier compliance.
    """
    first_touch_nodes = {
        "INITIAL_HOOK", "INITIAL_OUTREACH", "CASUAL_LOCAL_HOOK", "DRIVEBY_HOOK",
        "AS_IS_NO_FEES_HOOK", "CURIOUS_WALKAWAY_HOOK", "CODE_INITIAL_HOOK",
        "LIS_PENDENS_INITIAL_HOOK", "PROBATE_INITIAL_HOOK",
        "OPENER_MULTI_LIST", "OPENER_SINGLE_LIST", "OPENER_ULTRA_SHORT",
        "BRIDGE_WHAT_EXCUSE_ME", "BRIDGE_WHEN_DID_WE_TALK", "BRIDGE_WHO_IS_THIS"
    }
    if node in first_touch_nodes or "INITIAL" in str(node).upper() or str(node).endswith("_HOOK") or str(node).startswith("BRIDGE_"):
        return template_reply

    settings = load_seller_bot_settings()
    api_key = (settings.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not api_key or not settings.get("use_gemini_enhancer", True):
        return template_reply

    model = settings.get("gemini_model", "gemini-3.8-flash")
    bot_name = settings.get("bot_name", "Emma")
    partner_name = settings.get("partner_name", "John")
    office_phone = settings.get("office_phone", "(407) 815-5043")
    owner_name = lead.get("owner_name") or lead.get("first_name") or "there"
    address = lead.get("property_address") or lead.get("address") or "your property"

    # Grab top 5 most relevant golden replies
    goldens = load_seller_golden_replies()[:5]
    few_shots = ""
    for g in goldens:
        inb = g.get("seller_inbound")
        out = g.get("final_approved_text")
        if inb and out:
            few_shots += f"\nHomeowner: \"{inb}\"\n{bot_name}: \"{out}\"\n"

    intel_section = ""
    if deal_eval and deal_eval.get("tier") not in [None, "UNKNOWN"]:
        tier = deal_eval.get("tier")
        ask = deal_eval.get("detected_price") or 0
        mkt = deal_eval.get("market_value") or deal_eval.get("parcel_value") or 0
        assessed = deal_eval.get("parcel_value") or 0
        ratio = deal_eval.get("ratio_pct") or 0
        intel_section = (
            f"\nCONFIDENTIAL INTERNAL PROPERTY VALUATION (FOR YOUR SITUATIONAL AWARENESS ONLY - NEVER QUOTE THESE ESTIMATE NUMBERS TO THE SELLER):\n"
            f"- Est. Retail Market Value (ARV): ${mkt:,.0f}\n"
            f"- County Assessed Tax Value: ${assessed:,.0f}\n"
            f"- Seller Asking Price: ${ask:,.0f} ({ratio}% of market)\n"
            f"- Deal Tier: {tier}\n"
        )
        if tier == "UNREALISTIC_PRICE":
            intel_section += (
                f"- TIER GUIDANCE: The seller dropped an unrealistic or sarcastic dream price anchor (e.g. $1.5M or far above retail). "
                f"Acknowledge their number with humor and disarming warmth ('at that price I'd pack my bags today too! 😄'). "
                f"Never argue comps, give real estate lectures, or sound offended. Disarm the joke and politely see if they're open to a realistic as-is cash offer, or wish them well.\n"
            )
        elif tier == "GOLD_DEAL":
            intel_section += "- TIER GUIDANCE: Deep equity spread! Do not haggle or bargain them down. Lock in a quick call with John right away.\n"
        elif tier == "SPREAD_DEAL":
            intel_section += "- TIER GUIDANCE: Negotiable spread. Tactfully explore repair condition (roof, AC, plumbing) to bridge the gap.\n"

    custom_personality = (settings.get("personality_prompt") or "").strip()
    personality_block = ""
    if custom_personality:
        personality_block = f"\nCUSTOM PERSONALITY & TONE GUIDELINES:\n{custom_personality}\n"

    system_prompt = (
        f"You are {bot_name}, a friendly, warm, empathetic acquisitions coordinator at Peak Investments LLC (407 Flips).\n"
        f"You are texting via cellular SMS with a Florida homeowner facing distress ({distress_type}).\n"
        f"Your principal acquisitions partner who makes the cash purchasing decisions is {partner_name}.\n"
        f"Main office phone for calls: {office_phone}.\n"
        f"Target Property: {address}.\n"
        f"{intel_section}\n"
        f"{personality_block}"
        f"CURRENT GOAL FOR THIS STEP ({node}):\n"
        f"\"{template_reply}\"\n\n"
        f"CRITICAL RULES:\n"
        f"1. Keep it short, natural, and human (1 to 2 sentences max). Real people text casually.\n"
        f"2. Never use corporate or scammy phrases ('Dear Sir', 'As a real estate investor', 'I hope this finds you well').\n"
        f"3. Be empathetic, disarming, and helpful (solve code fines, stop auction date, handle estate contents).\n"
        f"4. Drive toward setting a quick 5 minute call with {partner_name} from office line {office_phone}.\n"
        f"5. CARRIER SPAM COMPLIANCE: In initial outreach or early messages, do NOT spam repetitive buzzwords like 'cash offer', 'all-cash', or 'local investor'. Sound like a normal, local person asking a simple conversational question.\n"
        f"6. NO DASHES OR HYPHENS: Absolutely NEVER use em-dashes (—), en-dashes (–), or hyphens (-). Real people texting use natural commas, periods, or spaces. Use 'as is' instead of 'as-is'. Dashes look robotic and break carrier SMS GSM-7 encoding.\n"
        f"7. Output ONLY the raw SMS text reply. No quotes, no markdown."
    )

    user_prompt = (
        f"APPROVED TEXTING EXAMPLES:\n{few_shots}\n\n"
        f"CURRENT SITUATION:\n"
        f"Homeowner Name: {owner_name}\n"
        f"Homeowner Inbound SMS: \"{inbound_message}\"\n"
        f"Core Intent to Deliver: \"{template_reply}\"\n\n"
        f"Your SMS text reply as {bot_name}:"
    )

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{system_prompt}\n\n{user_prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 90,
                "temperature": 0.3
            }
        }
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
        if res.status_code == 200:
            data = res.json()
            cand = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            cand = cand.strip('"\n\r ')
            if cand.lower().startswith(f"{bot_name.lower()}:"):
                cand = cand[len(bot_name) + 1:].strip()
            
            # Sanitize away any em-dashes, en-dashes, or conversational hyphens
            cand = cand.replace("—", ", ").replace("–", ", ")
            cand = cand.replace(" - ", ", ")
            cand = cand.replace("as-is", "as is").replace("As-is", "As is").replace("As-Is", "As is")
            cand = cand.replace("clean-out", "cleanout").replace("clean-outs", "cleanouts")
            cand = cand.replace("out-of-the-blue", "out of the blue")
            cand = cand.replace("5-minute", "5 minute").replace("10-minute", "10 minute")
            cand = cand.replace("all-cash", "cash").replace("All-cash", "Cash")
            # Replace any stray hyphen surrounded by spaces
            import re
            cand = re.sub(r'\s+-\s+', ', ', cand)
            cand = re.sub(r'(\w+)-(\w+)', r'\1 \2', cand)  # Replace words-separated-by-hyphen with spaces
            cand = re.sub(r'\s+', ' ', cand).strip()

            if len(cand) >= 12:
                return cand
    except Exception:
        pass

    clean_template = template_reply.replace("—", ", ").replace("–", ", ").replace(" - ", ", ")
    return clean_template


# --- Keyword & Regex Helper Utilities ---

def is_opt_out_reply(text: str, is_opener_reply: bool = True) -> bool:
    """
    Detects if a seller wants to opt out / stop receiving messages.
    
    Engine rule: any rejection phrased any way — no, nah, nope, stop, don't text/call/message me,
    leave me alone, remove me, unsubscribe, quit, wrong number — in reply to the opener = opt-out.
    Suppress the number permanently, send one confirmation ('Got it, won't text again.'), never text again.
    
    Scope guard: a 'no' three messages deep ('would you take 200k?' -> 'no') is a negotiation objection,
    not an opt-out. Only opener-level rejection kills the thread. Mid-conversation 'no' gets worked, not suppressed.
    """
    clean = text.lower().strip()
    
    # 1. Guard against questions about removing furniture, trash, clutter, liens, or fines
    if re.search(r'\bremove\s+(?:my\s+)?(?:furniture|trash|junk|clutter|table|tables|items|stuff|belongings|fines?|liens?|violations?|shed|roof)\b', clean):
        return False
    if re.search(r'\bstop\s+(?:by|in|over)\b', clean):
        return False

    # 2. Strict opt-out triggers (Always opt-out at any stage of the conversation)
    strict_patterns = [
        r'^\s*stop[\.!\?]?\s*$',
        r'\b(?:please\s+)?stop\s+(?:texting|calling|messaging|contacting)(?:\s+me)?\b',
        r'\b(?:please\s+)?quit\s+(?:texting|calling|messaging|contacting)(?:\s+me)?\b',
        r'^\s*please\s+stop[\.!\?]?\s*$',
        r'\b(unsubscribe|opt\s*out)\b',
        r'\b(remove\s+me|remove\s+my\s+(?:number|name|phone|cell))\b',
        r'\b(take\s+me\s+off(?:(?:\s+your|\s+the)?\s+list)?|lose\s+my\s+number|wrong\s+number)\b',
        r'\b(do\s+not\s+(?:text|call|contact|message)|don\'?t\s+(?:text|call|contact|message))(?:\s+me)?\b',
        r'\b(cease\s*(?:and\s*desist)?|leave\s+me\s+alone|f\*\*\*?\s*off|fuck\s*off)\b'
    ]
    if any(bool(re.search(pat, clean)) for pat in strict_patterns):
        return True

    # 3. Opener-level rejections (Engine rule: any rejection in response to the opener = opt-out)
    if is_opener_reply:
        opener_rejection_patterns = [
            r'^\s*(?:no|nah|nope|pass|never)\s*[\.!\?]?\s*$',
            r'^\s*(?:no\s+thanks|no\s+thank\s+you|no\s+thx|no\s+ty)\s*[\.!\?]?\s*$',
            r'^\s*(?:not\s+interested|i\'?m\s+not\s+interested|not\s+for\s+me)\s*[\.!\?]?\s*$',
            r'^\s*(?:no\s*,?\s*(?:not\s+interested|leave\s+me|dont|don\'t|i\'?m\s+good|we\'?re\s+good))\b',
            r'\b(?:not\s+interested|no\s+thanks|not\s+selling|i\'?m\s+not\s+selling|we\s+aren\'?t\s+selling|not\s+for\s+sale)\b',
            r'^\s*(?:no\s+way|definitely\s+not|absolutely\s+not|hell\s+no|heck\s+no)\s*[\.!\?]?\s*$',
            r'\b(?:don\'?t\s+text\s+no\s+more|won\'?t\s+text\s+no\s+more|hell\s+no|heck\s+no)\b'
        ]
        if any(bool(re.search(pat, clean)) for pat in opener_rejection_patterns):
            return True

    return False


def extract_dollar_amount(text: str) -> Optional[float]:
    """
    Extracts dollar price from phrases like '$150k', '180,000', 'want 220k', '$140000', '1.5 million', '$2m'.
    Requires a price indicator ($, k, million, or intent keywords like 'want', 'offer', 'asking', 'take', 'need', 'net', 'sell for', 'price')
    or excludes Florida zip codes / address numbers.
    """
    clean = text.lower().replace(",", "")
    
    # 1. Million expressions: "1.5 million", "2 million", "1.5m", "$2m"
    m_match = re.search(r'\$?(\d+(?:\.\d+)?)\s*(?:million|mil|m)\b', clean)
    if m_match:
        val = float(m_match.group(1))
        if val > 0:
            return val * 1000000.0

    # 2. Thousand expressions: "$150k", "220k", "150 k"
    k_match = re.search(r'\$?(\d+(?:\.\d+)?)\s*k\b', clean)
    if k_match:
        val = float(k_match.group(1)) * 1000.0
        if val >= 10000:
            return val

    # 3. Explicit currency prefix: "$180000", "$180,000", "$35000", "$1,200,000"
    dollar_match = re.search(r'\$\s*(\d{4,9})\b', clean)
    if dollar_match:
        val = float(dollar_match.group(1))
        if val >= 10000:
            return val

    # 4. Price indicator keywords preceding or following a 5-8 digit number
    price_keyword_patterns = [
        r'\b(?:want|asking|take|offer|net|need|price\s*(?:is|of)?|sell\s*(?:for|at)?|looking\s*for|bottom\s*dollar|give\s*me|around|about)\s+(?:around\s+|about\s+)?(\d{5,8})\b',
        r'\b(\d{5,8})\s*(?:dollars|bucks|cash|net|walkaway)\b'
    ]
    for pat in price_keyword_patterns:
        kw_match = re.search(pat, clean)
        if kw_match:
            val = float(kw_match.group(1))
            if val >= 10000:
                return val

    # 5. Bare 5-8 digit number check with strict address/zip exclusions
    address_preceding_pattern = r'\b(?:fl|florida|tampa|orlando|clearwater|st\.?\s*pete|stpete|pinellas|hillsborough|orange|polk|pasco|seminole|miami|road|rd|street|st|avenue|ave|blvd|drive|dr|lane|ln|court|ct|terrace|terr|way|suite|ste|apt|zip(?:\s*code)?|unit|box|hwy|highway|pkwy|parkway)\s*[,:]?\s*(\d{5})\b'
    
    raw_match = re.search(r'\b(\d{5,8})\b', clean)
    if raw_match:
        candidate_str = raw_match.group(1)
        candidate_val = float(candidate_str)
        
        # Check if matched inside address pattern
        if re.search(address_preceding_pattern, clean):
            addr_m = re.search(address_preceding_pattern, clean)
            if addr_m and addr_m.group(1) == candidate_str:
                return None
        
        # Florida zip code range (32000 - 34999) without price keyword or $ is excluded
        if len(candidate_str) == 5 and 32000 <= candidate_val <= 34999:
            return None
            
        # 6-digit number or higher without zip collision
        if candidate_val >= 50000 and len(candidate_str) >= 6:
            return candidate_val

    return None


def extract_appointment_time(text: str) -> Optional[str]:
    time_patterns = [
        r'\b(?:at|around|after)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b',
        r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b',
        r'\b\d{1,2}\s*o\'?clock\b',
        r'\btomorrow\b(?:\s+(?:morning|afternoon|evening|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?',
        r'\btoday\b(?:\s+(?:morning|afternoon|evening|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?',
        r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b(?:\s+(?:morning|afternoon|evening|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?'
    ]
    for pat in time_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m and len(m.group(0).strip()) > 1:
            return m.group(0).strip().title()
    return None


# --- Main Seller Bot State Machine Engine ---

class SellerBotEngine:
    def __init__(self):
        self.settings = load_seller_bot_settings()

    def detect_distress_type(self, lead: Dict[str, Any]) -> str:
        """Determines whether lead is Code Violation, Lis Pendens, or Probate."""
        cat = str(lead.get("distress_category") or lead.get("lead_type") or lead.get("category") or "").lower()
        if "code" in cat or "violation" in cat:
            return "Code Violation"
        elif "lis" in cat or "pendens" in cat or "foreclosure" in cat:
            return "Lis Pendens"
        elif "probate" in cat or "estate" in cat or "heir" in cat:
            return "Probate"
        return "General Distress"

    def generate_initial_outreach(
        self, 
        lead: Dict[str, Any], 
        distress_override: Optional[str] = None,
        forced_angle: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generates a fresh Stage 1 opener SMS text according to the two-stage doctrine.
        Doorbell stage: Gets a reply under 160 chars, single segment.
        Tiers by distress-list count (Multi-list vs Single-list vs Ultra-short).
        Appends mandatory rotating soft opt-out line (Drops 'Reply STOP to opt out').
        First-touch templates send deterministically without Gemini rewrite.
        """
        import random
        distress = distress_override or self.detect_distress_type(lead)
        first_name = lead.get("owner_name") or lead.get("first_name") or "there"
        if " " in first_name:
            first_name = first_name.split()[0].title()

        raw_addr = lead.get("property_address") or lead.get("address") or "the property"
        street_addr = raw_addr.split(",")[0].strip() if "," in raw_addr else raw_addr

        is_multi = is_multi_distress_lead(lead)

        # 1. Select opener angle tiered by distress list count
        if forced_angle == "multi_list":
            opener_angle = "multi_list"
            node = "OPENER_MULTI_LIST"
            template = DISTRESS_SCRIPTS["OPENER_MULTI_LIST"]
        elif forced_angle == "single_list":
            opener_angle = "single_list"
            node = "OPENER_SINGLE_LIST"
            template = DISTRESS_SCRIPTS["OPENER_SINGLE_LIST"]
        elif forced_angle == "ultra_short":
            opener_angle = "ultra_short"
            node = "OPENER_ULTRA_SHORT"
            template = DISTRESS_SCRIPTS["OPENER_ULTRA_SHORT"]
        elif is_multi:
            # Multi-list (2+ lists — getting hammered): rotate multi_list and ultra_short
            opener_angle = random.choice(["multi_list", "multi_list", "ultra_short"])
            if opener_angle == "multi_list":
                node = "OPENER_MULTI_LIST"
                template = DISTRESS_SCRIPTS["OPENER_MULTI_LIST"]
            else:
                node = "OPENER_ULTRA_SHORT"
                template = DISTRESS_SCRIPTS["OPENER_ULTRA_SHORT"]
        else:
            # Single-list: rotate single_list and ultra_short
            opener_angle = random.choice(["single_list", "single_list", "ultra_short"])
            if opener_angle == "single_list":
                node = "OPENER_SINGLE_LIST"
                template = DISTRESS_SCRIPTS["OPENER_SINGLE_LIST"]
            else:
                node = "OPENER_ULTRA_SHORT"
                template = DISTRESS_SCRIPTS["OPENER_ULTRA_SHORT"]

        base_text = template.replace("{first_name}", first_name).replace("{address}", street_addr)

        # 2. Append rotating approved human soft opt-out line
        soft_opt_out = get_soft_opt_out()
        full_text = f"{base_text} {soft_opt_out}"

        # 3. Compliance guarantee: single SMS segment (under 160 characters)
        if len(full_text) > 160:
            # Truncate ultra-long street address or fallback to ultra-short
            fallback_ultra = DISTRESS_SCRIPTS["OPENER_ULTRA_SHORT"].replace("{first_name}", first_name)
            shortest_opt = "Not interested? Just say no and I'll drop it."
            full_text = f"{fallback_ultra} {shortest_opt}"
            opener_angle = "ultra_short"
            node = "OPENER_ULTRA_SHORT"

        parcel_value = float(lead.get("just_value") or lead.get("assessed_value") or 250000.0)
        return {
            "status": "ok",
            "action": "INITIAL_OUTREACH",
            "node": node,
            "opener_angle": opener_angle,
            "is_multi_list": is_multi,
            "distress_type": distress,
            "suggested_reply": full_text,
            "suggestion": full_text,
            "deal_evaluation": evaluate_deal_spread(0, parcel_value, parcel_value * 1.3),
            "auto_send_allowed": False
        }

    def process_inbound_sms(
        self, 
        lead: Dict[str, Any], 
        inbound_text: str, 
        conversation_history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Processes an incoming seller text through the state machine.
        Returns suggested reply, next node, deal spread evaluation, and action flags.
        Handles Stage 1 -> Stage 2 bridge, opener-level vs mid-convo opt-out guard, and deal scoring.
        """
        settings = load_seller_bot_settings()
        clean_text = inbound_text.strip()
        distress = self.detect_distress_type(lead)

        # Route initial outreach generation if no inbound text from homeowner yet
        if not clean_text or clean_text.lower().startswith("distressed property outreach inquiry") or clean_text == "INITIAL_HOOK":
            return self.generate_initial_outreach(lead, distress)

        first_name = lead.get("owner_name") or lead.get("first_name") or "there"
        if " " in first_name:
            first_name = first_name.split()[0].title()

        address = lead.get("property_address") or lead.get("address") or "the property"
        parcel_value = float(lead.get("just_value") or lead.get("assessed_value") or 250000.0)

        # Pull retail market value (Zestimate or Florida retail model)
        val_info = get_property_market_valuation(address, parcel_value)
        market_value = float(lead.get("market_value") or val_info.get("market_value") or parcel_value * 1.30)

        # Determine conversation depth to apply Scope Guard
        # Only opener-level rejection suppresses; mid-conversation 'no' gets worked
        prior_inbounds = [
            m for m in (conversation_history or [])
            if (m.get("direction") == "INBOUND" or str(m.get("sender_phone") or "") == str(lead.get("phone") or ""))
        ]
        is_opener_reply = (len(prior_inbounds) == 0)

        # 1. Check Opt-Out (Engine rule & Scope guard)
        if is_opt_out_reply(clean_text, is_opener_reply=is_opener_reply):
            lead_phone = lead.get("phone") or lead.get("saved_phone") or lead.get("recipient")
            if lead_phone and add_to_suppression_list:
                try:
                    add_to_suppression_list(lead_phone, reason="OPT_OUT", lead_info=lead)
                except Exception:
                    pass
            return {
                "action": "OPT_OUT",
                "node": "OPT_OUT",
                "suggested_reply": DISTRESS_SCRIPTS["OPT_OUT_CONFIRMATION"],
                "deal_evaluation": evaluate_deal_spread(0, parcel_value, market_value),
                "auto_send_allowed": True
            }

        # 2. Stage 1 -> Stage 2 Bridge Golden Replies
        # Emma handles confused curiosity / identification questions warmly and pivots to qualify
        area = get_lead_area_name(lead)
        street_addr = address.split(",")[0].strip() if "," in address else address
        low = clean_text.lower().strip()

        # 2a. "what?" / "excuse me?"
        what_excuse_patterns = [
            r'^\s*what[\.!\?]*\s*$',
            r'^\s*excuse\s+me[\.!\?]*\s*$',
            r'^\s*huh[\.!\?]*\s*$',
            r'^\s*pardon[\.!\?]*\s*$',
            r'\bwhat\s+(?:is\s+this|is\s+this\s+about|do\s+you\s+mean|are\s+you\s+talking\s+about|is\s+this\s+regarding)\b'
        ]
        if any(re.search(p, low) for p in what_excuse_patterns):
            raw_reply = DISTRESS_SCRIPTS["BRIDGE_WHAT_EXCUSE_ME"].replace("{area}", area).replace("{address}", street_addr)
            node = "BRIDGE_WHAT_EXCUSE_ME"
            polished = polish_seller_reply_with_gemini(node, raw_reply, lead, clean_text, distress)
            return {
                "action": "SUGGESTION_READY",
                "node": node,
                "distress_type": distress,
                "deal_evaluation": evaluate_deal_spread(0, parcel_value, market_value),
                "suggested_reply": polished,
                "auto_send_allowed": False
            }

        # 2b. "which one were you?" / "when did we talk?" / "do I know you?"
        when_talk_patterns = [
            r'\bwhich\s+one\s+(?:were\s+you|was\s+this|are\s+you)\b',
            r'\bwhen\s+did\s+we\s+(?:talk|speak)\b',
            r'\b(?:did\s+we|have\s+we)\s+(?:talk|talked|spoken|speak|met)\b',
            r'\bdo\s+i\s+know\s+you\b',
            r'\bwho\s+were\s+you\s+again\b',
            r'\bremind\s+me\s+who\s+you\s+are\b'
        ]
        if any(re.search(p, low) for p in when_talk_patterns):
            raw_reply = DISTRESS_SCRIPTS["BRIDGE_WHEN_DID_WE_TALK"].replace("{area}", area).replace("{address}", street_addr)
            node = "BRIDGE_WHEN_DID_WE_TALK"
            polished = polish_seller_reply_with_gemini(node, raw_reply, lead, clean_text, distress)
            return {
                "action": "SUGGESTION_READY",
                "node": node,
                "distress_type": distress,
                "deal_evaluation": evaluate_deal_spread(0, parcel_value, market_value),
                "suggested_reply": polished,
                "auto_send_allowed": False
            }

        # 2c. "who is this?"
        who_is_this_patterns = [
            r'^\s*who\s+(?:is\s+this|are\s+you|dis)[\.!\?]*\s*$',
            r'^\s*who\'?s\s+this[\.!\?]*\s*$',
            r'\bwho\s+am\s+i\s+speaking\s+with\b',
            r'\bwho\s+is\s+texting\s+me\b'
        ]
        if any(re.search(p, low) for p in who_is_this_patterns):
            raw_reply = DISTRESS_SCRIPTS["BRIDGE_WHO_IS_THIS"].replace("{area}", area).replace("{address}", street_addr)
            node = "BRIDGE_WHO_IS_THIS"
            polished = polish_seller_reply_with_gemini(node, raw_reply, lead, clean_text, distress)
            return {
                "action": "SUGGESTION_READY",
                "node": node,
                "distress_type": distress,
                "deal_evaluation": evaluate_deal_spread(0, parcel_value, market_value),
                "suggested_reply": polished,
                "auto_send_allowed": False
            }

        # 2d. Scope guard for mid-conversation "no" objection (worked, not suppressed)
        if not is_opener_reply and re.search(r'^\s*(?:no|nah|nope|not\s+interested|no\s+thanks)\s*[\.!\?]?\s*$', low):
            raw_reply = DISTRESS_SCRIPTS["OBJECTION_MID_CONVO_NO"]
            node = "OBJECTION_MID_CONVO_NO"
            deal_eval = evaluate_deal_spread(0, parcel_value, market_value)
            polished = polish_seller_reply_with_gemini(node, raw_reply, lead, clean_text, distress, deal_eval)
            return {
                "action": "SUGGESTION_READY",
                "node": node,
                "distress_type": distress,
                "deal_evaluation": deal_eval,
                "suggested_reply": polished,
                "auto_send_allowed": False
            }

        # 2. Check for Price Mention
        extracted_price = extract_dollar_amount(clean_text)
        deal_eval = evaluate_deal_spread(extracted_price, parcel_value, market_value) if extracted_price else evaluate_deal_spread(0, parcel_value, market_value)

        # If a price was quoted, handle price negotiation first
        if extracted_price:
            if deal_eval["tier"] == "UNREALISTIC_PRICE":
                raw_reply = DISTRESS_SCRIPTS["UNREALISTIC_DREAM_PRICE"]
                node = "UNREALISTIC_DREAM_PRICE"
            elif deal_eval["tier"] == "GOLD_DEAL":
                raw_reply = DISTRESS_SCRIPTS["GOLD_DEAL_CALL_CLOSE"]
                node = "GOLD_DEAL_CALL_CLOSE"
            elif deal_eval["tier"] == "SPREAD_DEAL":
                raw_reply = DISTRESS_SCRIPTS["SPREAD_DEAL_COUNTER"]
                node = "SPREAD_DEAL_COUNTER"
            else:
                raw_reply = DISTRESS_SCRIPTS["RETAIL_CREATIVE_PIVOT"]
                node = "RETAIL_CREATIVE_PIVOT"

            polished = polish_seller_reply_with_gemini(node, raw_reply, lead, clean_text, distress, deal_eval)
            return {
                "action": "PRICE_RECEIVED",
                "node": node,
                "extracted_price": extracted_price,
                "deal_evaluation": deal_eval,
                "suggested_reply": polished,
                "auto_send_allowed": (deal_eval["tier"] == "GOLD_DEAL")
            }

        # 3. Check for Time Mention (Appointment Confirmation if no price was quoted)
        appt_time = extract_appointment_time(clean_text)
        if appt_time:
            raw_reply = DISTRESS_SCRIPTS["BOOK_CALL_CONFIRMED"].replace("{time}", appt_time)
            polished = polish_seller_reply_with_gemini("BOOK_CALL_CONFIRMED", raw_reply, lead, clean_text, distress, deal_eval)
            return {
                "action": "APPOINTMENT_CONFIRMED",
                "node": "CALL_CONFIRMED",
                "appointment_time": appt_time,
                "suggested_reply": polished,
                "deal_evaluation": deal_eval,
                "auto_send_allowed": True
            }

        # 4.5 Universal As-Is / Leftover Furniture & Clean-out Handler
        low = clean_text.lower()
        if any(w in low for w in ["furniture", "table", "tables", "clutter", "stuff", "junk", "clean", "cleanout", "mess", "leave behind", "left behind", "as is", "as-is", "charge me"]):
            raw_reply = DISTRESS_SCRIPTS["AS_IS_CONTENTS"]
            node = "AS_IS_CONTENTS"
            polished = polish_seller_reply_with_gemini(node, raw_reply, lead, clean_text, distress)
            return {
                "action": "SUGGESTION_READY",
                "node": node,
                "distress_type": distress,
                "deal_evaluation": deal_eval,
                "suggested_reply": polished,
                "auto_send_allowed": False
            }

        # 5. Distress-Specific Branches
        if distress == "Code Violation":
            if any(w in low for w in ["fine", "fines", "city", "citation", "lien", "code", "ticket", "violation"]):
                raw_reply = DISTRESS_SCRIPTS["CODE_OFFER_ASIS"]
                node = "CODE_OFFER_ASIS"
            elif any(w in low for w in ["yes", "yeah", "open", "sure", "what do you offer", "offer", "how much"]):
                raw_reply = DISTRESS_SCRIPTS["CODE_ASSESS_FINES"]
                node = "CODE_ASSESS_FINES"
            else:
                raw_reply = DISTRESS_SCRIPTS["QUALIFY_CONDITION"]
                node = "QUALIFY_CONDITION"

        elif distress == "Lis Pendens":
            if any(w in low for w in ["auction", "date", "sale", "foreclosure", "sheriff"]):
                raw_reply = DISTRESS_SCRIPTS["LIS_PENDENS_PAYOFF"]
                node = "LIS_PENDENS_PAYOFF"
            elif any(w in low for w in ["mod", "modification", "bank", "lawyer", "attorney"]):
                raw_reply = DISTRESS_SCRIPTS["LIS_PENDENS_BACKUP"]
                node = "LIS_PENDENS_BACKUP"
            elif any(w in low for w in ["yes", "open", "help", "options", "what can you do"]):
                raw_reply = DISTRESS_SCRIPTS["LIS_PENDENS_TIMELINE"]
                node = "LIS_PENDENS_TIMELINE"
            else:
                raw_reply = DISTRESS_SCRIPTS["QUALIFY_CONDITION"]
                node = "QUALIFY_CONDITION"

        elif distress == "Probate":
            if any(w in low for w in ["clutter", "furniture", "stuff", "junk", "clean", "mess"]):
                raw_reply = DISTRESS_SCRIPTS["PROBATE_CONTENTS_LEFTOVER"]
                node = "PROBATE_CONTENTS_LEFTOVER"
            elif any(w in low for w in ["heir", "brother", "sister", "family", "court", "attorney"]):
                raw_reply = DISTRESS_SCRIPTS["PROBATE_STATUS_CHECK"]
                node = "PROBATE_STATUS_CHECK"
            else:
                raw_reply = DISTRESS_SCRIPTS["QUALIFY_WALKAWAY_PRICE"]
                node = "QUALIFY_WALKAWAY_PRICE"

        else:
            # General Distress Fallback
            if any(w in low for w in ["call", "speak", "talk", "reach me"]):
                raw_reply = DISTRESS_SCRIPTS["BOOK_CALL_PROPOSAL"]
                node = "BOOK_CALL_PROPOSAL"
            elif any(w in low for w in ["condition", "roof", "ac", "rehab", "work"]):
                raw_reply = DISTRESS_SCRIPTS["QUALIFY_WALKAWAY_PRICE"]
                node = "QUALIFY_WALKAWAY_PRICE"
            else:
                raw_reply = DISTRESS_SCRIPTS["BOOK_CALL_PROPOSAL"]
                node = "BOOK_CALL_PROPOSAL"

        polished = polish_seller_reply_with_gemini(node, raw_reply, lead, clean_text, distress)

        return {
            "action": "SUGGESTION_READY",
            "node": node,
            "distress_type": distress,
            "deal_evaluation": deal_eval,
            "suggested_reply": polished,
            "auto_send_allowed": False
        }


def test_seller_gemini_connection(api_key: str, model: str = "gemini-3.8-flash") -> Dict[str, Any]:
    """Tests connectivity to Google Gemini API."""
    if not api_key:
        return {"status": "error", "message": "No Gemini API key provided."}
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": "Respond with 'GEMINI_OK' if you can read this."}]}],
            "generationConfig": {"maxOutputTokens": 20, "temperature": 0.1}
        }
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
        if res.status_code == 200:
            return {"status": "success", "message": f"Successfully connected to Google Gemini ({model})!"}
        return {"status": "error", "message": f"Gemini returned HTTP {res.status_code}: {res.text}"}
    except Exception as e:
        return {"status": "error", "message": f"Gemini connection failed: {str(e)}"}
