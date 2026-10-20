import json
from pathlib import Path
import tempfile
import threading
import unittest

from src.sms_outreach_queue import SmsOutreachQueue, TEMPLATE_IDS, FOLLOW_UP_TEMPLATES, fill_template


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'queue.json'
        self.now = 1000.0
        self.contacts = {f'p{i}': {'owner': f'Seller {i}', 'phone': f'407200{i:04}', 'county': 'Orange' if i % 2 else 'Pinellas',
                                 'address': f'{i} Sample St', 'state': 'FL', 'source': 'Skip Trace CSV (sample.csv)'} for i in range(1, 8)}
        self.history, self.blocked, self.sent = [], set(), []
        self.sender = lambda payload: self.send(payload)
        self.queue = self.create()

    def send(self, payload):
        self.sent.append(payload)
        return {'status': 'success'}

    def create(self):
        return SmsOutreachQueue(self.path, lambda: self.contacts, lambda: self.history,
                                lambda: {'sms': [{'id': tid, 'body': f'Angle {i}: Hi {{FirstName}}, {{Address}} in {{County}}'} for i, tid in enumerate(TEMPLATE_IDS, 1)]},
                                lambda phone, contact: (phone in self.blocked, 'Opted out'),
                                lambda payload: self.sender(payload), clock=lambda: self.now)

    def test_order_counties_rotation_interval_and_completion(self):
        order = ['p3', 'p2', 'p5', 'p1', 'p4']
        self.queue.start(order)
        self.queue.tick()
        self.assertEqual(len(self.sent), 1)
        self.now += 89.9
        self.queue.tick()
        self.assertEqual(len(self.sent), 1)
        self.now += .1
        self.queue.tick()
        for _ in range(3):
            self.now += 90
            self.queue.tick()
        self.assertEqual([s['parcel_id'] for s in self.sent], order)
        self.assertEqual([s['opener_angle'] for s in self.sent], list(TEMPLATE_IDS) + [TEMPLATE_IDS[0]])
        self.assertEqual([s['county'] for s in self.sent], ['Orange', 'Pinellas', 'Orange', 'Orange', 'Pinellas'])
        self.assertIn('2 Sample St in Pinellas', self.sent[1]['message'])
        self.assertEqual(self.queue.status()['status'], 'complete')

    def test_skips_contacted_missing_duplicates_blocked_and_non_imported(self):
        self.contacts['p2']['phone'] = self.contacts['p1']['phone']
        self.contacts['p3']['phone'] = ''
        self.contacts['p4']['last_sms_status'] = 'SENT'
        self.contacts['p5']['source'] = 'TruePeopleSearch'
        self.blocked.add(self.contacts['p6']['phone'])
        self.history = [{'channel': 'SMS', 'status': 'SENT', 'direction': 'OUTBOUND', 'phone': '+1' + self.contacts['p7']['phone']}]
        preview = self.queue.preview(list(self.contacts))
        self.assertEqual(preview['eligible'], 1)
        self.assertEqual(preview['skipped'], 6)
        self.assertFalse(self.path.exists(), 'Preview must not create a live queue')
        self.assertEqual(self.sent, [])

    def test_county_reset_preserves_history_survives_restart_and_allows_only_one_resend(self):
        self.contacts['p1']['last_sms_status'] = 'SENT'
        self.contacts['p2']['last_sms_status'] = 'SENT'
        self.history = [{'channel': 'SMS', 'status': 'SENT', 'direction': 'OUTBOUND', 'phone': self.contacts['p2']['phone'], 'message': 'Old opener'}]
        original = list(self.history)
        self.queue.state['sent_phones'] = [self.contacts['p2']['phone']]
        result = self.queue.reset_initial(['p1', 'p2'], 'Pinellas')
        self.assertEqual(result['parcel_ids'], ['p2'])
        self.assertEqual(result['skipped_reasons'], {'Different county': 1})
        self.assertEqual(self.history, original)
        self.assertEqual(self.sent, [])
        restarted = self.create()
        self.assertEqual(restarted.preview(['p1', 'p2'])['eligible'], 1)
        restarted.start(['p1', 'p2'])
        restarted.tick()
        self.assertEqual([s['parcel_id'] for s in self.sent], ['p2'])
        self.assertEqual(restarted.pending_initial_resends(), {})
        self.assertEqual(self.create().preview(['p1', 'p2'])['eligible'], 0)
        self.assertEqual(self.history, original)

    def test_reset_cannot_override_reply_suppression_held_phone_or_phone_change(self):
        for contact in self.contacts.values():
            contact['last_sms_status'] = 'SENT'
        self.blocked.add(self.contacts['p2']['phone'])
        self.queue.state['held_phones'] = [self.contacts['p4']['phone']]
        self.history = [{'channel': 'SMS', 'direction': 'INBOUND', 'phone': self.contacts['p6']['phone']}]
        result = self.queue.reset_initial(['p2', 'p4', 'p6'], 'Pinellas')
        self.assertEqual(result['reset'], 0)
        self.assertEqual(result['skipped_reasons'], {'Opted out': 1, 'Previous send needs review': 1, 'Already replied': 1})
        self.blocked.clear()
        self.queue.reset_initial(['p2'], 'Pinellas')
        self.contacts['p2']['phone'] = self.contacts['p1']['phone']
        self.assertEqual(self.queue.preview(['p2'])['eligible'], 0)

    def test_reset_checks_late_replies_and_manual_send_consumes_approval(self):
        self.contacts['p2']['last_sms_status'] = 'SENT'
        self.queue.reset_initial(['p2'], 'Pinellas')
        self.history = [{'channel': 'SMS', 'direction': 'INBOUND', 'phone': self.contacts['p2']['phone']}]
        self.assertEqual(self.queue.preview(['p2'])['skipped_reasons'], {'Already replied': 1})
        self.history.clear()
        self.queue.record_sent(self.contacts['p2']['phone'])
        self.assertEqual(self.queue.preview(['p2'])['eligible'], 0)

    def test_reset_rejected_while_batch_is_active_and_failed_resend_is_not_retried(self):
        self.queue.start(['p1'])
        with self.assertRaises(ValueError):
            self.queue.reset_initial(['p2'], 'Pinellas')
        self.queue.control('stop')
        self.contacts['p2']['last_sms_status'] = 'SENT'
        self.queue.reset_initial(['p2'], 'Pinellas')
        self.sender = lambda _: {'status': 'error'}
        self.queue.start(['p2'])
        self.queue.tick()
        self.assertEqual(self.queue.pending_initial_resends(), {})
        self.assertEqual(self.queue.preview(['p2'])['eligible'], 0)

    def test_rechecks_contact_and_opt_out_before_dispatch_without_advancing_angle(self):
        self.queue.start(['p1', 'p2', 'p3'])
        self.blocked.add(self.contacts['p1']['phone'])
        self.contacts['p2']['phone'] = '4072009999'
        self.queue.tick()
        self.assertEqual(self.sent[0]['parcel_id'], 'p3')
        self.assertEqual(self.sent[0]['opener_angle'], TEMPLATE_IDS[0])
        self.assertEqual(self.queue.status()['skipped'], 2)

    def test_pause_resume_stop_and_second_start_rejection(self):
        self.queue.start(['p1', 'p2'])
        with self.assertRaises(ValueError):
            self.queue.start(['p3'])
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

    def test_restart_between_sends_preserves_interval_and_does_not_resend(self):
        self.queue.start(['p1', 'p2'])
        self.queue.tick()
        restarted = self.create()
        restarted.tick()
        self.assertEqual(len(self.sent), 1)
        self.now += 90
        restarted.tick()
        self.assertEqual([s['parcel_id'] for s in self.sent], ['p1', 'p2'])

    def test_interrupted_send_is_held_for_review_not_retried_on_a_new_run(self):
        self.sender = lambda payload: (_ for _ in ()).throw(SystemExit('simulated process exit'))
        self.queue.start(['p1', 'p2'])
        with self.assertRaises(SystemExit):
            self.queue.tick()
        restarted = self.create()
        self.assertEqual(restarted.status()['status'], 'paused')
        self.assertEqual(restarted.status()['failed'], 1)
        restarted.control('stop')
        self.sender = self.send
        restarted.start(['p1', 'p2'])
        restarted.tick()
        self.assertEqual([s['parcel_id'] for s in self.sent], ['p2'])

    def test_gateway_failure_pauses_without_auto_retry(self):
        self.sender = lambda payload: {'status': 'error'}
        self.queue.start(['p1', 'p2'])
        self.queue.tick()
        self.assertEqual(self.queue.status()['status'], 'paused')
        self.sender = self.send
        self.now += 90
        self.queue.tick()
        self.assertEqual(self.sent, [])
        self.queue.control('resume')
        self.queue.tick()
        self.assertEqual(self.sent[0]['parcel_id'], 'p2')

    def test_pause_during_send_allows_only_the_in_flight_send_to_finish(self):
        entered, release = threading.Event(), threading.Event()
        def slow_send(payload):
            entered.set()
            self.assertTrue(release.wait(3))
            return self.send(payload)
        self.sender = slow_send
        self.queue.start(['p1', 'p2'])
        worker = threading.Thread(target=self.queue.tick)
        worker.start()
        self.assertTrue(entered.wait(3))
        self.queue.control('pause')
        release.set()
        worker.join(3)
        self.now += 90
        self.queue.tick()
        self.assertEqual(self.queue.status()['status'], 'paused')
        self.assertEqual(len(self.sent), 1)

    def test_corrupt_queue_disables_outreach_without_stopping_the_app(self):
        self.path.write_text('{invalid', encoding='utf-8')
        queue = self.create()
        self.assertEqual(queue.status()['status'], 'error')
        queue.tick()
        with self.assertRaises(ValueError):
            queue.start(['p1'])
        self.assertEqual(self.sent, [])
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{invalid')

    def test_name_personalization(self):
        self.assertEqual(fill_template('Hi {FirstName}, {County}', {'owner': 'GARCIA JOSE'}, 'Orange'), 'Hi Jose, Orange')
        self.assertEqual(fill_template('Hi {FirstName}', {'owner': 'Example LLC'}, 'Orange'), 'Hi there')

    def mark_initial_sent(self, *ids):
        for pid in ids:
            self.contacts[pid]['last_sms_status'] = 'SENT'

    def test_follow_up_filters_replies_unsent_missing_address_duplicates_and_opt_outs(self):
        self.mark_initial_sent('p1', 'p2', 'p3', 'p4', 'p5', 'p6')
        self.contacts['p2']['phone'] = '+1' + self.contacts['p1']['phone']
        self.contacts['p4']['address'] = ''
        self.blocked.add(self.contacts['p5']['phone'])
        self.history = [{'channel': 'SMS', 'direction': 'INBOUND', 'sender_phone': '+1' + self.contacts['p3']['phone']}]
        preview = self.queue.preview(list(self.contacts), 'follow_up')
        self.assertEqual(preview['eligible'], 2)
        self.assertEqual(preview['skipped_reasons'], {'Duplicate phone': 1, 'Already replied': 1,
            'Missing property address': 1, 'Opted out': 1, 'No previous SMS': 1})
        self.assertFalse(self.path.exists())
        self.assertEqual(self.sent, [])

    def test_follow_up_cycles_ten_messages_in_order_and_uses_each_street_address(self):
        for i in range(8, 12):
            self.contacts[f'p{i}'] = dict(self.contacts['p1'], phone=f'407200{i:04}', address=f'{i} Sample St, Orlando, FL')
        self.mark_initial_sent(*self.contacts)
        self.queue.start(list(self.contacts), 'follow_up')
        for _ in self.contacts:
            self.queue.tick()
            self.now += 90
        self.assertEqual([p['opener_angle'] for p in self.sent],
                         [t['id'] for t in FOLLOW_UP_TEMPLATES] + [FOLLOW_UP_TEMPLATES[0]['id']])
        self.assertEqual(len(set(p['message'] for p in self.sent[:10])), 10)
        self.assertEqual(self.sent[0]['message'], "Hello, I'm trying to locate the property owner of 1 Sample St. Would that be you?")
        self.assertIn('8 Sample St', self.sent[7]['message'])
        self.assertNotIn('Orlando', self.sent[7]['message'])
        self.assertEqual(self.queue.status()['campaign'], 'follow_up')
        self.assertEqual(self.queue.status()['status'], 'complete')

    def test_follow_up_rechecks_replies_before_dispatch_and_keeps_manual_mode_across_restart(self):
        self.mark_initial_sent('p1', 'p2', 'p3')
        self.queue.start(['p1', 'p2', 'p3'], 'follow_up')
        self.queue.record_reply('+1' + self.contacts['p1']['phone'])
        self.history = [{'channel': 'SMS', 'direction': 'INBOUND', 'phone': self.contacts['p2']['phone']}]
        self.queue.tick()
        self.assertEqual([p['parcel_id'] for p in self.sent], ['p3'])
        self.assertEqual(self.queue.status()['skipped_reasons']['Already replied'], 2)
        self.assertTrue(self.queue.requires_manual_reply(self.contacts['p3']['phone']))
        self.assertFalse(self.queue.requires_manual_reply(self.contacts['p1']['phone']))
        self.history.clear()  # Simulate inbox history pruning.
        restarted = self.create()
        self.assertTrue(restarted.requires_manual_reply('+1' + self.contacts['p3']['phone']))
        self.assertTrue(restarted.has_replied(self.contacts['p1']['phone']))
        self.assertTrue(restarted.has_replied(self.contacts['p2']['phone']))
        self.assertEqual(restarted.preview(['p1', 'p2', 'p3'], 'follow_up')['eligible'], 0)
        restarted.start(['p4'])
        restarted.tick()
        restarted = self.create()
        self.assertEqual(restarted.preview(['p3'], 'follow_up')['eligible'], 0)
        self.assertTrue(restarted.requires_manual_reply(self.contacts['p3']['phone']))

    def test_follow_up_handles_legacy_history_and_previous_follow_up(self):
        self.history = [{'channel': 'SMS', 'status': 'SENT', 'recipient': '+1' + self.contacts['p1']['phone']},
                        {'channel': 'SMS', 'status': 'SENT', 'recipient': self.contacts['p2']['phone'], 'opener_angle': 'follow_up_4'}]
        self.assertEqual(self.queue.preview(['p1', 'p2'], 'follow_up')['skipped_reasons'], {'Already followed up': 1})
        self.queue.start(['p1', 'p2'], 'follow_up')
        self.queue.tick()
        self.assertEqual([p['parcel_id'] for p in self.sent], ['p1'])
        with self.assertRaises(ValueError):
            self.queue.start(['p1', 'p2'], 'follow_up')

    def test_follow_up_manual_reply_marker_is_saved_before_gateway_call(self):
        self.mark_initial_sent('p1')
        def immediate_reply(payload):
            self.assertTrue(self.queue.requires_manual_reply(payload['phone']))
            persisted = json.loads(self.path.read_text(encoding='utf-8'))
            self.assertIn(payload['phone'], persisted['manual_reply_phones'])
            self.queue.record_reply(payload['phone'])
            return self.send(payload)
        self.sender = immediate_reply
        self.queue.start(['p1'], 'follow_up')
        self.queue.tick()
        self.assertTrue(self.create().has_replied(self.contacts['p1']['phone']))

    def test_interrupted_follow_up_is_not_retried(self):
        self.mark_initial_sent('p1', 'p2')
        self.sender = lambda payload: (_ for _ in ()).throw(SystemExit('simulated process exit'))
        self.queue.start(['p1', 'p2'], 'follow_up')
        with self.assertRaises(SystemExit):
            self.queue.tick()
        restarted = self.create()
        self.assertEqual(restarted.status()['status'], 'paused')
        restarted.control('stop')
        self.sender = self.send
        restarted.start(['p1', 'p2'], 'follow_up')
        restarted.tick()
        self.assertEqual([p['parcel_id'] for p in self.sent], ['p2'])

    def test_invalid_campaign_cannot_create_a_queue(self):
        with self.assertRaises(ValueError):
            self.queue.start(['p1'], 'anything')
        self.assertFalse(self.path.exists())

    def test_startup_retains_existing_replies_before_history_is_pruned(self):
        self.history = [{'channel': 'SMS', 'direction': 'INBOUND', 'phone': '+1' + self.contacts['p1']['phone']}]
        self.queue = self.create()
        self.history.clear()
        self.assertTrue(self.create().has_replied(self.contacts['p1']['phone']))


if __name__ == '__main__':
    unittest.main()
