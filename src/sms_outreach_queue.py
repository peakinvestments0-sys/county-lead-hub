"""Persistent, deliberately paced initial SMS and unanswered-contact follow-ups."""
from collections import Counter
from pathlib import Path
import json
import re
import threading
import time
import uuid
from src.initial_sms_templates import TEMPLATE_IDS

INTERVAL_SECONDS = 90
FOLLOW_UP_TEMPLATES = tuple(
    {'id': f'follow_up_{i}', 'body': body}
    for i, body in enumerate((
        "Hello, I'm trying to locate the property owner of {Address}. Would that be you?",
        "Hi, I'm looking for the homeowner at {Address}. Is that you?",
        "Hello, is this the right person to reach about ownership of {Address}?",
        "Hi there, I'm trying to get in touch with the owner of {Address}. Are you the owner?",
        "Hello, would you happen to be the homeowner at {Address}?",
        "Hi, I wanted to check if you own the property at {Address}. Do I have the right person?",
        "Hello, I'm hoping to reach the property owner of {Address}. Is this you?",
        "Hi there, are you the person who owns the home at {Address}?",
        "Hello, just following up. I'm looking for the owner of {Address}. Would that be you?",
        "Hi, am I reaching the homeowner for {Address}, or do I have the wrong person?",
    ), 1)
)


def normalize_phone(value):
    digits = re.sub(r'\D', '', str(value or ''))
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    return digits if len(digits) == 10 and digits[0] in '23456789' else ''


def fill_template(body, contact, county):
    owner = str(contact.get('owner') or '').strip()
    generic = not owner or owner.lower() in ('homeowner', 'property owner', 'unknown', 'unknown owner', 'florida homeowner')
    corporate = re.search(r'\b(llc|inc|corp|trust|estate|properties|holdings|group|management|solutions|services|investments|realty|real estate)\b', owner, re.I)
    words = owner.split()
    if generic or corporate:
        first, last = 'there', ''
    elif owner.isupper() and len(words) >= 2:
        first, last = words[-1].title(), ' '.join(words[:-1]).title()
    else:
        first, last = words[0].title(), ' '.join(words[1:]).title()
    values = {'FirstName': first, 'LastName': last, 'Address': str(contact.get('address') or 'your property').split(',')[0].strip(),
              'City': contact.get('city') or county, 'County': county, 'State': contact.get('state') or 'FL', 'Phone': '(407) 555-FLIP'}
    return re.sub(r'\{(FirstName|LastName|Address|City|County|State|Phone)\}', lambda m: str(values[m.group(1)]), body)


