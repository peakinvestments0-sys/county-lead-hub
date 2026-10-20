"""Run the real queue routes with a fake gateway and isolated data files."""
import ast
import json
from pathlib import Path
import tempfile
from typing import List
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from src.sms_outreach_queue import SmsOutreachQueue, TEMPLATE_IDS


class AutoSmsApiTests(unittest.TestCase):
    def test_start_status_pause_resume_stop_routes_without_live_gateway(self):
        with tempfile.TemporaryDirectory() as directory:
            sent = []
            contacts = {'parcel-orange': {'county': 'Orange', 'owner': 'Jose Garcia', 'phone': '4072000001', 'address': '1 Main St', 'source': 'Skip Trace CSV (one.csv)'},
                        'parcel-lake': {'county': 'Lake', 'owner': 'Alice Lane', 'phone': '3522000002', 'address': '2 Main St', 'source': 'Skip Trace CSV (two.csv)'}}
            def send(payload):
                sent.append(payload)
                return {'status': 'success'}
            queue = SmsOutreachQueue(Path(directory) / 'queue.json', lambda: contacts, lambda: [],
                                     lambda: {'sms': [{'id': tid, 'body': 'Hi {FirstName}, {Address} in {County}'} for tid in TEMPLATE_IDS]},
                                     lambda *_: (False, ''), send)
            names = {'AutoSmsStartRequest', 'AutoSmsControlRequest', 'get_auto_sms_status', 'preview_auto_sms', 'start_auto_sms', 'control_auto_sms'}
            source = ast.parse((Path(__file__).resolve().parents[1] / 'server.py').read_text(encoding='utf-8'))
            definitions = [n for n in source.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
            self.assertEqual(len(definitions), 6)
            app = FastAPI()
            ns = {'app': app, 'auto_sms_queue': queue, 'BaseModel': BaseModel, 'List': List, 'HTTPException': HTTPException}
            exec(compile(ast.Module(body=definitions, type_ignores=[]), 'server.py', 'exec'), ns)
            with TestClient(app) as client:
                self.assertEqual(client.get('/api/sms/auto/status').json()['queue']['status'], 'idle')
                ids = {'parcel_ids': ['parcel-lake', 'parcel-orange']}
                self.assertEqual(client.post('/api/sms/auto/preview', json=ids).json()['eligible'], 2)
                self.assertEqual(sent, [])
                self.assertEqual(client.post('/api/sms/auto/start', json=ids).status_code, 200)
                self.assertEqual(sent, [], 'Starting persists a queue; only its worker dispatches')
                self.assertEqual(client.post('/api/sms/auto/start', json=ids).status_code, 400)
                self.assertEqual(client.post('/api/sms/auto/control', json={'action': 'pause'}).json()['queue']['status'], 'paused')
                queue.tick()
                self.assertEqual(sent, [])
                client.post('/api/sms/auto/control', json={'action': 'resume'})
                queue.tick()
                self.assertEqual(sent[0]['parcel_id'], 'parcel-lake')
                self.assertEqual(sent[0]['county'], 'Lake')
                self.assertEqual(sent[0]['message'], 'Hi Alice, 2 Main St in Lake')
                self.assertEqual(client.post('/api/sms/auto/control', json={'action': 'stop'}).json()['queue']['status'], 'stopped')
                self.assertEqual(client.get('/api/sms/auto/status').json()['queue']['sent'], 1)
                contacts['parcel-lake']['last_sms_status'] = 'SENT'
                follow_up = {'parcel_ids': ['parcel-lake', 'parcel-orange'], 'campaign': 'follow_up'}
                preview = client.post('/api/sms/auto/preview', json=follow_up).json()
                self.assertEqual(preview['eligible'], 1)
                self.assertEqual(preview['skipped_reasons'], {'No previous SMS': 1})
                self.assertEqual(len(sent), 1)
                response = client.post('/api/sms/auto/start', json=follow_up)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['queue']['campaign'], 'follow_up')
                self.assertEqual(len(sent), 1)
                queue.tick()
                self.assertEqual(sent[-1]['message'], "Hello, I'm trying to locate the property owner of 2 Main St. Would that be you?")
                self.assertEqual(client.post('/api/sms/auto/start', json=follow_up).status_code, 400)
                self.assertEqual(client.post('/api/sms/auto/start', json={**ids, 'campaign': 'invalid'}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
