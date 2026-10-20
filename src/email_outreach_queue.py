"""Persistent sequential email outreach with no live sends during preview."""
from collections import Counter
from html import escape
from pathlib import Path
import json
import re
import threading
import time
import uuid

from src.saved_property_matches import is_explicit_probate
from src.sms_outreach_queue import fill_template

INTERVAL_SECONDS = 90


def normalize_email(value):
    text = str(value or '').strip().lower()
    if len(text) > 254 or text.count('@') != 1:
        return ''
    local, domain = text.split('@')
    if (not local or len(local) > 64 or local.startswith('.') or local.endswith('.') or '..' in local
            or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local) or '.' not in domain
            or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p) for p in domain.split('.'))):
        return ''
    return text


def property_key(pid, contact):
    return ':'.join((str(contact.get('state') or 'FL').upper(), str(contact.get('county') or '').lower(),
                     str(contact.get('matched_parcel_id') or pid)))


def select_template(contact):
    record = contact.get('property_match', {}).get('record', {})
    types = [record.get('Lead_Type') or contact.get('distress_category') or '']
    types += record.get('All_Lead_Types') or []
    if record.get('Has_Confirmed_Probate') == 'Yes' or (record.get('Has_Confirmed_Probate') != 'No'
                                                        and any(is_explicit_probate(t) for t in types)):
        return 'probate'
    if any(re.search(r'lis[ _]pendens|foreclosure', t, re.I) for t in types):
        return 'lis_pendens'
    if any(re.search(r'code', t, re.I) for t in types):
        return 'code_violation'
    return 'quick_cash'


def render_email(pid, contact, templates, settings):
    record = contact.get('property_match', {}).get('record', {})
    context = dict(contact)
    context['owner'] = contact.get('owner') or record.get('Clean_Full_Name') or 'Property Owner'
    context['address'] = record.get('Property_Address') or contact.get('address') or ''
    context['city'] = record.get('Property_City') or contact.get('city') or ''
    tid = select_template(contact)
    template = templates.get(tid, {})
    if not str(template.get('subject') or '').strip() or not str(template.get('body') or '').strip():
        raise ValueError(f'Email template {tid} needs a subject and message in Outreach Templates.')
    def fill(text):
        text = fill_template(text, context, contact.get('county') or '')
        return text.replace('(407) 555-FLIP', settings.get('company_phone') or '') \
                   .replace('john@407flips.com', settings.get('reply_to') or settings.get('sender_email') or '')
    subject, body = fill(template['subject']), fill(template['body'])
    if '\n' in subject or '\r' in subject or re.search(r'\{[A-Za-z]+\}', subject + body):
        raise ValueError(f'Email template {tid} has an invalid subject or unsupported placeholder.')
    footer = '\n\n' + (settings.get('company_name') or '407 Flips')
    if settings.get('business_address'):
        footer += '\n' + settings['business_address']
    footer += '\nIf you do not wish to receive property inquiries, reply REMOVE.'
    plain = body + footer
    html = ('<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;color:#334155">'
            '<h2 style="color:#0284c7">' + escape(settings.get('company_name') or '407 Flips') + '</h2>'
            + ''.join('<p style="line-height:1.6">' + escape(p).replace('\n', '<br>') + '</p>'
                      for p in body.split('\n\n'))
            + '<hr><p style="font-size:11px;color:#64748b">' + escape(footer.strip()).replace('\n', '<br>') + '</p></div>')
    return {'parcel_id': pid, 'recipient_email': normalize_email(contact.get('email')),
            'recipient_name': context['owner'], 'property_address': context['address'],
            'county': contact.get('county') or '', 'subject': subject, 'html_content': html,
            'plain_content': plain, 'template_type': tid, 'auto_outreach': True}


