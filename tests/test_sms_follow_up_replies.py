"""Exercise actual webhook/gateway code without app startup or live SMS."""
import ast
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fastapi import FastAPI


SOURCE = ast.parse((Path(__file__).resolve().parents[1] / 'server.py').read_text(encoding='utf-8'))


def load_function(name, namespace):
    definitions = [n for n in SOURCE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(definitions) == 1
    exec(compile(ast.Module(body=definitions, type_ignores=[]), 'server.py', 'exec'), namespace)
    return namespace[name]


class FollowUpReplyTests(unittest.TestCase):
    def webhook(self, manual):
        queue = Mock()
        queue.requires_manual_reply.return_value = manual
        send, thread = Mock(), Mock()
        lead = {'parcel_id': 'p1', 'owner_name': 'Owner', 'property_address': '1 Main St'}
        bot_result = {'action': 'SUGGEST_REPLY', 'auto_send_allowed': True, 'suggested_reply': 'Bot reply'}
        async def body():
            return {'event': 'sms:received', 'payload': {'phoneNumber': '+14072000001', 'message': 'Yes, I own it'}}
        namespace = {
            'app': FastAPI(), 'Request': object, 'auto_sms_queue': queue,
            'find_lead_by_phone': Mock(return_value=lead), 'get_lead_sms_thread': Mock(return_value=[]),
            'seller_bot': SimpleNamespace(process_inbound_sms=Mock(return_value=bot_result)),
            'os': SimpleNamespace(path=SimpleNamespace(exists=lambda _: False)), 'OUTREACH_LOG_FILE': 'unused',
            'time': SimpleNamespace(strftime=lambda _: '2026-10-14 10:00:00', sleep=Mock()),
            'append_outreach_log': Mock(), 'load_seller_bot_settings': lambda: {'enabled': True, 'mode': 'autopilot'},
            'random': SimpleNamespace(randint=lambda *_: 30), 'threading': SimpleNamespace(Thread=thread),
            'send_sms_via_gateway': send, 'SendSmsRequest': lambda **kwargs: kwargs,
        }
        function = load_function('receive_inbound_sms', namespace)
        result = asyncio.run(function(SimpleNamespace(json=body)))
        return result, queue, send, thread, namespace

    def test_follow_up_reply_is_logged_and_never_schedules_an_autopilot_reply(self):
        result, queue, send, thread, namespace = self.webhook(manual=True)
        queue.record_reply.assert_called_once_with('+14072000001')
        namespace['append_outreach_log'].assert_called_once()
        entry = namespace['append_outreach_log'].call_args.args[0]
        self.assertEqual(entry['direction'], 'INBOUND')
        self.assertEqual(entry['message'], 'Yes, I own it')
        self.assertFalse(result['auto_dispatched'])
        thread.assert_not_called()
        send.assert_not_called()

    def test_other_contacts_retain_autopilot_and_delayed_dispatch_rechecks_manual_mode(self):
        result, queue, send, thread, _ = self.webhook(manual=False)
        self.assertTrue(result['auto_dispatched'])
        dispatch = thread.call_args.kwargs['target']
        queue.requires_manual_reply.return_value = True
        dispatch()
        send.assert_not_called()
        queue.requires_manual_reply.return_value = False
        dispatch()
        send.assert_called_once()

    def test_gateway_skips_follow_up_if_reply_arrives_after_queue_check(self):
        queue = Mock()
        queue.has_replied.return_value = True
        block = Mock(side_effect=AssertionError('Must stop before gateway setup'))
        namespace = {'app': FastAPI(), 'SendSmsRequest': object, 'auto_sms_queue': queue,
                     'is_lead_blocked_from_outreach': block}
        send = load_function('send_sms_via_gateway', namespace)
        result = send(SimpleNamespace(opener_angle='follow_up_1', phone='4072000001'))
        self.assertTrue(result['suppressed'])
        self.assertEqual(result['blocked_reason'], 'Already replied')
        block.assert_not_called()


if __name__ == '__main__':
    unittest.main()