class SmsOutreachQueue:
    def __init__(self, path, load_contacts, load_history, load_templates, is_blocked, send, clock=time.time):
        self.path = Path(path)
        self.load_contacts, self.load_history = load_contacts, load_history
        self.load_templates, self.is_blocked, self.send, self.clock = load_templates, is_blocked, send, clock
        self.lock = threading.RLock()
        self.worker = None
        self.load_error = ''
        self.state = {'status': 'idle', 'items': [], 'sent_phones': [], 'skipped_reasons': {}}
        if self.path.exists():
            try:
                self.state = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(self.state.get('items'), list) or self.state.get('status') not in ('idle', 'running', 'paused', 'stopped', 'complete'):
                    raise ValueError('Invalid queue data')
            except Exception:
                self.load_error = 'Saved Auto SMS queue could not be read. Auto SMS is disabled until that file is recovered; the rest of Lead Hub remains available.'
                self.state = {'status': 'error', 'items': [], 'sent_phones': [], 'notice': self.load_error}
            # The gateway may have accepted a text before the server stopped.
            # Never resend a message whose outcome is unknown.
            interrupted = [i for i in self.state['items'] if i['status'] == 'sending']
            if interrupted:
                for item in interrupted:
                    item['status'] = 'uncertain'
                self.state['held_phones'] = sorted(set(self.state.get('held_phones', [])) | {i['phone'] for i in interrupted})
                self.state['status'] = 'paused'
                self.state['notice'] = 'A send was interrupted. Check its outreach history before continuing; it will not be retried.'
                self._save()
        if not self.load_error:
            try:
                history = self.load_history()
            except Exception:
                # Eligibility still requires readable history in preview/start/tick.
                history = []
            replied, followed_up = self._follow_up_tracking(history)
            manual = set(self.state.get('manual_reply_phones', [])) | followed_up
            tracking = {'replied_phones': sorted(replied), 'follow_up_sent_phones': sorted(followed_up),
                        'manual_reply_phones': sorted(manual)}
            if any(value != self.state.get(key, []) for key, value in tracking.items()):
                self.state.update(tracking)
                self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, indent=2), encoding='utf-8')
        temp.replace(self.path)

    def _contacted_phones(self, contacts, history):
        phones = set(self.state.get('sent_phones', [])) | set(self.state.get('held_phones', []))
        for contact in contacts.values():
            if str(contact.get('last_sms_status') or '').startswith('SENT'):
                phones.add(normalize_phone(contact.get('phone') or contact.get('clean_phone')))
        for entry in history:
            if entry.get('channel') == 'SMS' and entry.get('direction', 'OUTBOUND') == 'OUTBOUND' and entry.get('status') == 'SENT':
                phones.add(normalize_phone(entry.get('phone') or entry.get('recipient')))
        return phones

    def _follow_up_tracking(self, history):
        replied = set(self.state.get('replied_phones', []))
        followed_up = set(self.state.get('follow_up_sent_phones', []))
        for entry in history:
            if entry.get('channel') != 'SMS':
                continue
            phone = normalize_phone(entry.get('phone') or entry.get('sender_phone') or entry.get('recipient'))
            if not phone:
                continue
            if entry.get('direction') == 'INBOUND':
                replied.add(phone)
            elif entry.get('status') == 'SENT' and str(entry.get('opener_angle') or '').startswith('follow_up_'):
                followed_up.add(phone)
        return replied, followed_up

    def record_reply(self, phone):
        """Keep reply detection after the rolling inbox history has been trimmed."""
        phone = normalize_phone(phone)
        with self.lock:
            if not phone or self.load_error or phone in self.state.get('replied_phones', []):
                return
            self.state['replied_phones'] = sorted(set(self.state.get('replied_phones', [])) | {phone})
            self._save()

    def has_replied(self, phone):
        with self.lock:
            replied, _ = self._follow_up_tracking(self.load_history())
            return normalize_phone(phone) in replied

    def requires_manual_reply(self, phone):
        with self.lock:
            return normalize_phone(phone) in self.state.get('manual_reply_phones', [])

    def pending_initial_resends(self):
        with self.lock:
            return dict(self.state.get('initial_resend_approvals', {}))

    def record_sent(self, phone):
        """A manual send also consumes any one-time initial resend approval."""
        phone = normalize_phone(phone)
        with self.lock:
            approvals = self.state.get('initial_resend_approvals', {})
            if phone and phone in approvals.values():
                self.state['initial_resend_approvals'] = {pid: number for pid, number in approvals.items() if number != phone}
                self.state['sent_phones'] = sorted(set(self.state.get('sent_phones', [])) | {phone})
                self._save()

    def reset_initial(self, parcel_ids, county):
        """Permit one new initial text without deleting history or suppression data."""
        with self.lock:
            if self.load_error:
                raise ValueError(self.load_error)
            if self.state['status'] in ('running', 'paused') or any(i['status'] == 'sending' for i in self.state['items']):
                raise ValueError('Stop the existing Auto SMS queue before resetting leads.')
            if not str(county or '').strip():
                raise ValueError('A county is required for a resend reset.')
            contacts, history = self.load_contacts(), self.load_history()
            contacted = self._contacted_phones(contacts, history)
            replied, _ = self._follow_up_tracking(history)
            approvals = dict(self.state.get('initial_resend_approvals', {}))
            reasons, selected, seen = Counter(), [], set()
            for pid in dict.fromkeys(str(pid).strip() for pid in parcel_ids):
                contact = contacts.get(pid) or {}
                phone = normalize_phone(contact.get('phone') or contact.get('clean_phone'))
                if str(contact.get('county') or '').strip().casefold() != county.strip().casefold():
                    reason = 'Different county'
                elif phone in replied:
                    reason = 'Already replied'
                else:
                    reason = self._reason(pid, contact, set(), replied=replied)
                if not reason and phone not in contacted:
                    reason = 'Not previously contacted'
                if not reason and phone in seen:
                    reason = 'Duplicate phone'
                if reason:
                    reasons[reason] += 1
                    continue
                seen.add(phone)
                approvals[pid] = phone
                selected.append(pid)
            self.state['initial_resend_approvals'] = approvals
            self._save()
            return {'reset': len(selected), 'parcel_ids': selected, 'skipped_reasons': dict(reasons)}

    def _reason(self, pid, contact, contacted, campaign='initial', replied=None, followed_up=None):
        if not contact or not str(contact.get('source') or '').startswith('Skip Trace CSV'):
            return 'Not an imported contact'
        if pid.startswith('TEST-'):
            return 'Test lead'
        phone = normalize_phone(contact.get('phone') or contact.get('clean_phone'))
        if not phone:
            return 'Missing or invalid phone'
        if campaign == 'follow_up':
            if phone in (replied or set()):
                return 'Already replied'
            if phone in (followed_up or set()):
                return 'Already followed up'
            if phone in self.state.get('held_phones', []):
                return 'Previous send needs review'
            if phone not in contacted:
                return 'No previous SMS'
            address = str(contact.get('address') or '').split(',')[0].strip()
            if not address or address.lower() in ('unknown', 'unknown address', 'your property', 'n/a'):
                return 'Missing property address'
        else:
            if phone in self.state.get('held_phones', []):
                return 'Previous send needs review'
            approved = self.state.get('initial_resend_approvals', {}).get(pid) == phone
            if approved and phone in (replied or set()):
                return 'Already replied'
            if phone in contacted and not approved:
                return 'Already contacted'
        blocked, reason = self.is_blocked(phone, contact)
        if blocked:
            return reason or 'Blocked number'
        return ''

    def _prepare(self, parcel_ids, campaign='initial'):
        if self.load_error:
            raise ValueError(self.load_error)
        if campaign not in ('initial', 'follow_up'):
            raise ValueError('Unknown SMS campaign')
        if campaign == 'follow_up':
            templates = list(FOLLOW_UP_TEMPLATES)
        else:
            configured = {t['id']: t for t in self.load_templates().get('sms', []) if t.get('id') in TEMPLATE_IDS}
            if any(not str(configured.get(tid, {}).get('body') or '').strip() for tid in TEMPLATE_IDS):
                raise ValueError('All four SMS owner-check templates must have message text')
            templates = [configured[tid] for tid in TEMPLATE_IDS]
        contacts = self.load_contacts()
        history = self.load_history()
        contacted, seen, seen_ids = self._contacted_phones(contacts, history), set(), set()
        replied, followed_up = self._follow_up_tracking(history)
        items, reasons = [], Counter()
        for value in parcel_ids:
            pid = str(value).strip()
            if pid in seen_ids:
                continue
            seen_ids.add(pid)
            contact = contacts.get(pid)
            reason = self._reason(pid, contact, contacted, campaign, replied, followed_up)
            phone = normalize_phone((contact or {}).get('phone') or (contact or {}).get('clean_phone'))
            if not reason and phone in seen:
                reason = 'Duplicate phone'
            if reason:
                reasons[reason] += 1
                continue
            seen.add(phone)
            items.append({'parcel_id': pid, 'phone': phone, 'owner': contact.get('owner') or 'Property Owner',
                          'county': contact.get('county') or '', 'status': 'pending'})
        return items, dict(reasons), templates, replied, followed_up

    def preview(self, parcel_ids, campaign='initial'):
        with self.lock:
            items, reasons, _, _, _ = self._prepare(parcel_ids, campaign)
            return {'eligible': len(items), 'skipped': sum(reasons.values()), 'skipped_reasons': reasons,
                    'campaign': campaign, 'interval_seconds': INTERVAL_SECONDS}

    def start(self, parcel_ids, campaign='initial'):
        with self.lock:
            if self.state['status'] in ('running', 'paused') or any(i['status'] == 'sending' for i in self.state['items']):
                raise ValueError('An Auto SMS queue already exists. Resume or stop it first.')
            items, reasons, templates, replied, followed_up = self._prepare(parcel_ids, campaign)
            if not items:
                if campaign == 'follow_up':
                    raise ValueError('No eligible follow-ups. Only previously texted imported contacts with no reply qualify. Already-followed-up, blocked, duplicate, and missing-address numbers are skipped.')
                raise ValueError('No eligible imported leads. Already-contacted, missing, duplicate, and blocked numbers are skipped.')
            counties = sorted({i['county'] for i in items if i['county']})
            self.state = {'id': str(uuid.uuid4()), 'status': 'running', 'campaign': campaign, 'counties': counties, 'items': items,
                          'templates': templates, 'angle_index': 0, 'next_send_at': self.clock(),
                          'sent_phones': self.state.get('sent_phones', []), 'held_phones': self.state.get('held_phones', []),
                          'initial_resend_approvals': self.state.get('initial_resend_approvals', {}),
                          'replied_phones': sorted(replied), 'follow_up_sent_phones': sorted(followed_up),
                          'manual_reply_phones': sorted(set(self.state.get('manual_reply_phones', [])) | followed_up),
                          'skipped_reasons': reasons, 'notice': ''}
            self._save()
            return self.status()

    def control(self, action):
        with self.lock:
            if self.load_error:
                raise ValueError(self.load_error)
            if action == 'pause' and self.state['status'] == 'running':
                self.state['status'] = 'paused'
            elif action == 'resume' and self.state['status'] == 'paused':
                self.state['status'] = 'running'
                self.state['notice'] = ''
                self.state['next_send_at'] = max(self.clock(), self.state.get('next_send_at', 0))
            elif action == 'stop' and self.state['status'] in ('running', 'paused'):
                self.state['status'] = 'stopped'
            else:
                raise ValueError('That action is not available for this queue')
            self._save()
            return self.status()

    def status(self):
        with self.lock:
            counts = Counter(i['status'] for i in self.state['items'])
            pending = next((i for i in self.state['items'] if i['status'] == 'pending'), None)
            return {'status': self.state['status'], 'campaign': self.state.get('campaign', 'initial'),
                    'counties': self.state.get('counties', []), 'total': len(self.state['items']),
                    'sent': counts['sent'], 'remaining': counts['pending'], 'in_flight': bool(counts['sending']),
                    'failed': counts['failed'] + counts['uncertain'],
                    'skipped': sum(self.state.get('skipped_reasons', {}).values()),
                    'skipped_reasons': self.state.get('skipped_reasons', {}), 'notice': self.state.get('notice', ''),
                    'next_owner': (pending or {}).get('owner', ''), 'interval_seconds': INTERVAL_SECONDS,
                    'seconds_until_next': max(0, int(self.state.get('next_send_at', 0) - self.clock() + .999))}

    def tick(self):
        with self.lock:
            if self.state['status'] != 'running' or self.clock() < self.state.get('next_send_at', 0) or any(i['status'] == 'sending' for i in self.state['items']):
                return
            contacts = self.load_contacts()
            history = self.load_history()
            contacted = self._contacted_phones(contacts, history)
            replied, followed_up = self._follow_up_tracking(history)
            self.state['replied_phones'] = sorted(replied)
            self.state['follow_up_sent_phones'] = sorted(followed_up)
            campaign = self.state.get('campaign', 'initial')
            item = next((i for i in self.state['items'] if i['status'] == 'pending'), None)
            while item:
                contact = contacts.get(item['parcel_id'])
                reason = self._reason(item['parcel_id'], contact, contacted, campaign, replied, followed_up)
                if not reason and normalize_phone(contact.get('phone') or contact.get('clean_phone')) != item['phone']:
                    reason = 'Phone changed since queue started'
                if not reason:
                    break
                item['status'] = 'skipped'
                reasons = self.state['skipped_reasons']
                reasons[reason] = reasons.get(reason, 0) + 1
                item = next((i for i in self.state['items'] if i['status'] == 'pending'), None)
            if not item:
                self.state['status'] = 'complete'
                self._save()
                return
            template = self.state['templates'][self.state['angle_index'] % len(self.state['templates'])]
            county = str(contact.get('county') or '')
            payload = {'parcel_id': item['parcel_id'], 'phone': item['phone'], 'county': county,
                       'owner_name': contact.get('owner'), 'property_address': contact.get('address'),
                       'message': fill_template(template['body'], contact, county), 'opener_angle': template['id']}
            item['status'] = 'sending'
            # Consume before dispatch and persist with the sending state so a
            # crash, failed send, or later batch cannot reuse this permission.
            self.state['initial_resend_approvals'] = {
                pid: phone for pid, phone in self.state.get('initial_resend_approvals', {}).items()
                if phone != item['phone']
            }
            if campaign == 'follow_up':
                # Persist before sending, so an immediate reply never triggers Autopilot.
                self.state['manual_reply_phones'] = sorted(set(self.state.get('manual_reply_phones', [])) | {item['phone']})
            self.state['next_send_at'] = self.clock() + INTERVAL_SECONDS
            self._save()  # Persist before contacting the gateway, to prevent blind retries after a crash.
        try:
            result = self.send(payload)
        except Exception:
            result = {'status': 'error', 'message': 'Send outcome is unknown. Check outreach history; this number will not be retried.'}
        with self.lock:
            self.state['next_send_at'] = self.clock() + INTERVAL_SECONDS
            if result.get('status') == 'success':
                item['status'] = 'sent'
                self.state['sent_phones'] = sorted(set(self.state.get('sent_phones', [])) | {item['phone']})
                if campaign == 'follow_up':
                    self.state['follow_up_sent_phones'] = sorted(set(self.state.get('follow_up_sent_phones', [])) | {item['phone']})
                self.state['angle_index'] += 1
            elif result.get('suppressed'):
                item['status'] = 'skipped'
                reason = result.get('blocked_reason') or 'Blocked number'
                self.state['skipped_reasons'][reason] = self.state['skipped_reasons'].get(reason, 0) + 1
            else:
                item['status'] = 'failed'
                self.state['held_phones'] = sorted(set(self.state.get('held_phones', [])) | {item['phone']})
                self.state['notice'] = 'Send failed or its outcome is unknown. Check outreach history. Resume continues with the next lead; this number will not be retried.'
                if self.state['status'] == 'running':
                    self.state['status'] = 'paused'
            if self.state['status'] == 'running' and not any(i['status'] == 'pending' for i in self.state['items']):
                self.state['status'] = 'complete'
            self._save()

    def start_worker(self):
        with self.lock:
            if self.worker and self.worker.is_alive():
                return
            def run():
                while True:
                    try:
                        self.tick()
                    except Exception:
                        with self.lock:
                            self.state['status'] = 'paused'
                            self.state['notice'] = 'Auto SMS paused after an error. Check the queue before resuming.'
                            try:
                                self._save()
                            except Exception:
                                pass
                    time.sleep(1)
            self.worker = threading.Thread(target=run, name='auto-sms-outreach', daemon=True)
            self.worker.start()