class EmailOutreachQueue:
    def __init__(self, path, load_contacts, load_history, load_templates, load_settings, is_blocked, send, clock=time.time):
        self.path, self.clock = Path(path), clock
        self.load_contacts, self.load_history, self.load_templates = load_contacts, load_history, load_templates
        self.load_settings, self.is_blocked, self.send = load_settings, is_blocked, send
        self.lock, self.worker, self.load_error = threading.RLock(), None, ''
        self.state = {'status': 'idle', 'items': [], 'skipped_reasons': {}}
        if self.path.exists():
            try:
                self.state = json.loads(self.path.read_text(encoding='utf-8'))
                if (self.state['status'] not in ('idle', 'running', 'paused', 'stopped', 'complete')
                        or not isinstance(self.state['items'], list)
                        or any(not isinstance(item, dict) or not {'parcel_id', 'email', 'property_key', 'status'} <= item.keys()
                               or item['status'] not in ('pending', 'sending', 'sent', 'skipped', 'failed', 'uncertain')
                               for item in self.state['items'])):
                    raise ValueError('Invalid queue data')
            except Exception:
                self.load_error = 'Saved Auto Email queue could not be read. Recover it before starting another batch.'
                self.state = {'status': 'error', 'items': [], 'notice': self.load_error}
            for item in self.state['items']:
                if item['status'] == 'sending':
                    item['status'] = 'uncertain'
                    self._hold(item)
                    self.state.update(status='paused', notice='An email send was interrupted. Check outreach history; it will not be retried.')
            if self.state['status'] == 'paused' and any(i['status'] == 'uncertain' for i in self.state['items']):
                self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, indent=2), encoding='utf-8')
        temp.replace(self.path)

    def _hold(self, item):
        self.state['held_emails'] = sorted(set(self.state.get('held_emails', [])) | {item['email']})
        self.state['held_properties'] = sorted(set(self.state.get('held_properties', [])) | {item['property_key']})

    def _tracking(self, contacts):
        emails, properties = set(self.state.get('sent_emails', [])), set(self.state.get('sent_properties', []))
        for pid, contact in contacts.items():
            if str(contact.get('last_email_status') or '').startswith('SENT') or (contact.get('last_email_sent') and not contact.get('last_email_status')):
                if not pid.startswith('TEST-'):
                    emails.add(normalize_email(contact.get('email')))
                    properties.add(property_key(pid, contact))
        for entry in self.load_history():
            if (str(entry.get('channel') or '').upper() == 'EMAIL' and entry.get('status') == 'SENT'
                    and entry.get('direction', 'OUTBOUND') == 'OUTBOUND' and not entry.get('sandbox')):
                emails.add(normalize_email(entry.get('recipient') or entry.get('email')))
                pid = str(entry.get('parcel_id') or '')
                if pid in contacts:
                    properties.add(property_key(pid, contacts[pid]))
        return emails - {''}, properties

    def _reason(self, pid, contact, emails, properties):
        if not contact:
            return 'Contact no longer exists'
        if pid.startswith('TEST-') or contact.get('source') in ('Sandbox Demo Lead', 'Google Voice Live Test Line'):
            return 'Test lead'
        email = normalize_email(contact.get('email'))
        if not email:
            return 'Missing or malformed email'
        if email in self.state.get('held_emails', []) or property_key(pid, contact) in self.state.get('held_properties', []):
            return 'Previous email send needs review'
        if email in emails or property_key(pid, contact) in properties:
            return 'Already emailed'
        blocked, reason = self.is_blocked(email, contact)
        if blocked:
            return reason or 'Blocked email'
        address = contact.get('property_match', {}).get('record', {}).get('Property_Address') or contact.get('address')
        if not str(address or '').strip():
            return 'Missing property address'
        return ''

    def _prepare(self, parcel_ids):
        if self.load_error:
            raise ValueError(self.load_error)
        contacts, settings = self.load_contacts(), self.load_settings()
        templates = {t['id']: t for t in self.load_templates().get('email', [])}
        emails, properties = self._tracking(contacts)
        items, reasons, seen_emails, seen_properties = [], Counter(), set(), set()
        for pid in dict.fromkeys(str(p).strip() for p in parcel_ids):
            contact = contacts.get(pid)
            reason = self._reason(pid, contact, emails, properties)
            email, key = normalize_email((contact or {}).get('email')), property_key(pid, contact or {})
            if not reason and (email in seen_emails or key in seen_properties):
                reason = 'Duplicate email or property'
            if reason:
                reasons[reason] += 1
                continue
            payload = render_email(pid, contact, templates, settings)
            items.append({'parcel_id': pid, 'email': email, 'property_key': key, 'owner': payload['recipient_name'],
                          'template_type': payload['template_type'], 'status': 'pending'})
            seen_emails.add(email)
            seen_properties.add(key)
        return items, dict(reasons), templates, settings, emails, properties

    def preview(self, parcel_ids):
        with self.lock:
            items, reasons, _, _, _, _ = self._prepare(parcel_ids)
            return {'eligible': len(items), 'skipped': sum(reasons.values()), 'skipped_reasons': reasons,
                    'template_counts': dict(Counter(i['template_type'] for i in items)), 'interval_seconds': INTERVAL_SECONDS}

    def recheck_before_send(self, pid, email):
        with self.lock:
            contacts = self.load_contacts()
            emails, properties = self._tracking(contacts)
            contact = contacts.get(pid)
            reason = self._reason(pid, contact, emails, properties)
            if not reason and normalize_email(contact.get('email')) != normalize_email(email):
                return 'Email changed since queue started'
            return reason

    def start(self, parcel_ids):
        with self.lock:
            if self.state['status'] in ('running', 'paused') or any(i['status'] == 'sending' for i in self.state['items']):
                raise ValueError('An Auto Email queue already exists. Resume or stop it first.')
            items, reasons, templates, settings, emails, properties = self._prepare(parcel_ids)
            if not items:
                raise ValueError('No eligible emails in this filtered list. Missing, duplicate, previously emailed, blocked, and test contacts are skipped.')
            if (not settings.get('smtp_password') or not settings.get('smtp_user') or not settings.get('smtp_server')
                    or not normalize_email(settings.get('sender_email')) or not normalize_email(settings.get('reply_to'))):
                raise ValueError('Configure the SMTP credentials, sender, and reply-to address in Email Gateway Setup first.')
            self.state = {'id': str(uuid.uuid4()), 'status': 'running', 'items': items, 'templates': templates,
                          'next_send_at': max(self.clock(), self.state.get('next_send_at', 0)),
                          'sent_emails': sorted(emails), 'sent_properties': sorted(properties),
                          'held_emails': self.state.get('held_emails', []), 'held_properties': self.state.get('held_properties', []),
                          'skipped_reasons': reasons, 'notice': ''}
            self._save()
            return self.status()

    def status(self):
        with self.lock:
            counts = Counter(i['status'] for i in self.state['items'])
            pending = next((i for i in self.state['items'] if i['status'] == 'pending'), {})
            return {'status': self.state['status'], 'total': len(self.state['items']), 'sent': counts['sent'],
                    'remaining': counts['pending'], 'in_flight': bool(counts['sending']),
                    'failed': counts['failed'] + counts['uncertain'], 'next_owner': pending.get('owner', ''),
                    'skipped': sum(self.state.get('skipped_reasons', {}).values()),
                    'skipped_reasons': self.state.get('skipped_reasons', {}), 'notice': self.state.get('notice', ''),
                    'interval_seconds': INTERVAL_SECONDS,
                    'seconds_until_next': max(0, int(self.state.get('next_send_at', 0) - self.clock() + .999))}

    def control(self, action):
        with self.lock:
            if self.load_error:
                raise ValueError(self.load_error)
            transitions = {('running', 'pause'): 'paused', ('paused', 'resume'): 'running',
                           ('running', 'stop'): 'stopped', ('paused', 'stop'): 'stopped'}
            target = transitions.get((self.state['status'], action))
            if not target:
                raise ValueError('That action is not available for this email queue')
            self.state['status'] = target
            if action == 'resume':
                self.state['notice'] = ''
            self._save()
            return self.status()

    def tick(self):
        with self.lock:
            if self.state['status'] != 'running' or self.clock() < self.state.get('next_send_at', 0) or any(i['status'] == 'sending' for i in self.state['items']):
                return
            contacts = self.load_contacts()
            emails, properties = self._tracking(contacts)
            self.state.update(sent_emails=sorted(emails), sent_properties=sorted(properties))
            for item in self.state['items']:
                if item['status'] != 'pending':
                    continue
                contact = contacts.get(item['parcel_id'])
                reason = self._reason(item['parcel_id'], contact, emails, properties)
                if not reason and (normalize_email(contact.get('email')) != item['email'] or property_key(item['parcel_id'], contact) != item['property_key']):
                    reason = 'Contact changed since queue started'
                if reason:
                    item['status'] = 'skipped'
                    self.state['skipped_reasons'][reason] = self.state['skipped_reasons'].get(reason, 0) + 1
                    continue
                payload = render_email(item['parcel_id'], contact, self.state['templates'], self.load_settings())
                item['template_type'], item['status'] = payload['template_type'], 'sending'
                self.state['next_send_at'] = self.clock() + INTERVAL_SECONDS
                self._save()
                break
            else:
                self.state['status'] = 'complete'
                self._save()
                return
        try:
            result = self.send(payload)
        except Exception:
            result = {'status': 'error', 'message': 'Email outcome is unknown.'}
        with self.lock:
            self.state['next_send_at'] = self.clock() + INTERVAL_SECONDS
            if result.get('status') == 'success' and not result.get('sandbox'):
                item['status'] = 'sent'
                self.state['sent_emails'] = sorted(set(self.state.get('sent_emails', [])) | {item['email']})
                self.state['sent_properties'] = sorted(set(self.state.get('sent_properties', [])) | {item['property_key']})
            elif result.get('suppressed'):
                item['status'] = 'skipped'
                reason = result.get('blocked_reason') or 'Blocked email'
                self.state['skipped_reasons'][reason] = self.state['skipped_reasons'].get(reason, 0) + 1
            else:
                item['status'] = 'failed'
                self._hold(item)
                self.state['notice'] = 'Email failed or its outcome is unknown. Check outreach history and gateway settings. Resume continues with the next lead; this email will not be retried.'
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
                            self.state['notice'] = 'Auto Email paused after an error. Review the queue and gateway settings before resuming.'
                            try:
                                self._save()
                            except Exception:
                                pass
                    time.sleep(1)
            self.worker = threading.Thread(target=run, name='auto-email-outreach', daemon=True)
            self.worker.start()
