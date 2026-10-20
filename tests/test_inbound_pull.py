import ast
import asyncio
import io
import os
from pathlib import Path
import tempfile
import time
from typing import Optional
import unittest
from unittest.mock import patch

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from src.data_loader import ParcelDatabase
from src.matcher import CrossReferenceEngine
from src.normalizer import extract_human_defendants, extract_legal_tokens
from src.inbound_pull import (LIS_PENDENS_HEADERS, PullValidationError, identify_pull,
                              ingest_once, ingest_pull_file)


def shared_loader(directory):
    """Load actual app functions without initializing live outreach services."""
    tree = ast.parse(Path('server.py').read_text(encoding='utf-8'))
    names = {'read_lead_upload', 'run_match', 'match_lead_dataframe'}
    definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    parcels = pd.DataFrame([dict(PARCEL_NUMBER='P1', STRAP='P1', OWNER1='DISTINCT OWNER',
        SITE_ADDRESS='123 MAIN ST', SITE_CITY='ORLANDO', SITE_ZIP='32801',
        LEGAL='LOT 37 BLOCK 154 MEADOW WOODS VILLAGE 9 PHASE 2')])
    db = ParcelDatabase(parcels)
    ns = dict(app=FastAPI(), pd=pd, io=io, os=os, time=time, Optional=Optional,
              UploadFile=UploadFile, File=File, Form=Form, HTTPException=HTTPException,
              CrossReferenceEngine=CrossReferenceEngine, extract_human_defendants=extract_human_defendants,
              get_county_paths=lambda _: {'has_master': True, 'target_dir': directory},
              get_database=lambda _: db, load_custom_categories=lambda: [], load_saved_contacts=lambda: {})
    exec(compile(ast.Module(body=definitions, type_ignores=[]), 'server.py', 'exec'), ns)
    return ns


def clerk_frame(keys=('1', '2')):
    return pd.DataFrame([dict(zip(LIS_PENDENS_HEADERS,
        ['10/19/2026', key, '', 'BANK', 'OTHER PERSON', '',
         'Lot: 37 Block: 154 MEADOW WOODS VILLAGE 9 PHASE 2' if key == '1' else ''])) for key in keys])


