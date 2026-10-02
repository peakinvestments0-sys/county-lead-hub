import os
import json
import re
import time
import smtplib
import urllib.parse
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Dict, Any, Optional, Tuple, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CALLBACKS_FILE = os.path.join(DATA_DIR, "scheduled_callbacks.json")
EMAIL_SETTINGS_FILE = os.path.join(DATA_DIR, "email_settings.json")

DEFAULT_CALENDAR_RECIPIENT = "johngroberts76@gmail.com"

def load_scheduled_callbacks() -> List[Dict[str, Any]]:
    if os.path.exists(CALLBACKS_FILE):
        try:
            with open(CALLBACKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_scheduled_callbacks(callbacks: List[Dict[str, Any]]):
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(CALLBACKS_FILE, "w", encoding="utf-8") as f:
            json.dump(callbacks, f, indent=2)
    except Exception:
        pass

def parse_appointment_datetime(time_str: str) -> Tuple[datetime, datetime]:
    """
    Parses natural language times like 'afternoon', 'tomorrow at 10am', 'tomorrow morning'
    into start and end datetimes (default 15-minute appointment duration).
    """
    now = datetime.now()
    clean = (time_str or "").lower().strip()
    
    # Target date: default today
    target_date = now.date()
    if "tomorrow" in clean:
        target_date = target_date + timedelta(days=1)
    elif "next week" in clean:
        target_date = target_date + timedelta(days=7)
    
    # Target time
    target_hour = 14  # Default 2:00 PM for afternoon
    target_minute = 0
    
    # Check for specific hour mention like "10am", "10:30am", "3pm", "at 4"
    hour_match = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', clean)
    if hour_match:
        h = int(hour_match.group(1))
        m = int(hour_match.group(2)) if hour_match.group(2) else 0
        ampm = (hour_match.group(3) or "").lower()
        if ampm == "pm" and h < 12:
            h += 12
        elif ampm == "am" and h == 12:
            h = 0
        elif not ampm:
            # Infer standard business hours (e.g. 1-6 is PM, 9-11 is AM)
            if 1 <= h <= 6:
                h += 12
        target_hour = h
        target_minute = m
    elif "morning" in clean:
        target_hour = 10
        target_minute = 0
    elif "evening" in clean or "night" in clean:
        target_hour = 18
        target_minute = 0
    elif "afternoon" in clean:
        # If it's already past 2pm today, default to 1 hour from now or 4pm
        if target_date == now.date() and now.hour >= 14:
            target_hour = min(now.hour + 1, 17)
        else:
            target_hour = 14
        target_minute = 0
    else:
        # If unknown, schedule 2 hours from now during business hours
        target_hour = max(10, min(now.hour + 2, 17))
        target_minute = 0

    start_dt = datetime.combine(target_date, datetime.min.time()).replace(hour=target_hour, minute=target_minute, second=0)
    # If the calculated time is already in the past for today, push to tomorrow
    if start_dt <= now and target_date == now.date():
        start_dt = start_dt + timedelta(days=1)
        
    end_dt = start_dt + timedelta(minutes=15)
    return start_dt, end_dt

def build_google_calendar_url(lead: Dict[str, Any], start_dt: datetime, end_dt: datetime) -> str:
    """Generates a 1-click Google Calendar web creation link as a direct fallback."""
    title = f"📞 Call {lead.get('owner_name', 'Homeowner')} ({lead.get('phone', '')})"
    details = (
        f"Seller Phone Call with John\n\n"
        f"Owner: {lead.get('owner_name', 'Homeowner')}\n"
        f"Phone: {lead.get('phone', 'N/A')}\n"
        f"Address: {lead.get('property_address', 'Florida Property')}\n"
        f"PIN: {lead.get('parcel_id', 'N/A')}\n"
        f"Distress: {lead.get('distress_category', 'General Distress')}\n"
        f"Est. Market: ${lead.get('market_value', 0):,.0f}\n"
        f"Assessed: ${lead.get('just_value', 0):,.0f}\n\n"
        f"Notes: Emma scheduled this 5-minute acquisitions callback via SMS."
    )
    location = lead.get('property_address', 'Phone Appointment')
    fmt = "%Y%m%dT%H%M%S"
    dates_str = f"{start_dt.strftime(fmt)}/{end_dt.strftime(fmt)}"
    
    base_url = "https://calendar.google.com/calendar/render"
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates_str,
        "details": details,
        "location": location,
        "add": DEFAULT_CALENDAR_RECIPIENT
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"

def build_ical_content(event_id: str, lead: Dict[str, Any], start_dt: datetime, end_dt: datetime) -> str:
    """Creates a standard RFC 5545 iCalendar string with a 15-minute phone alarm."""
    utc_format = "%Y%m%dT%H%M%SZ"
    # Convert to UTC string representation (or local floating)
    dtstamp = datetime.utcnow().strftime(utc_format)
    # Using local floating time without Z so it matches user's local timezone perfectly
    dtstart_str = start_dt.strftime("%Y%m%dT%H%M%S")
    dtend_str = end_dt.strftime("%Y%m%dT%H%M%S")
    
    owner = lead.get('owner_name', 'Homeowner')
    phone = lead.get('phone', 'N/A')
    address = lead.get('property_address', 'Florida Property')
    pin = lead.get('parcel_id', 'N/A')
    market = lead.get('market_value', 0)
    
    summary = f"📞 Call {owner} ({phone}) - {address}"
    desc = (
        f"Wholesale Acquisitions Phone Appointment\\n\\n"
        f"Owner: {owner}\\n"
        f"Phone: {phone}\\n"
        f"Address: {address}\\n"
        f"PIN: {pin}\\n"
        f"Est. Market: ${market:,.0f}\\n\\n"
        f"Scheduled by Emma via 2-Way SMS."
    )

    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//Peak Investments//Florida Lead Hub Calendar Sync//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{event_id}@407flips.com",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart_str}",
        f"DTEND:{dtend_str}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{desc}",
        f"LOCATION:{address}",
        "STATUS:CONFIRMED",
        f"ORGANIZER;CN=Emma:mailto:john@407flips.com",
        f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=ACCEPTED;CN=John Roberts:mailto:{DEFAULT_CALENDAR_RECIPIENT}",
        "BEGIN:VALARM",
        "TRIGGER:-PT15M",
        "ACTION:DISPLAY",
        f"DESCRIPTION:Reminder: Call {owner} in 15 minutes",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR"
    ]
    return "\r\n".join(lines)

