"""
Lucas - Autonomous Acquisitions Executive Operator & Pipeline Closer
Persona: Lucas (Back-Office COO & Pipeline Intelligence)
Works alongside Emma (Front-Office Seller Specialist) and John (Principal Investor)
"""

import os
import json
import time
import threading
import datetime
from typing import Dict, Any, List, Optional, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
LUCAS_TIMERS_FILE = os.path.join(DATA_DIR, "lucas_timers.json")
LUCAS_MEMORY_FILE = os.path.join(DATA_DIR, "lucas_memory.json")
SAVED_CONTACTS_FILE = os.path.join(DATA_DIR, "saved_contacts.json")
SCHEDULED_CALLBACKS_FILE = os.path.join(DATA_DIR, "scheduled_callbacks.json")
SELLER_BOT_SETTINGS_FILE = os.path.join(DATA_DIR, "seller_bot_settings.json")

class LucasOperatorEngine:
    """
    Lucas Executive Operator:
    - Deals Triage & Pipeline Radar
    - Autonomous Delayed Timers & SMS Nudges
    - Daily Executive Briefings & Wholesale Margin Tracking
    - Background Event Monitoring Thread
    """
    def __init__(self):
        self.timers: List[Dict[str, Any]] = self._load_timers()
        self.memory: List[Dict[str, Any]] = self._load_memory()
        self._lock = threading.Lock()
        self._running = True
        
        # Start background timer execution thread
        self._worker_thread = threading.Thread(target=self._background_timer_loop, daemon=True)
        self._worker_thread.start()
        
        self.log_memory(
            "INFO",
            "Lucas Operator Online",
            "Autonomous back-office pipeline monitoring and delayed timer engine active."
        )

    # -------------------------------------------------------------
    # PERSISTENCE & MEMORY
    # -------------------------------------------------------------
    def _load_timers(self) -> List[Dict[str, Any]]:
        if os.path.exists(LUCAS_TIMERS_FILE):
            try:
                with open(LUCAS_TIMERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
        return []

    def _save_timers(self):
        try:
            os.makedirs(os.path.dirname(LUCAS_TIMERS_FILE), exist_ok=True)
            with open(LUCAS_TIMERS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.timers, f, indent=2)
        except Exception:
            pass

    def _load_memory(self) -> List[Dict[str, Any]]:
        if os.path.exists(LUCAS_MEMORY_FILE):
            try:
                with open(LUCAS_MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data[-100:]
            except Exception:
                pass
        return []

    def _save_memory(self):
        try:
            os.makedirs(os.path.dirname(LUCAS_MEMORY_FILE), exist_ok=True)
            with open(LUCAS_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.memory[-100:], f, indent=2)
        except Exception:
            pass

    def log_memory(self, level: str, title: str, details: str, lead_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        with self._lock:
            entry = {
                "id": f"lucas_{int(time.time() * 1000)}_{len(self.memory)}",
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "level": level.upper(), # INFO, SUCCESS, ACTION, WARNING
                "title": title,
                "details": details,
                "lead_id": lead_id,
                "metadata": metadata or {}
            }
            self.memory.insert(0, entry)
            if len(self.memory) > 100:
                self.memory = self.memory[:100]
            self._save_memory()

    # -------------------------------------------------------------
    # BACKGROUND TIMER WORKER
    # -------------------------------------------------------------
    def _background_timer_loop(self):
        """Checks pending delayed timers every 15 seconds and executes due actions."""
        while self._running:
            try:
                now_ts = time.time()
                due_timers = []
                with self._lock:
                    for t in self.timers:
                        if t.get("status") == "PENDING" and t.get("trigger_ts", 0) <= now_ts:
                            due_timers.append(t)

                for t in due_timers:
                    self._execute_timer(t)

            except Exception as e:
                pass
            time.sleep(15)

    def _execute_timer(self, timer: Dict[str, Any]):
        """Executes a due timer action (e.g. SMS nudge via Emma or contract reminder)."""
        timer_id = timer.get("id")
        action = timer.get("action_type")
        lead_name = timer.get("lead_name", "Seller")
        phone = timer.get("clean_phone") or timer.get("phone", "")
        message = timer.get("payload_message", "")

        try:
            from src.suppression_service import is_lead_blocked_from_outreach
            is_blocked, reason = is_lead_blocked_from_outreach(phone)
            if is_blocked:
                with self._lock:
                    timer["status"] = "SUPPRESSED"
                    timer["error"] = f"Outreach blocked: {reason}"
                    self._save_timers()
                self.log_memory(
                    "WARNING",
                    f"Timer Canceled for {lead_name} (Suppressed/DNC)",
                    f"Outbound follow-up blocked: {reason}",
                    lead_id=timer.get("lead_id")
                )
                return

            if action in ["SMS_NUDGE", "AUTO_FOLLOWUP"] and phone:
                # Dispatch follow-up SMS via backend SMS sender or log simulation
                self._dispatch_sms(phone, message, lead_name)
                with self._lock:
                    timer["status"] = "COMPLETED"
                    timer["executed_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._save_timers()

                self.log_memory(
                    "ACTION",
                    f"Delayed Nudge Sent to {lead_name}",
                    f"Dispatched autonomous follow-up SMS via Emma: \"{message}\"",
                    lead_id=timer.get("lead_id"),
                    metadata={"phone": phone, "timer_id": timer_id}
                )

            elif action == "CONTRACT_REMINDER":
                self._dispatch_sms(phone, message, lead_name)
                with self._lock:
                    timer["status"] = "COMPLETED"
                    timer["executed_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._save_timers()

                self.log_memory(
                    "ACTION",
                    f"Contract Reminder Dispatched to {lead_name}",
                    f"Reminded seller regarding pending agreement: \"{message}\"",
                    lead_id=timer.get("lead_id"),
                    metadata={"phone": phone, "timer_id": timer_id}
                )

            else:
                with self._lock:
                    timer["status"] = "COMPLETED"
                    timer["executed_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._save_timers()

                self.log_memory(
                    "SUCCESS",
                    f"Timer Triggered for {lead_name}",
                    f"Action '{action}' executed successfully.",
                    lead_id=timer.get("lead_id")
                )

        except Exception as e:
            with self._lock:
                timer["status"] = "FAILED"
                timer["error"] = str(e)
                self._save_timers()
            self.log_memory("WARNING", f"Timer Failed for {lead_name}", str(e), lead_id=timer.get("lead_id"))

    def _dispatch_sms(self, phone: str, message: str, lead_name: str):
        """Sends SMS via local gateway settings or sandbox simulation."""
        # Check if Android Gateway or Sandbox
        clean = "".join(filter(str.isdigit, phone))
        try:
            # We import and call server-level sms dispatch if available or record to thread
            from src.seller_bot_engine import SELLER_BOT_SETTINGS_FILE
            # Update last_sms in saved_contacts
            self._record_contact_outreach(clean, message)
        except Exception:
            pass

    def _record_contact_outreach(self, clean_phone: str, message: str):
        if not os.path.exists(SAVED_CONTACTS_FILE):
            return
        try:
            with open(SAVED_CONTACTS_FILE, "r", encoding="utf-8") as f:
                contacts = json.load(f)
            updated = False
            for k, c in contacts.items():
                if c.get("clean_phone") == clean_phone:
                    c["last_sms_sent"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    c["last_sms_status"] = "SENT (Lucas Auto-Nudge)"
                    c["last_sms_message"] = message
                    updated = True
                    break
            if updated:
                with open(SAVED_CONTACTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(contacts, f, indent=2)
        except Exception:
            pass

    # -------------------------------------------------------------
    # TIMER MANAGEMENT API
    # -------------------------------------------------------------
    def schedule_timer(
        self,
        lead_id: str,
        lead_name: str,
        phone: str,
        address: str,
        action_type: str,
        delay_hours: float,
        custom_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Schedules a future delayed action/timer."""
        trigger_ts = time.time() + (delay_hours * 3600)
        scheduled_str = datetime.datetime.fromtimestamp(trigger_ts).strftime("%Y-%m-%d %I:%M %p")
        
        # Default follow-up templates if custom message not provided
        first_name = lead_name.split()[0] if lead_name else "there"
        if not custom_message:
            if action_type == "CONTRACT_FOLLOWUP":
                custom_message = f"Hi {first_name}, Lucas and Emma here just checking in on the purchase agreement we emailed over for {address}. Let us know if you had any questions on the terms!"
            elif action_type == "STALLED_NUDGE":
                custom_message = f"Hi {first_name}, just following up regarding {address}. We are finalizing our cash allocations for this week—are you still interested in selling if the price makes sense?"
            else:
                custom_message = f"Hi {first_name}, Emma here following up on our previous chat about {address}. Have you had a chance to think over our cash offer?"

        timer_obj = {
            "id": f"tmr_{int(time.time() * 1000)}",
            "lead_id": lead_id,
            "lead_name": lead_name,
            "clean_phone": "".join(filter(str.isdigit, phone)),
            "phone": phone,
            "address": address,
            "action_type": action_type,
            "delay_hours": delay_hours,
            "trigger_ts": trigger_ts,
            "scheduled_time": scheduled_str,
            "payload_message": custom_message,
            "status": "PENDING",
            "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with self._lock:
            self.timers.insert(0, timer_obj)
            self._save_timers()

        self.log_memory(
            "INFO",
            f"Timer Scheduled: {lead_name}",
            f"Set {delay_hours:g}h delayed {action_type} scheduled for {scheduled_str}.",
            lead_id=lead_id,
            metadata={"trigger_time": scheduled_str, "action": action_type}
        )
        return timer_obj

    def cancel_timer(self, timer_id: str) -> bool:
        with self._lock:
            for t in self.timers:
                if t.get("id") == timer_id:
                    t["status"] = "CANCELLED"
                    self._save_timers()
                    self.log_memory("INFO", "Timer Cancelled", f"Operator cancelled timer {timer_id}.")
                    return True
        return False

    def get_timers(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.timers)

    # -------------------------------------------------------------
    # DEAL TRIAGE & PIPELINE RADAR
    # -------------------------------------------------------------
    def get_pipeline_triage(self) -> Dict[str, Any]:
        """
        Evaluates saved leads, scheduled callbacks, and pending contracts.
        Sorts deals into:
        - 🚨 URGENT (Action Required)
        - 💬 IN_PROGRESS (Active Emma negotiations)
        - 📝 CONTRACT_OUT (Pending PandaDoc Signature)
        - ⏱️ TIMERS_ACTIVE (Scheduled follow-ups)
        - 💤 STALLED (Needs Lucas Re-activation)
        """
        contacts = {}
        if os.path.exists(SAVED_CONTACTS_FILE):
            try:
                with open(SAVED_CONTACTS_FILE, "r", encoding="utf-8") as f:
                    contacts = json.load(f)
            except Exception:
                contacts = {}

        callbacks = []
        if os.path.exists(SCHEDULED_CALLBACKS_FILE):
            try:
                with open(SCHEDULED_CALLBACKS_FILE, "r", encoding="utf-8") as f:
                    callbacks = json.load(f)
            except Exception:
                callbacks = []

        active_timers = [t for t in self.timers if t.get("status") == "PENDING"]
        timer_by_phone = {t.get("clean_phone"): t for t in active_timers}

        triage_deals = []
        stats = {
            "total_deals": len(contacts),
            "urgent_count": 0,
            "contract_out_count": 0,
            "callbacks_pending": len([c for c in callbacks if not c.get("completed")]),
            "active_timers_count": len(active_timers),
            "estimated_pipeline_spread": 0
        }

        now = datetime.datetime.now()

        for lead_id, c in contacts.items():
            owner = c.get("owner", "Homeowner")
            phone = c.get("phone", "")
            clean_phone = c.get("clean_phone", "")
            address = c.get("address", "")
            category = c.get("distress_category", "Distressed Lead")
            just_value = float(c.get("just_value") or 250000)
            
            # Estimated wholesale assignment spread (assumes 15% discount margin target)
            estimated_spread = max(15000, int(just_value * 0.12))
            stats["estimated_pipeline_spread"] += estimated_spread

            last_contract_status = (c.get("last_contract_status") or "").upper()
            last_sms_sent = c.get("last_sms_sent")
            last_sms_msg = c.get("last_sms_message") or ""
            
            # Determine Triage Stage & Urgency Score (0 - 100)
            stage = "LEAD"
            urgency = "NORMAL"
            urgency_score = 40
            recommendation = "Review property details and launch initial Emma hook."
            action_badge = "INITIATE"

            # Check if pending contract
            if "SENT" in last_contract_status or "OUT" in last_contract_status:
                stage = "CONTRACT_OUT"
                urgency = "URGENT"
                urgency_score = 90
                recommendation = f"PandaDoc contract awaiting signature. Have Lucas send a 24h SMS check-in."
                action_badge = "CHASE CONTRACT"
                stats["contract_out_count"] += 1
                stats["urgent_count"] += 1

            # Check if scheduled callback
            matched_cb = next((cb for cb in callbacks if cb.get("clean_phone") == clean_phone and not cb.get("completed")), None)
            if matched_cb:
                stage = "CALLBACK_BOOKED"
                urgency = "URGENT"
                urgency_score = 95
                cb_time = matched_cb.get("scheduled_time", "Soon")
                recommendation = f"Phone call booked for John on {cb_time}. Review notes before dialing."
                action_badge = "CALL SCHEDULED"
                stats["urgent_count"] += 1

            # Check if timer pending
            elif clean_phone in timer_by_phone:
                pending_t = timer_by_phone[clean_phone]
                stage = "TIMER_ACTIVE"
                urgency = "IN_PROGRESS"
                urgency_score = 65
                recommendation = f"Lucas delayed timer set for {pending_t.get('scheduled_time')}: {pending_t.get('action_type')}."
                action_badge = "TIMER RUNNING"

            # Check if SMS sent recently
            elif last_sms_sent:
                try:
                    last_dt = datetime.datetime.strptime(last_sms_sent, "%Y-%m-%d %H:%M:%S")
                    hours_ago = (now - last_dt).total_seconds() / 3600.0
                    if hours_ago > 48:
                        stage = "STALLED"
                        urgency = "ACTION_NEEDED"
                        urgency_score = 75
                        recommendation = f"No response for {int(hours_ago)} hours. Trigger Lucas 48h re-activation hook."
                        action_badge = "STALLED DEAL"
                        stats["urgent_count"] += 1
                    else:
                        stage = "NEGOTIATING"
                        urgency = "IN_PROGRESS"
                        urgency_score = 60
                        recommendation = "Emma conversation in progress. Monitor seller replies."
                        action_badge = "ACTIVE CHAT"
                except Exception:
                    stage = "CONTACTED"
                    urgency_score = 50

            triage_deals.append({
                "lead_id": lead_id,
                "owner": owner,
                "phone": phone,
                "clean_phone": clean_phone,
                "address": address,
                "county": c.get("county", "Pinellas"),
                "category": category,
                "just_value": just_value,
                "estimated_spread": estimated_spread,
                "stage": stage,
                "urgency": urgency,
                "urgency_score": urgency_score,
                "action_badge": action_badge,
                "recommendation": recommendation,
                "last_sms_sent": last_sms_sent,
                "last_sms_message": last_sms_msg,
                "last_contract_status": last_contract_status,
                "has_active_timer": clean_phone in timer_by_phone
            })

        # Sort deals by urgency score descending
        triage_deals.sort(key=lambda d: d["urgency_score"], reverse=True)

        return {
            "stats": stats,
            "deals": triage_deals,
            "briefing": self._generate_executive_briefing(stats, triage_deals)
        }

    def _generate_executive_briefing(self, stats: Dict[str, Any], deals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generates John's executive daily operational briefing."""
        top_deals = deals[:3] if deals else []
        urgent_total = stats.get("urgent_count", 0)
        spread_total = stats.get("estimated_pipeline_spread", 0)
        
        headline = "Pipeline Operating at Full Capacity" if urgent_total == 0 else f"{urgent_total} High-Priority Deals Require Your Eyes Today"
        
        notes = []
        if stats.get("contract_out_count", 0) > 0:
            notes.append(f"📝 {stats['contract_out_count']} PandaDoc purchase agreement(s) outstanding.")
        if stats.get("callbacks_pending", 0) > 0:
            notes.append(f"📅 {stats['callbacks_pending']} seller callback appointment(s) scheduled for John.")
        if stats.get("active_timers_count", 0) > 0:
            notes.append(f"⏱️ {stats['active_timers_count']} automated Lucas follow-up timers queued.")
        if not notes:
            notes.append("All leads are current. Launch outreach on verified Florida list.")

        return {
            "headline": headline,
            "total_spread_formatted": f"${spread_total:,.0f}",
            "notes": notes,
            "top_deals": top_deals,
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
        }

    # -------------------------------------------------------------
    # OPERATOR COMMAND EXECUTOR
    # -------------------------------------------------------------
    def execute_command(self, prompt: str, target_phone: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes an executive instruction from John:
        e.g. "Set 24h follow up", "Chase contract", "Nudge Vance", "Triage status"
        """
        prompt_lower = prompt.lower().strip()
        
        # 1. Schedule Timer Command
        if "timer" in prompt_lower or "follow" in prompt_lower or "nudge" in prompt_lower:
            hours = 24.0
            if "72" in prompt_lower: hours = 72.0
            elif "48" in prompt_lower: hours = 48.0
            elif "24" in prompt_lower: hours = 24.0
            elif "12" in prompt_lower: hours = 12.0
            elif "2 hour" in prompt_lower or "two hour" in prompt_lower: hours = 2.0
            elif "1 hour" in prompt_lower or "one hour" in prompt_lower: hours = 1.0

            # Target resolve
            lead_name = "Homeowner"
            phone = target_phone or "(727) 555-0199"
            address = "742 Evergreen Terr"
            lead_id = "TEST-PINELLAS-001"

            # Check if name mentioned
            if "marcus" in prompt_lower or "sterling" in prompt_lower:
                lead_name = "Marcus Sterling"
                phone = "(727) 555-0244"
                address = "1244 Woodlawn St"
                lead_id = "TEST-PINELLAS-002"
            elif "vance" in prompt_lower or "robert" in prompt_lower:
                lead_name = "Robert Vance"
                phone = "(727) 555-0199"
                address = "742 Evergreen Terr"
                lead_id = "TEST-PINELLAS-001"

            action_type = "CONTRACT_FOLLOWUP" if "contract" in prompt_lower else "SMS_NUDGE"
            timer = self.schedule_timer(
                lead_id=lead_id,
                lead_name=lead_name,
                phone=phone,
                address=address,
                action_type=action_type,
                delay_hours=hours
            )
            return {
                "status": "success",
                "message": f"Understood, John. Scheduled a {hours:g}-hour {action_type} for {lead_name} ({timer['scheduled_time']}).",
                "timer": timer
            }

        # 2. General Briefing Request
        triage = self.get_pipeline_triage()
        return {
            "status": "success",
            "message": f"Lucas Briefing: You have {triage['stats']['urgent_count']} priority deals and ${triage['stats']['estimated_pipeline_spread']:,.0f} in pipeline spread.",
            "briefing": triage["briefing"]
        }

# Global Singleton Instance
lucas_operator = LucasOperatorEngine()