class InboundPullTests(unittest.TestCase):
    def test_filename_orders_and_unknown_or_undefined_schemas(self):
        for name in ('lis-pendens-orange-2026-10-19.csv', 'orange-county-lis-pendens-2026-10-19.csv'):
            self.assertEqual(identify_pull(name, ['Orange']), ('lis-pendens', 'Orange'))
        for name in ('unknown-orange-2026-10-19.csv', 'lis-pendens-orange-2026-02-30.csv',
                     'lis-pendens-unknown-2026-10-19.csv'):
            with self.assertRaises(PullValidationError):
                identify_pull(name, ['Orange'])

    def test_persistent_dedupe_per_county_type_and_transaction_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / 'journal.db'
            calls = []
            load = lambda rows: calls.append(len(rows))
            first = ingest_once(clerk_frame(('1', '1', '2')), 'lis-pendens', 'Orange', 'one.csv', load, journal)
            self.assertEqual((first['rows_ingested'], first['rows_skipped_duplicates']), (2, 1))
            again = ingest_once(clerk_frame(), 'lis-pendens', 'Orange', 'two.csv', load, journal)
            self.assertEqual((again['rows_ingested'], again['rows_skipped_duplicates']), (0, 2))
            ingest_once(clerk_frame(), 'lis-pendens', 'Pinellas', 'two.csv', load, journal)
            ingest_once(clerk_frame(), 'probate', 'Orange', 'two.csv', load, journal)
            self.assertEqual(calls, [2, 2, 2])
            def fail(_):
                raise OSError('cache write failed')
            with self.assertRaises(OSError):
                ingest_once(clerk_frame(('3',)), 'lis-pendens', 'Orange', 'three.csv', fail, journal)
            retry = ingest_once(clerk_frame(('3',)), 'lis-pendens', 'Orange', 'three.csv', load, journal)
            self.assertEqual(retry['rows_ingested'], 1)

    def test_shared_pipeline_legal_match_empty_legal_and_first_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = shared_loader(directory)
            path = Path(directory) / 'orange-county-lis-pendens-2026-10-19.csv'
            clerk_frame().to_csv(path, index=False)
            journal = Path(directory) / 'journal.db'
            result = ingest_pull_file(path, ns['read_lead_upload'], ns['match_lead_dataframe'], ['Orange'], journal)
            self.assertEqual(result['rows_ingested'], 2)
            cache = pd.read_parquet(Path(directory) / 'matched_leads_cache.parquet')
            self.assertEqual(len(cache), 1)
            self.assertEqual(cache.iloc[0]['Parcel_ID'], 'P1')
            self.assertIn('Legal', cache.iloc[0]['Match_Method'])
            self.assertEqual(cache.iloc[0]['Source_File'], path.name)
            again = ingest_pull_file(path, ns['read_lead_upload'], ns['match_lead_dataframe'], ['Orange'], journal)
            self.assertEqual(again['rows_skipped_duplicates'], 2)
            self.assertEqual(extract_legal_tokens('Lot: 37 Block: 154')['lot'], '37')

    def test_manual_load_list_and_watcher_share_dedupe(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = shared_loader(directory)
            journal = Path(directory) / 'journal.db'
            with patch('src.inbound_pull.LEDGER_PATH', journal):
                data = clerk_frame().to_csv(index=False).encode()
                upload = UploadFile(filename='manual.csv', file=io.BytesIO(data))
                response = asyncio.run(ns['run_match']('Orange', 'lis_pendens', upload))
                self.assertEqual(response['kpis']['matched_count'], 1)
                path = Path(directory) / 'lis-pendens-orange-2026-10-19.csv'
                path.write_bytes(data)
                result = ingest_pull_file(path, ns['read_lead_upload'], ns['match_lead_dataframe'], ['Orange'])
                self.assertEqual(result['rows_ingested'], 0)
                self.assertEqual(result['rows_skipped_duplicates'], 2)

    def test_schema_mismatch_and_missing_key_never_call_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = shared_loader(directory)
            for name, frame, expected in [
                ('lis-pendens-orange-2026-10-19.csv', clerk_frame().rename(columns={'grantee': 'who'}), 'missing'),
                ('probate-orange-2026-10-19.csv', clerk_frame(), 'Schema not defined'),
                ('code-violations-orange-2026-10-19.csv', clerk_frame(), 'Schema not defined'),
                ('tax-lien-orange-2026-10-19.csv', clerk_frame(), 'Schema not defined'),
                ('lis-pendens-orange-2026-10-19.csv', clerk_frame(('',)), 'instrument_number'),
            ]:
                path = Path(directory) / name
                frame.to_csv(path, index=False)
                def fail(*_):
                    self.fail('Invalid file reached matcher')
                with self.assertRaisesRegex(PullValidationError, expected):
                    ingest_pull_file(path, ns['read_lead_upload'], fail, ['Orange'], Path(directory) / 'journal.db')

    def test_cache_failure_propagates_and_does_not_dedupe_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            ns = shared_loader(directory)
            path = Path(directory) / 'lis-pendens-orange-2026-10-19.csv'
            clerk_frame().to_csv(path, index=False)
            journal = Path(directory) / 'journal.db'
            with patch.object(pd.DataFrame, 'to_parquet', side_effect=OSError('disk full')):
                with self.assertRaisesRegex(OSError, 'disk full'):
                    ingest_pull_file(path, ns['read_lead_upload'], ns['match_lead_dataframe'], ['Orange'], journal)
            result = ingest_pull_file(path, ns['read_lead_upload'], ns['match_lead_dataframe'], ['Orange'], journal)
            self.assertEqual(result['rows_ingested'], 2)


if __name__ == '__main__':
    unittest.main()