def send_calendar_invite_email(
    lead: Dict[str, Any], 
    time_str: str, 
    recipient_email: str = DEFAULT_CALENDAR_RECIPIENT
) -> Dict[str, Any]:
    """
    Sends an automated calendar invite (.ics) via SMTP2GO to John's Gmail.
    Google automatically places the event onto Google Calendar.
    """
    start_dt, end_dt = parse_appointment_datetime(time_str)
    event_id = f"appt_{int(time.time())}_{lead.get('clean_phone', 'lead')}"
    ical_data = build_ical_content(event_id, lead, start_dt, end_dt)
    gcal_url = build_google_calendar_url(lead, start_dt, end_dt)
    
    # Load SMTP settings
    smtp_settings = {}
    if os.path.exists(EMAIL_SETTINGS_FILE):
        try:
            with open(EMAIL_SETTINGS_FILE, "r", encoding="utf-8") as f:
                smtp_settings = json.load(f)
        except Exception:
            pass

    host = smtp_settings.get("smtp_server", "mail.smtp2go.com")
    port = int(smtp_settings.get("smtp_port", 2525))
    user = smtp_settings.get("smtp_user", "407flips.com")
    pwd = smtp_settings.get("smtp_password", "")
    sender_email = smtp_settings.get("sender_email", "john@407flips.com")
    sender_name = "Emma (Acquisitions) | 407 Flips"

    owner = lead.get('owner_name', 'Homeowner')
    phone = lead.get('phone', 'N/A')
    address = lead.get('property_address', 'Florida Property')
    market = lead.get('market_value', 0)
    time_display = start_dt.strftime("%A, %b %d at %I:%M %p")

    # Construct MIMEMultipart email with calendar invitation
    msg = MIMEMultipart("mixed")
    msg["From"] = f"{sender_name} <{sender_email}>"
    msg["To"] = recipient_email
    msg["Subject"] = f"📅 Confirmed Call: {owner} ({time_str.title()}) • {address}"

    html_content = f"""
    <div style="font-family: Arial, sans-serif; background-color: #0b1220; color: #f8fafc; padding: 24px; border-radius: 12px; max-width: 600px; margin: 0 auto; border: 1px solid #1e293b;">
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 16px;">
            <span style="font-size: 24px;">🤖</span>
            <div>
                <h2 style="margin: 0; color: #38bdf8; font-size: 18px;">Emma Confirmed a Phone Appointment!</h2>
                <p style="margin: 2px 0 0; color: #94a3b8; font-size: 12px;">Google Calendar invitation attached automatically.</p>
            </div>
        </div>

        <div style="background-color: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #10b981;">
            <div style="font-size: 14px; font-weight: bold; color: #ffffff; margin-bottom: 4px;">📅 {time_display}</div>
            <div style="font-size: 13px; color: #34d399; font-weight: bold;">Seller requested: "{time_str}"</div>
        </div>

        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 13px;">
            <tr style="border-bottom: 1px solid #334155;">
                <td style="padding: 8px 0; color: #94a3b8; width: 120px;">Homeowner:</td>
                <td style="padding: 8px 0; color: #ffffff; font-weight: bold;">{owner}</td>
            </tr>
            <tr style="border-bottom: 1px solid #334155;">
                <td style="padding: 8px 0; color: #94a3b8;">Phone:</td>
                <td style="padding: 8px 0; color: #38bdf8; font-weight: bold; font-family: monospace;">{phone}</td>
            </tr>
            <tr style="border-bottom: 1px solid #334155;">
                <td style="padding: 8px 0; color: #94a3b8;">Address:</td>
                <td style="padding: 8px 0; color: #ffffff;">{address}</td>
            </tr>
            <tr style="border-bottom: 1px solid #334155;">
                <td style="padding: 8px 0; color: #94a3b8;">Est. Market:</td>
                <td style="padding: 8px 0; color: #10b981; font-weight: bold;">${market:,.0f}</td>
            </tr>
        </table>

        <div style="text-align: center; margin-top: 24px;">
            <a href="{gcal_url}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 13px; display: inline-block;">
                📅 Open in Google Calendar
            </a>
        </div>
    </div>
    """

    # Add HTML body
    part_html = MIMEText(html_content, "html", "utf-8")
    msg.attach(part_html)

    # Attach the .ics meeting invite
    part_cal = MIMEBase("text", "calendar", method="REQUEST", name="invite.ics")
    part_cal.set_payload(ical_data.encode("utf-8"))
    encoders.encode_base64(part_cal)
    part_cal.add_header("Content-Disposition", "attachment; filename=invite.ics")
    part_cal.add_header("Content-Class", "urn:content-classes:calendarmessage")
    msg.attach(part_cal)

    # Dispatch via SMTP if credentials are present
    sent_status = "SAVED_LOCAL"
    if pwd:
        try:
            with smtplib.SMTP(host, port, timeout=12) as server:
                server.login(user, pwd)
                server.sendmail(sender_email, [recipient_email], msg.as_string())
                sent_status = "SENT_SMTP2GO"
        except Exception as e:
            sent_status = f"SMTP_ERROR: {str(e)}"

    # Record in persistent scheduled callbacks list
    callback_entry = {
        "id": event_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "scheduled_time_raw": time_str,
        "start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "display_time": time_display,
        "owner": owner,
        "phone": phone,
        "clean_phone": lead.get("clean_phone") or "".join(filter(str.isdigit, str(phone))),
        "address": address,
        "parcel_id": lead.get("parcel_id", ""),
        "market_value": market,
        "status": "PENDING",  # PENDING or COMPLETED
        "email_recipient": recipient_email,
        "email_status": sent_status,
        "gcal_url": gcal_url
    }

    callbacks = load_scheduled_callbacks()
    # Update if existing, or insert at top
    callbacks = [c for c in callbacks if c.get("id") != event_id and c.get("clean_phone") != callback_entry["clean_phone"]]
    callbacks.insert(0, callback_entry)
    save_scheduled_callbacks(callbacks)

    return {
        "status": "success",
        "callback": callback_entry,
        "email_status": sent_status,
        "gcal_url": gcal_url
    }
