import ast
import json
from pathlib import Path
import tempfile
from typing import Any, Dict
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI

from src import initial_sms_templates as shared
from src.seller_bot_engine import SellerBotEngine, sanitize_sms_no_underlines_no_hyphens
from src.sms_outreach_queue import fill_template


class SharedInitialSmsTests(unittest.TestCase):
    def test_saved_initial_messages_are_the_four_approved_owner_checks(self):
        expected = [
            "Hello, I'm trying to locate the property owner of {Address}. Would that be you?",
            "Hi, I'm looking for the homeowner at {Address}. Is that you?",
            "Hello, is this the right person to reach about ownership of {Address}?",
            "Hi there, I'm trying to get in touch with the owner of {Address}. Are you the owner?",
        ]
        self.assertEqual([t['body'] for t in shared.load_initial_sms_templates()], expected)
        self.assertEqual([t['body'] for t in shared.DEFAULT_SMS_TEMPLATES], expected)

    def setUp(self):
        self.bot = SellerBotEngine()
        self.lead = {'owner_name': 'Alice Smith', 'property_address': '123 Main St, Clearwater, FL',
                     'just_value': 200000, 'distress_count': 1}

    def test_every_county_and_distress_count_uses_the_same_current_template(self):
        templates = shared.load_initial_sms_templates()
        for template in templates:
            expected = sanitize_sms_no_underlines_no_hyphens(fill_template(template['body'],
                {'owner': 'Alice Smith', 'address': self.lead['property_address']}, 'Orange'))
            for county in ('Orange', 'Pinellas', 'Seminole', 'Hillsborough', 'Pasco'):
                for count in (1, 3):
                    result = self.bot.generate_initial_outreach(dict(self.lead, county=county, distress_count=count), forced_angle=template['id'])
                    self.assertEqual(result['suggested_reply'], expected)
                    self.assertEqual(result['opener_angle'], template['id'])
                    self.assertFalse(result['auto_send_allowed'])
                    self.assertNotIn('Saw the house online', result['suggested_reply'])

    def test_legacy_requests_use_updated_messages_and_saved_edits_are_shared(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'templates.json'
            path.write_text(json.dumps({'sms': [{'id': 'quick_question', 'body': 'Hi {FirstName}, is {Address} in {County} yours?'}]}), encoding='utf-8')
            with patch.object(shared, 'TEMPLATES_FILE', path):
                result = self.bot.generate_initial_outreach(dict(self.lead, county='Pinellas'), forced_angle='single_list')
                self.assertEqual(result['suggested_reply'], 'Hi Alice, is 123 Main in Pinellas yours?')
                self.assertEqual(result['opener_angle'], 'quick_question')
                self.assertEqual(len(shared.load_initial_sms_templates()), 4)

    def test_initial_generation_never_uses_ai_or_sends_a_message(self):
        with patch('src.seller_bot_engine.requests.post', side_effect=AssertionError('No network on initial suggestion')):
            for _ in range(12):
                result = self.bot.generate_initial_outreach(dict(self.lead, county='Pinellas'))
                self.assertIn(result['opener_angle'], shared.TEMPLATE_IDS)
                self.assertFalse(result['auto_send_allowed'])

    def test_bot_route_passes_selected_template_and_actual_county(self):
        tree = ast.parse(Path('server.py').read_text(encoding='utf-8'))
        definition = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate_bot_suggestion')
        bot = Mock()
        bot.generate_initial_outreach.return_value = {'suggested_reply': 'Updated opener', 'deal_evaluation': {}}
        ns = {'app': FastAPI(), 'Dict': Dict, 'Any': Any, 'seller_bot': bot,
              'find_lead_by_phone': lambda _: {'county': 'Orange'}, 'get_lead_sms_thread': lambda *_: []}
        exec(compile(ast.Module(body=[definition], type_ignores=[]), 'server.py', 'exec'), ns)
        result = ns['generate_bot_suggestion']({'seller_message': 'INITIAL_HOOK', 'county': 'Pinellas', 'opener_angle': 'quick_question', 'property_address': '123 Main St'})
        self.assertEqual(result['suggestion'], 'Updated opener')
        args, kwargs = bot.generate_initial_outreach.call_args
        self.assertEqual(args[0]['county'], 'Pinellas')
        self.assertEqual(kwargs['forced_angle'], 'quick_question')


if __name__ == '__main__': unittest.main()
