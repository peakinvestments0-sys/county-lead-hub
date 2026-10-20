"""Exercise real queue routes and MIME/SMTP sender with an isolated fake SMTP server."""
import ast
from email import message_from_string
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from typing import List, Optional
import unittest
from unittest.mock import Mock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from src.email_outreach_queue import EmailOutreachQueue


class AutoEmailApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.contacts = {'p1': {'owner': 'Alice Smith', 'email': 'alice@sample.org', 'address': '1 Main St', 'county': 'Orange', 'distress_category': 'Lis Pendens'},
                         'p2': {'owner': 'Brian Jones', 'email': 'brian@sample.org', 'address': '2 Main St', 'county': 'Lake'}}
        self.history = []
        self.smtp = Mock()
        self.smtp.sendmail.return_value = {}
        self.gateway = Mock(return_value=self.smtp)
        settings = {'smtp_server': 'fake.smtp.local', 'smtp_port': 2525, 'smtp_user': 'test-user', 'smtp_password': 'fake-not-a-secret',
                    'sender_email': 'john@sample.org', 'reply_to': 'reply@sample.org', 'sender_name': 'John | 407 Flips'}
        templates = {'email': [{'id': tid, 'subject': 'Question about {Address}', 'body': 'Hi {FirstName},\n\nAre you the owner of {Address}?'}
                               for tid in ('lis_pendens', 'probate', 'code_violation', 'quick_cash')]}
        def save(pid, data):
            self.contacts[pid].update(data)
        app = FastAPI()
        ns = {'app': app, 'BaseModel': BaseModel, 'Optional': Optional, 'List': List, 'HTTPException': HTTPException,
              'DATA_DIR': self.temp.name, 'OUTREACH_LOG_FILE': str(Path(self.temp.name) / 'unused.json'),
              'load_saved_contacts': lambda: self.contacts, 'load_email_settings': lambda: settings,
              'is_lead_blocked_from_outreach': lambda *_: (False, ''),
              'smtplib': SimpleNamespace(SMTP=self.gateway), 'time': time, 'os': os, 'json': json,
              'append_outreach_log': lambda entry: self.history.insert(0, entry), 'save_contact': save,
              'MIMEMultipart': __import__('email.mime.multipart', fromlist=['MIMEMultipart']).MIMEMultipart,
              'MIMEText': __import__('email.mime.text', fromlist=['MIMEText']).MIMEText}
        names = {'AutoEmailStartRequest', 'AutoEmailControlRequest', 'get_auto_email_status', 'preview_auto_email',
                 'start_auto_email', 'control_auto_email', 'SendEmailRequest', 'send_email_via_smtp', 'is_email_blocked_from_outreach'}
        tree = ast.parse(Path('server.py').read_text(encoding='utf-8'))
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
        self.assertEqual(len(definitions), len(names))
        exec(compile(ast.Module(body=definitions, type_ignores=[]), 'server.py', 'exec'), ns)
        self.queue = EmailOutreachQueue(Path(self.temp.name) / 'queue.json', lambda: self.contacts, lambda: self.history,
            lambda: templates, lambda: settings, ns['is_email_blocked_from_outreach'],
            lambda payload: ns['send_email_via_smtp'](ns['SendEmailRequest'](**payload)), clock=lambda: self.now)
        ns['auto_email_queue'] = self.queue
        self.client, self.ns = TestClient(app), ns
        self.addCleanup(self.client.close)

    def test_preview_start_pause_resume_stop_and_real_mime_without_live_smtp(self):
        ids = {'parcel_ids': ['p1', 'p2']}
        self.assertEqual(self.client.get('/api/email/auto/status').json()['queue']['status'], 'idle')
        preview = self.client.post('/api/email/auto/preview', json=ids).json()
        self.assertEqual(preview['eligible'], 2)
        self.assertEqual(preview['template_counts'], {'lis_pendens': 1, 'quick_cash': 1})
        self.assertFalse(self.queue.path.exists())
        self.gateway.assert_not_called()
        self.assertEqual(self.client.post('/api/email/auto/start', json=ids).status_code, 200)
        self.gateway.assert_not_called()
        self.assertEqual(self.client.post('/api/email/auto/start', json=ids).status_code, 400)
        self.client.post('/api/email/auto/control', json={'action': 'pause'})
        self.queue.tick()
        self.gateway.assert_not_called()
        self.client.post('/api/email/auto/control', json={'action': 'resume'})
        self.queue.tick()
        self.smtp.sendmail.assert_called_once()
        mime = message_from_string(self.smtp.sendmail.call_args.args[2])
        self.assertEqual(mime['To'], 'alice@sample.org')
        self.assertEqual(mime['Reply-To'], 'reply@sample.org')
        self.assertEqual(mime['Subject'], 'Question about 1 Main St')
        self.assertEqual([p.get_content_type() for p in mime.get_payload()], ['text/plain', 'text/html'])
        plain = mime.get_payload()[0].get_payload(decode=True).decode('utf-8')
        self.assertIn('Hi Alice,', plain)
        self.assertIn('reply REMOVE', plain)
        self.assertEqual(self.contacts['p1']['last_email_template'], 'lis_pendens')
        self.assertEqual(self.history[0]['direction'], 'OUTBOUND')
        self.assertEqual(self.history[0]['message'], plain)
        self.assertEqual(self.client.post('/api/email/auto/control', json={'action': 'stop'}).json()['queue']['status'], 'stopped')
        self.now += 90
        self.queue.tick()
        self.smtp.sendmail.assert_called_once()

    def test_opt_out_after_start_is_rechecked_and_never_touches_smtp(self):
        self.queue.start(['p1'])
        self.contacts['p1']['email_opt_out'] = True
        self.queue.tick()
        self.gateway.assert_not_called()
        self.assertEqual(self.queue.status()['skipped'], 1)
        self.assertEqual(self.queue.status()['status'], 'complete')

    def test_final_gateway_rechecks_manual_send_that_happened_after_queue_check(self):
        self.queue.start(['p1'])
        self.contacts['p1']['last_email_sent'] = '2026-10-14 12:00:00'
        self.contacts['p1']['last_email_status'] = 'SENT'
        payload = {'recipient_email': 'alice@sample.org', 'subject': 'Hello', 'html_content': '<p>Hi</p>', 'parcel_id': 'p1', 'auto_outreach': True}
        result = self.client.post('/api/email/send', json=payload).json()
        self.assertTrue(result['suppressed'])
        self.assertEqual(result['blocked_reason'], 'Already emailed')
        self.gateway.assert_not_called()

    def test_smtp_failure_pauses_without_duplicate_retry(self):
        self.smtp.sendmail.side_effect = RuntimeError('fake gateway unavailable')
        self.queue.start(['p1', 'p2'])
        self.queue.tick()
        self.assertEqual(self.queue.status()['status'], 'paused')
        self.assertEqual(self.history, [])
        self.smtp.sendmail.side_effect = None
        self.now += 90
        self.queue.control('resume')
        self.queue.tick()
        self.assertEqual(self.smtp.sendmail.call_args.args[1], ['brian@sample.org'])
        self.assertNotIn('last_email_sent', self.contacts['p1'])

    def test_linked_contact_opt_out_and_email_suppression_are_honored(self):
        self.contacts['p1']['matched_parcel_id'] = '123'
        self.contacts['alias'] = dict(self.contacts['p1'], email='other@sample.org', email_bounced=True)
        self.assertEqual(self.queue.preview(['p1'])['eligible'], 0)
        del self.contacts['alias']
        Path(self.temp.name, 'email_suppression.json').write_text('[{"email":"ALICE@sample.org"}]', encoding='utf-8')
        self.assertEqual(self.queue.preview(['p1'])['eligible'], 0)
        self.gateway.assert_not_called()


if __name__ == '__main__': unittest.main()
