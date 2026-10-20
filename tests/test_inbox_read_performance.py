"""Exercise inbox reads without starting the app, webhooks, or outbound SMS."""
import ast
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import Mock, patch

from src import valuation_service as valuation


class InboxReadTests(unittest.TestCase):
    def test_inbox_valuation_fallback_does_not_use_network_or_write_cache(self):
        with patch.object(valuation, 'fetch_online_zestimate', side_effect=AssertionError('No network')) as online, \
             patch.object(valuation, 'save_valuations_cache') as save:
            result = valuation.get_property_market_valuation('123 Sample Street', 200000, allow_online_lookup=False, cache={})
        self.assertEqual(result['market_value'], 260000)
        online.assert_not_called()
        save.assert_not_called()

    def test_regular_valuation_retains_online_lookup_behavior(self):
        with patch.object(valuation, 'fetch_online_zestimate', return_value=450000) as online, \
             patch.object(valuation, 'save_valuations_cache') as save:
            result = valuation.get_property_market_valuation('123 Sample Street', 200000, cache={})
        self.assertEqual(result['market_value'], 450000)
        online.assert_called_once()
        save.assert_called_once()

    def test_grouping_keeps_reply_and_uses_saved_values_without_network(self):
        # Compile the real grouping functions alone to avoid server import side effects.
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / 'server.py').read_text(encoding='utf-8'))
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('find_lead_by_phone', 'get_grouped_sms_threads')]
        self.assertEqual(len(funcs), 2)
        contacts = Mock(return_value={'parcel-1': {'clean_phone': '4075550123', 'phone': '4075550123', 'owner': 'Sample Seller', 'address': '123 Sample Street', 'just_value': 200000}})
        cached = Mock(return_value={'123samplestreet': {'market_value': 410000, 'source': 'Saved valuation', 'just_value': 200000}})
        logs = [
            {'timestamp': '2026-10-12 21:01:00', 'direction': 'INBOUND', 'phone': '+14075550123', 'message': 'Call me', 'status': 'RECEIVED'},
            {'timestamp': '2026-10-12 21:00:00', 'direction': 'OUTBOUND', 'phone': '(407) 555-0123', 'message': 'Hello', 'status': 'SENT'},
        ]
        with tempfile.TemporaryDirectory() as directory:
            history = Path(directory) / 'history.json'
            history.write_text(json.dumps(logs), encoding='utf-8')
            ns = {'os': os, 'json': json, 'Dict': Dict, 'List': List, 'Any': Any, 'Optional': Optional,
                  'OUTREACH_LOG_FILE': str(history), 'load_saved_contacts': contacts, 'load_valuations_cache': cached,
                  'get_property_market_valuation': valuation.get_property_market_valuation}
            exec(compile(ast.Module(body=funcs, type_ignores=[]), str(root / 'server.py'), 'exec'), ns)
            with patch.object(valuation, 'fetch_online_zestimate', side_effect=AssertionError('No network')):
                threads = ns['get_grouped_sms_threads']()
        self.assertEqual(len(threads), 1)
        self.assertEqual(threads[0]['owner'], 'Sample Seller')
        self.assertEqual(threads[0]['inbound_count'], 1)
        self.assertEqual(threads[0]['last_message'], 'Call me')
        self.assertEqual(threads[0]['market_value'], 410000)
        self.assertEqual(threads[0]['valuation_source'], 'Saved valuation')
        self.assertEqual([m['direction'] for m in threads[0]['messages']], ['OUTBOUND', 'INBOUND'])
        contacts.assert_called_once()
        cached.assert_called_once()


if __name__ == '__main__':
    unittest.main()
