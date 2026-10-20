import ast
import asyncio
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Any, Optional, Tuple
import unittest
from unittest.mock import Mock

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from src.saved_property_matches import PropertyMatchIndex, address_key


class SavedMatchTests(unittest.TestCase):
    def records(self):
        return [dict(Parcel_ID='123', Property_Address='10 Main St', Match_Status='MATCHED',
                     Lead_Type=kind, Case_Number=case, Source_File='county.csv', Is_Stacked_Distress='Yes')
                for kind, case in [('Lis Pendens', 'LP-1'), ('Civil Judgment', 'J-2')]]

    def test_persists_all_types_and_evidence_in_json_with_canonical_identity(self):
        result = PropertyMatchIndex(self.records(), 'cache.parquet').resolve('SKIP-1', {'address': '10 MAIN ST', 'county': 'Orange'})
        saved = json.loads(json.dumps(result))
        self.assertEqual(saved['matched_parcel_id'], '123')
        details = saved['property_match']['record']
        self.assertEqual(details['All_Lead_Types'], ['Lis Pendens', 'Civil Judgment'])
        self.assertEqual(details['Is_Stacked_Distress'], 'Yes')
        self.assertEqual(details['Has_Confirmed_Probate'], 'No')
        self.assertEqual([r['Case_Number'] for r in saved['property_match']['evidence']], ['LP-1', 'J-2'])
        self.assertTrue(saved['property_match']['checked_at'])

    def test_ambiguous_address_does_not_guess_and_saved_parcel_wins(self):
        records = self.records() + [dict(self.records()[0], Parcel_ID='456')]
        index = PropertyMatchIndex(records, 'cache')
        self.assertIsNone(index.resolve('SKIP-1', {'address': '10 Main St'}))
        result = index.resolve('SKIP-1', {'address': '10 Main St', 'matched_parcel_id': '123'})
        self.assertEqual(result['matched_parcel_id'], '123')

    def test_felony_flag_trust_and_probate_notes_do_not_invent_double_distress_or_probate(self):
        record = dict(self.records()[0], Lead_Type='Legal Distress (Felony)', Is_Trust_Or_Estate='Yes',
                      Distress_Stack_Notes='FELONY ARREST: two charges')
        result = PropertyMatchIndex([record], 'cache').resolve('123', {})['property_match']['record']
        self.assertEqual(result['Is_Stacked_Distress'], 'No')
        self.assertEqual(result['Has_Confirmed_Probate'], 'No')
        record['Distress_Stack_Notes'] = 'DOUBLE DISTRESS: Legal Distress (Felony) + Active County Probate Case'
        result = PropertyMatchIndex([record], 'cache').resolve('123', {})['property_match']['record']
        self.assertEqual(result['Has_Confirmed_Probate'], 'No')
        self.assertNotIn('Probate', result['All_Lead_Types'])

    def test_actual_probate_record_and_explicit_stack_notes(self):
        records = [dict(self.records()[0], Distress_Stack_Notes='DOUBLE DISTRESS: Lis Pendens + Open Municipal Code Violation'),
                   dict(self.records()[0], Lead_Type='Probate Court Paper')]
        result = PropertyMatchIndex(records, 'cache').resolve('123', {})['property_match']['record']
        self.assertEqual(result['Has_Confirmed_Probate'], 'Yes')
        self.assertEqual(set(result['All_Lead_Types']), {'Lis Pendens', 'Code Violation', 'Probate'})

    def test_death_certificate_labeled_probate_does_not_authorize_probate_email(self):
        records = [dict(self.records()[0], Lead_Type='Probate (Death Certificate)')]
        result = PropertyMatchIndex(records, 'cache').resolve('123', {})['property_match']['record']
        self.assertEqual(result['Has_Confirmed_Probate'], 'No')
        self.assertEqual(result['All_Lead_Types'], ['Death Certificate'])

    def test_legacy_judgment_or_lien_label_does_not_invent_a_third_condition(self):
        records = [dict(self.records()[0], Lead_Type='Code Violation',
                        Distress_Stack_Notes='DOUBLE DISTRESS: Code Violation + County Judgment / Recorded Lien'),
                   dict(self.records()[0], Lead_Type='Recorded Lien')]
        result = PropertyMatchIndex(records, 'cache').resolve('123', {})['property_match']['record']
        self.assertEqual(set(result['All_Lead_Types']), {'Code Violation', 'Recorded Lien'})

    def test_real_import_preserves_history_and_does_not_rematch_on_reimport(self):
        tree = ast.parse(Path('server.py').read_text(encoding='utf-8'))
        functions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name in ('import_skiptrace_endpoint', 'clean_phone_number')]
        contacts = {'SKIP-ORANGE-10-MAIN-ST': {'address': '10 Main St', 'county': 'Orange', 'state': 'FL',
                    'email': 'existing@example.org', 'last_sms_sent': '2026-10-14 10:00:00', 'last_sms_status': 'SENT'}}
        index = PropertyMatchIndex(self.records(), 'cache')
        get_index = Mock(return_value=index)
        def write(_, value):
            contacts.clear()
            contacts.update(json.loads(json.dumps(value)))
        namespace = {'app': FastAPI(), 'UploadFile': UploadFile, 'File': File, 'Form': Form, 'HTTPException': HTTPException,
                     'pd': pd, 'io': io, 're': __import__('re'), 'Optional': Optional, 'Tuple': Tuple, 'Any': Any,
                     'load_saved_contacts': lambda: json.loads(json.dumps(contacts)), 'address_key': address_key,
                     'detect_fl_county': lambda raw, city, default: raw or default,
                     'get_saved_property_index': get_index, 'OUTREACH_DATA_LOCK': threading.RLock(),
                     'atomic_outreach_json_write': write, 'CONTACTS_FILE': 'unused', 'time': time}
        exec(compile(ast.Module(body=functions, type_ignores=[]), 'server.py', 'exec'), namespace)
        csv = b'FirstName,LastName,PropertyAddress,PropertyCity,PropertyState,County,Contact1Phone_1,Contact1Email_1\nAlice,Adams,10 Main St,Orlando,FL,Orange,4072000001,\n'
        def run():
            upload = UploadFile(filename='contacts.csv', file=io.BytesIO(csv))
            return asyncio.run(namespace['import_skiptrace_endpoint'](upload, 'Orange'))
        self.assertEqual(run()['imported_count'], 1)
        contact = contacts['SKIP-ORANGE-10-MAIN-ST']
        self.assertEqual(contact['owner'], 'Alice Adams')
        self.assertEqual(contact['email'], 'existing@example.org')
        self.assertEqual(contact['last_sms_status'], 'SENT')
        self.assertEqual(contact['matched_parcel_id'], '123')
        snapshot = contact['property_match']
        get_index.reset_mock()
        run()
        get_index.assert_not_called()
        self.assertEqual(contacts['SKIP-ORANGE-10-MAIN-ST']['property_match'], snapshot)

    def test_explicit_refresh_backs_up_contacts_and_preserves_every_existing_field(self):
        names = {'get_saved_property_index', 'refresh_saved_property_matches', 'get_contacts'}
        tree = ast.parse(Path('server.py').read_text(encoding='utf-8'))
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            pd.DataFrame(self.records()).to_parquet(data / 'matched_leads_cache.parquet')
            original = {'SKIP-1': {'address': '10 Main St', 'county': 'Orange', 'email': 'a@example.org',
                                 'last_sms_status': 'SENT', 'last_email_sent': 'yesterday'},
                        'unresolved': {'county': 'Orange', 'address': 'Unknown Street', 'phone': '4072000001'}}
            contacts = data / 'saved_contacts.json'
            contacts.write_text(json.dumps(original), encoding='utf-8')
            def write(path, value):
                Path(path).write_text(json.dumps(value), encoding='utf-8')
            from src.saved_property_matches import load_property_index
            loader = Mock(side_effect=load_property_index)
            ns = {'app': FastAPI(), 'DATA_DIR': str(data), 'CONTACTS_FILE': str(contacts),
                  'load_saved_contacts': lambda: json.loads(contacts.read_text(encoding='utf-8')),
                  'get_county_paths': lambda *a, **k: {'target_dir': str(data)},
                  'load_property_index': loader, 'os': os, 'time': time,
                  'OUTREACH_DATA_LOCK': threading.RLock(), 'atomic_outreach_json_write': write}
            exec(compile(ast.Module(body=functions, type_ignores=[]), 'server.py', 'exec'), ns)
            result = ns['refresh_saved_property_matches']()
            self.assertEqual(result['matched_contacts'], 1)
            self.assertEqual(result['unresolved'], ['unresolved'])
            self.assertEqual(json.loads(Path(result['backup']).read_text()), original)
            saved = ns['get_contacts']()
            for pid, contact in original.items():
                for key, value in contact.items():
                    self.assertEqual(saved[pid][key], value)
            loader.reset_mock()
            for _ in range(3):
                self.assertEqual(ns['get_contacts']()['SKIP-1']['matched_parcel_id'], '123')
            loader.assert_not_called()


if __name__ == '__main__':
    unittest.main()
