import json
from pathlib import Path
import tempfile
import threading
import unittest

from src.email_outreach_queue import EmailOutreachQueue, normalize_email, render_email, select_template


class EmailQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'queue.json'
        self.now = 1000
        self.contacts = {f'p{i}': {'owner': 'Jane Smith', 'email': f'person{i}@sample.org', 'address': f'{i} Main St',
                                 'city': 'Orlando', 'county': 'Orange', 'source': 'TruePeopleSearch', 'matched_parcel_id': str(i)}
                         for i in range(1, 9)}
        self.contacts['p1']['distress_category'] = 'Lis Pendens'
        self.contacts['p2']['property_match'] = {'record': {'Lead_Type': 'Probate Court Paper', 'Has_Confirmed_Probate': 'Yes'}}
        self.contacts['p3']['distress_category'] = 'Code Violation'
        self.contacts['p8']['distress_category'] = 'Probate (Death Certificate)'
        self.templates = {'email': [{'id': tid, 'subject': 'Question about {Address}',
            'body': 'Hi {FirstName},\n\n' + tid + ' {Address}, {City}, {County}. Call {Phone}. john@407flips.com'}
            for tid in ('lis_pendens', 'probate', 'code_violation', 'quick_cash')]}
        self.settings = {'smtp_password': 'fake-only', 'smtp_user': 'fake', 'smtp_server': 'localhost',
                         'sender_email': 'sender@sample.org', 'reply_to': 'reply@sample.org', 'company_phone': '(407) 200-0000',
                         'company_name': '407 Flips', 'business_address': 'Orlando, FL'}
        self.history, self.sent = [], []
        self.sender = self.send
        self.queue = self.create()

    def create(self):
        return EmailOutreachQueue(self.path, lambda: self.contacts, lambda: self.history, lambda: self.templates,
            lambda: self.settings, lambda email, contact: (bool(contact.get('blocked')), 'Opted out'),
            lambda payload: self.sender(payload), clock=lambda: self.now)

    def send(self, payload):
        self.sent.append(payload)
        return {'status': 'success'}

    def test_order_interval_personalization_and_template_rules(self):
        ids = ['p1', 'p2', 'p3', 'p4', 'p8']
        self.queue.start(ids)
        self.assertEqual(self.sent, [])
        self.queue.tick()
        self.now += 89
        self.queue.tick()
        self.assertEqual(len(self.sent), 1)
        self.now += 1
        for _ in range(4):
            self.queue.tick()
            self.now += 90
        self.assertEqual([p['parcel_id'] for p in self.sent], ids)
        self.assertEqual([p['template_type'] for p in self.sent], ['lis_pendens', 'probate', 'code_violation', 'quick_cash', 'quick_cash'])
        self.assertIn('Hi Jane,', self.sent[0]['plain_content'])
        self.assertIn('1 Main St, Orlando, Orange', self.sent[0]['plain_content'])
        self.assertIn('(407) 200-0000', self.sent[0]['plain_content'])
        self.assertIn('reply@sample.org', self.sent[0]['plain_content'])
        self.assertIn('reply REMOVE', self.sent[0]['plain_content'])
        self.assertEqual(self.queue.status()['status'], 'complete')

    def test_preview_is_read_only_and_skips_bad_duplicate_and_previously_emailed_aliases(self):
        self.contacts['p2']['email'] = ' '+self.contacts['p1']['email'].upper()+' '
        self.contacts['p3']['email'] = 'bad@@sample.org'
        self.contacts['p4']['last_email_sent'] = '2026-10-14 12:00:00'
        self.contacts['p4']['last_email_status'] = 'SENT'
        self.contacts['p5']['blocked'] = True
        self.contacts['p6']['matched_parcel_id'] = '4'
        self.contacts['p7']['address'] = ''
        self.contacts['TEST-1'] = dict(self.contacts['p8'])
        result = self.queue.preview(list(self.contacts))
        self.assertEqual(result['eligible'], 2)
        self.assertEqual(result['skipped_reasons']['Already emailed'], 2)
        self.assertEqual(result['skipped_reasons']['Duplicate email or property'], 1)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.sent, [])

    def test_same_property_with_different_emails_is_queued_once(self):
        self.contacts['p2']['matched_parcel_id'] = '1'
        self.assertEqual(self.queue.preview(['p1', 'p2'])['eligible'], 1)
        self.queue.start(['p1', 'p2'])
        self.queue.tick()
        self.assertEqual(len(self.sent), 1)
        self.contacts['p1']['email'] = 'new@sample.org'
        self.assertEqual(self.queue.preview(['p1', 'p2'])['eligible'], 0)

    def test_rechecks_opt_out_manual_send_and_email_change_before_dispatch(self):
        self.queue.start(['p1', 'p2', 'p3', 'p4'])
        self.contacts['p1']['blocked'] = True
        self.contacts['p2']['email'] = 'changed@sample.org'
        self.history.append({'channel': 'EMAIL', 'status': 'SENT', 'recipient': self.contacts['p3']['email']})
        self.queue.tick()
        self.assertEqual([p['parcel_id'] for p in self.sent], ['p4'])
        self.assertEqual(self.queue.status()['skipped'], 3)

    def test_pause_resume_stop_and_new_start_rejection(self):
        self.queue.start(['p1', 'p2'])
        with self.assertRaises(ValueError): self.queue.start(['p3'])
        self.queue.control('pause')
        self.queue.tick()
        self.assertEqual(self.sent, [])
        self.queue.control('resume')
        self.queue.tick()
        self.queue.control('stop')
        self.now += 90
        self.queue.tick()
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.queue.status()['status'], 'stopped')

    def test_restart_keeps_spacing_and_dedup_after_history_pruning(self):
        self.queue.start(['p1', 'p2'])
        self.queue.tick()
        restarted = self.create()
        restarted.tick()
        self.assertEqual(len(self.sent), 1)
        self.now += 90
        restarted.tick()
        self.assertEqual([p['parcel_id'] for p in self.sent], ['p1', 'p2'])
        self.assertEqual(self.create().preview(['p1', 'p2'])['eligible'], 0)

    def test_interrupted_send_is_held_and_not_retried_on_another_batch(self):
        self.sender = lambda payload: (_ for _ in ()).throw(SystemExit('simulated crash'))
        self.queue.start(['p1', 'p2'])
        with self.assertRaises(SystemExit): self.queue.tick()
        restarted = self.create()
        self.assertEqual(restarted.status()['status'], 'paused')
        self.assertEqual(restarted.status()['failed'], 1)
        restarted.control('stop')
        self.sender = self.send
        restarted.start(['p1', 'p2'])
        self.now += 90
        restarted.tick()
        self.assertEqual([p['parcel_id'] for p in self.sent], ['p2'])

    def test_gateway_error_pauses_and_resume_continues_with_next_contact(self):
        self.sender = lambda _: {'status': 'error'}
        self.queue.start(['p1', 'p2'])
        self.queue.tick()
        self.assertEqual(self.queue.status()['status'], 'paused')
        self.sender = self.send
        self.now += 90
        self.queue.control('resume')
        self.queue.tick()
        self.assertEqual([p['parcel_id'] for p in self.sent], ['p2'])

    def test_pause_during_send_and_overlapping_tick_dispatch_only_once(self):
        entered, release = threading.Event(), threading.Event()
        def slow(payload):
            entered.set()
            self.assertTrue(release.wait(3))
            return self.send(payload)
        self.sender = slow
        self.queue.start(['p1', 'p2'])
        thread = threading.Thread(target=self.queue.tick)
        thread.start()
        self.assertTrue(entered.wait(3))
        self.queue.tick()
        self.queue.control('pause')
        release.set()
        thread.join(3)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.queue.status()['status'], 'paused')

    def test_corrupt_or_malformed_queue_disables_only_email_and_is_not_overwritten(self):
        for value in ('{invalid', '{"status":"running","items":[{}]}'):
            self.path.write_text(value, encoding='utf-8')
            queue = self.create()
            self.assertEqual(queue.status()['status'], 'error')
            with self.assertRaises(ValueError): queue.start(['p1'])
            self.assertEqual(self.path.read_text(encoding='utf-8'), value)

    def test_setup_and_template_errors_do_not_create_live_queue(self):
        self.settings['smtp_password'] = ''
        with self.assertRaises(ValueError): self.queue.start(['p1'])
        self.assertFalse(self.path.exists())
        self.templates['email'] = []
        with self.assertRaises(ValueError): self.queue.preview(['p1'])
        self.assertFalse(self.path.exists())

    def test_html_is_escaped_and_subject_header_injection_is_rejected(self):
        self.contacts['p1']['address'] = '1 Main <script>alert(1)</script>'
        payload = render_email('p1', self.contacts['p1'], {t['id']: t for t in self.templates['email']}, self.settings)
        self.assertNotIn('<script>', payload['html_content'])
        self.assertIn('&lt;script&gt;', payload['html_content'])
        self.templates['email'][0]['subject'] = 'Hello\r\nBcc: other@sample.org'
        with self.assertRaises(ValueError): self.queue.start(['p1'])
        self.assertFalse(self.path.exists())

    def test_email_validation_and_explicit_probate_selection(self):
        self.assertEqual(normalize_email(' Jane.Smith@Sample.org '), 'jane.smith@sample.org')
        for value in ('bad@@sample.org', 'a..b@sample.org', 'one@-sample.org', 'two@sample', 'a b@sample.org'):
            self.assertEqual(normalize_email(value), '')
        self.assertEqual(select_template({'distress_category': 'Lis Pendens', 'Is_Trust_Or_Estate': 'Yes'}), 'lis_pendens')
        self.assertEqual(select_template({'distress_category': 'Probate (Death Certificate)'}), 'quick_cash')


if __name__ == '__main__': unittest.main()
